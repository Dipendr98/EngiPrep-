import os
import subprocess
import sys
import tempfile
import shutil

from flask import Blueprint, request, jsonify

import config

bp = Blueprint('code', __name__)

# Language configurations for compilation and execution
LANG_CONFIG = {
    'python': {
        'extension': '.py',
        'compile': None,
        'run': lambda path: [sys.executable, path],
    },
    'javascript': {
        'extension': '.js',
        'compile': None,
        'run': lambda path: ['node', path],
    },
    'typescript': {
        'extension': '.ts',
        'compile': None,
        'run': lambda path: ['npx', 'ts-node', '--transpile-only', path],
    },
    'java': {
        'extension': '.java',
        'compile': lambda path, dir: ['javac', path],
        'run': lambda path, dir: ['java', '-cp', dir, _java_class_name(path)],
    },
    'c': {
        'extension': '.c',
        'compile': lambda path, dir: ['gcc', '-o', os.path.join(dir, 'a.out'), path, '-lm'],
        'run': lambda path, dir: [os.path.join(dir, 'a.out')],
    },
    'cpp': {
        'extension': '.cpp',
        'compile': lambda path, dir: ['g++', '-o', os.path.join(dir, 'a.out'), path, '-lm', '-lstdc++'],
        'run': lambda path, dir: [os.path.join(dir, 'a.out')],
    },
    'go': {
        'extension': '.go',
        'compile': None,
        'run': lambda path: ['go', 'run', path],
    },
    'rust': {
        'extension': '.rs',
        'compile': lambda path, dir: ['rustc', '-o', os.path.join(dir, 'a.out'), path],
        'run': lambda path, dir: [os.path.join(dir, 'a.out')],
    },
    'ruby': {
        'extension': '.rb',
        'compile': None,
        'run': lambda path: ['ruby', path],
    },
    'php': {
        'extension': '.php',
        'compile': None,
        'run': lambda path: ['php', path],
    },
    'swift': {
        'extension': '.swift',
        'compile': None,
        'run': lambda path: ['swift', path],
    },
    'kotlin': {
        'extension': '.kt',
        'compile': lambda path, dir: ['kotlinc', path, '-include-runtime', '-d', os.path.join(dir, 'out.jar')],
        'run': lambda path, dir: ['java', '-jar', os.path.join(dir, 'out.jar')],
    },
    'csharp': {
        'extension': '.cs',
        'compile': None,
        'run': lambda path: ['dotnet-script', path],
    },
    'bash': {
        'extension': '.sh',
        'compile': None,
        'run': lambda path: ['bash', path],
    },
    'sql': {
        'extension': '.sql',
        'compile': None,
        'run': lambda path: ['sqlite3', ':memory:', '.read ' + path],
        'use_shell': True,
    },
}


def _java_class_name(path):
    """Extract public class name from Java file for execution."""
    basename = os.path.basename(path)
    return os.path.splitext(basename)[0]


def _check_tool_available(cmd):
    """Check if a command-line tool is available."""
    try:
        result = subprocess.run(
            ['where' if os.name == 'nt' else 'which', cmd],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


@bp.route('/api/run', methods=['POST'])
def run_code():
    data = request.json or {}
    user_code = data.get('code', '')
    language = data.get('language', 'python')

    if not user_code.strip():
        return jsonify({'error': 'No code provided'}), 400

    lang_cfg = LANG_CONFIG.get(language)
    if not lang_cfg:
        return jsonify({
            'stdout': '',
            'stderr': f'Unsupported language: {language}',
            'exit_code': 1,
        })

    # For SQL, use a special handler
    if language == 'sql':
        return _run_sql(user_code)

    # Create temp directory for compiled languages
    tmpdir = tempfile.mkdtemp(prefix='codeprep_run_')
    ext = lang_cfg['extension']

    # Java requires filename to match class name
    if language == 'java':
        class_name = _extract_java_class(user_code)
        filename = class_name + ext
    else:
        filename = 'solution' + ext

    filepath = os.path.join(tmpdir, filename)

    try:
        with open(filepath, 'w') as f:
            f.write(user_code)

        # Compilation step (if needed)
        compile_fn = lang_cfg.get('compile')
        if compile_fn:
            try:
                compile_cmd = compile_fn(filepath, tmpdir)
                compile_result = subprocess.run(
                    compile_cmd,
                    capture_output=True, text=True,
                    timeout=config.CODE_TIMEOUT,
                    cwd=tmpdir,
                )
                if compile_result.returncode != 0:
                    return jsonify({
                        'stdout': compile_result.stdout,
                        'stderr': f'Compilation Error:\n{compile_result.stderr}',
                        'exit_code': compile_result.returncode,
                    })
            except subprocess.TimeoutExpired:
                return jsonify({
                    'stdout': '',
                    'stderr': f'Compilation timeout (>{config.CODE_TIMEOUT}s)',
                    'exit_code': 1,
                })
            except FileNotFoundError as e:
                return jsonify({
                    'stdout': '',
                    'stderr': f'Compiler not found. Make sure the {language} compiler is installed.\n{e}',
                    'exit_code': 1,
                })

        # Execution step
        try:
            run_fn = lang_cfg['run']
            # Some run functions take (path, dir), others just (path)
            import inspect
            params = inspect.signature(run_fn).parameters
            if len(params) == 2:
                run_cmd = run_fn(filepath, tmpdir)
            else:
                run_cmd = run_fn(filepath)

            result = subprocess.run(
                run_cmd,
                capture_output=True, text=True,
                timeout=config.CODE_TIMEOUT,
                cwd=tmpdir,
            )
            return jsonify({
                'stdout': result.stdout,
                'stderr': result.stderr,
                'exit_code': result.returncode,
            })
        except subprocess.TimeoutExpired:
            return jsonify({
                'stdout': '',
                'stderr': f'Timeout: code took too long (>{config.CODE_TIMEOUT}s)',
                'exit_code': 1,
            })
        except FileNotFoundError as e:
            return jsonify({
                'stdout': '',
                'stderr': f'Runtime not found. Make sure {language} is installed on the system.\n{e}',
                'exit_code': 1,
            })

    except Exception as e:
        return jsonify({
            'stdout': '',
            'stderr': f'Runner error: {e}',
            'exit_code': 1,
        })
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except OSError:
            pass


def _extract_java_class(code):
    """Extract the public class name from Java source code."""
    import re
    match = re.search(r'public\s+class\s+(\w+)', code)
    if match:
        return match.group(1)
    return 'Solution'


def _run_sql(user_code):
    """Run SQL code using sqlite3."""
    fd, path = tempfile.mkstemp(suffix='.sql', prefix='codeprep_sql_')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(user_code)

        # Try sqlite3
        try:
            result = subprocess.run(
                ['sqlite3', ':memory:'],
                input=user_code,
                capture_output=True, text=True,
                timeout=config.CODE_TIMEOUT,
            )
            return jsonify({
                'stdout': result.stdout,
                'stderr': result.stderr,
                'exit_code': result.returncode,
            })
        except FileNotFoundError:
            # Fallback: try python's sqlite3 module
            return _run_sql_python(user_code)
        except subprocess.TimeoutExpired:
            return jsonify({
                'stdout': '',
                'stderr': f'Timeout: SQL took too long (>{config.CODE_TIMEOUT}s)',
                'exit_code': 1,
            })
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _run_sql_python(user_code):
    """Run SQL using Python's built-in sqlite3 module as fallback."""
    wrapper = f'''
import sqlite3
import sys

conn = sqlite3.connect(':memory:')
cursor = conn.cursor()

statements = """{user_code}"""

try:
    for statement in statements.split(';'):
        statement = statement.strip()
        if statement:
            cursor.execute(statement)
            if cursor.description:
                cols = [d[0] for d in cursor.description]
                print('|'.join(cols))
                print('-' * 40)
                for row in cursor.fetchall():
                    print('|'.join(str(v) for v in row))
    conn.commit()
except Exception as e:
    print(f"SQL Error: {{e}}", file=sys.stderr)
    sys.exit(1)
finally:
    conn.close()
'''
    fd, path = tempfile.mkstemp(suffix='.py', prefix='codeprep_sql_py_')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(wrapper)
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True,
            timeout=config.CODE_TIMEOUT,
        )
        return jsonify({
            'stdout': result.stdout,
            'stderr': result.stderr,
            'exit_code': result.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            'stdout': '',
            'stderr': f'Timeout: SQL took too long (>{config.CODE_TIMEOUT}s)',
            'exit_code': 1,
        })
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@bp.route('/api/translate-code', methods=['POST'])
def translate_code():
    """Translate starter code from one language to another using AI."""
    data = request.json or {}
    code = data.get('code', '')
    from_lang = data.get('from_language', 'python')
    to_lang = data.get('to_language', '')
    problem_title = data.get('problem_title', '')

    if not code.strip() or not to_lang:
        return jsonify({'error': 'Missing code or target language'}), 400

    if from_lang == to_lang:
        return jsonify({'translated_code': code})

    lang_names = {
        'python': 'Python', 'javascript': 'JavaScript', 'typescript': 'TypeScript',
        'java': 'Java', 'c': 'C', 'cpp': 'C++', 'csharp': 'C#', 'go': 'Go',
        'rust': 'Rust', 'ruby': 'Ruby', 'php': 'PHP', 'swift': 'Swift',
        'kotlin': 'Kotlin', 'bash': 'Bash', 'sql': 'SQL',
    }
    from_name = lang_names.get(from_lang, from_lang)
    to_name = lang_names.get(to_lang, to_lang)

    prompt = f"""Convert the following {from_name} starter code skeleton to {to_name}. 
This is a coding interview problem{' called "' + problem_title + '"' if problem_title else ''}.

Rules:
- Keep the same class/function structure and method signatures
- Translate types appropriately (e.g., Python int -> Java int, Python list -> Java List, etc.)
- Keep method/function names the same
- Use idiomatic {to_name} style and conventions
- Keep the body as empty/stub (pass, return default, throw not implemented, etc.)
- Do NOT add any explanation, comments about the translation, or markdown formatting
- Return ONLY the translated code, nothing else

{from_name} code:
```
{code}
```

{to_name} code:"""

    try:
        from services.ai import get_client, get_model
        client = get_client()
        response = client.chat.completions.create(
            model=get_model(),
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.1,
            max_tokens=1000,
        )
        translated = response.choices[0].message.content.strip()
        # Clean up: remove markdown code fences if present
        translated = translated.strip()
        if translated.startswith('```'):
            lines = translated.split('\n')
            # Remove first line (```lang) and last line (```)
            if lines[-1].strip() == '```':
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            translated = '\n'.join(lines)
        translated = translated.strip()

        return jsonify({'translated_code': translated})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/languages', methods=['GET'])
def list_languages():
    """Return list of supported languages."""
    languages = []
    for key, cfg in LANG_CONFIG.items():
        languages.append({
            'id': key,
            'label': key.replace('cpp', 'C++').replace('csharp', 'C#').title() if key not in ('cpp', 'csharp', 'sql', 'php') else
                     {'cpp': 'C++', 'csharp': 'C#', 'sql': 'SQL', 'php': 'PHP'}.get(key, key),
            'extension': cfg['extension'],
        })
    return jsonify(languages)