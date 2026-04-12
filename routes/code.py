import ast
import os
import subprocess
import sys
import tempfile
import shutil

from flask import Blueprint, request, jsonify

import config
from services import ai

bp = Blueprint('code', __name__)


def _native_binary_path(dir_path, stem='solution'):
    suffix = '.exe' if os.name == 'nt' else ''
    return os.path.join(dir_path, stem + suffix)


def _command_for_windows(cmd):
    if os.name == 'nt' and cmd == 'npx':
        return 'npx.cmd'
    return cmd


def _resolve_typescript_runner():
    candidates = []
    if os.name == 'nt':
        candidates.extend([
            os.path.join(config.BASE_DIR, 'node_modules', '.bin', 'ts-node.cmd'),
            shutil.which('ts-node.cmd'),
            shutil.which('ts-node'),
        ])
    else:
        candidates.extend([
            os.path.join(config.BASE_DIR, 'node_modules', '.bin', 'ts-node'),
            shutil.which('ts-node'),
        ])

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    raise FileNotFoundError('ts-node is not installed. Install it globally or in this project to run TypeScript.')


def _typescript_run_command(path):
    try:
        return [_resolve_typescript_runner(), '--transpile-only', path]
    except FileNotFoundError:
        node = shutil.which('node')
        if node:
            # Fallback for JS-compatible TypeScript skeletons.
            return [node, path]
        raise


def _resolve_bash_runner():
    if os.name != 'nt':
        runner = shutil.which('bash')
        if runner:
            return runner
        raise FileNotFoundError('bash is not installed on the system.')

    candidates = [
        r'C:\Program Files\Git\bin\bash.exe',
        r'C:\Program Files\Git\usr\bin\bash.exe',
        shutil.which('bash.exe'),
        shutil.which('bash'),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate) and 'git' in candidate.lower():
            return candidate

    raise FileNotFoundError(
        'Bash execution on Windows requires Git Bash. '
        'The built-in Windows bash bridge is not usable here without a configured Linux distribution.'
    )


def _bash_run_command(path):
    return [_resolve_bash_runner(), path]


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
        'run': _typescript_run_command,
    },
    'java': {
        'extension': '.java',
        'compile': lambda path, dir: ['javac', path],
        'run': lambda path, dir: ['java', '-cp', dir, _java_class_name(path)],
    },
    'c': {
        'extension': '.c',
        'compile': lambda path, dir: ['gcc', '-o', _native_binary_path(dir), path, '-lm'],
        'run': lambda path, dir: [_native_binary_path(dir)],
    },
    'cpp': {
        'extension': '.cpp',
        'compile': lambda path, dir: ['g++', '-o', _native_binary_path(dir), path, '-lm', '-lstdc++'],
        'run': lambda path, dir: [_native_binary_path(dir)],
    },
    'go': {
        'extension': '.go',
        'compile': None,
        'run': lambda path: ['go', 'run', path],
    },
    'rust': {
        'extension': '.rs',
        'compile': lambda path, dir: ['rustc', '-o', _native_binary_path(dir), path],
        'run': lambda path, dir: [_native_binary_path(dir)],
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
        'run': _bash_run_command,
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


def _language_runtime_status(language):
    if language == 'python':
        return True, sys.executable
    if language == 'javascript':
        return (_check_tool_available('node'), 'Node.js is required for JavaScript execution.')
    if language == 'typescript':
        try:
            runner = _resolve_typescript_runner()
            return True, f'Using {runner}'
        except FileNotFoundError:
            if _check_tool_available('node'):
                return True, 'Using Node fallback for JS-compatible TypeScript code.'
            return False, 'TypeScript requires ts-node or Node.js to be installed.'
    if language == 'java':
        return (_check_tool_available('javac') and _check_tool_available('java'), 'Java requires both javac and java.')
    if language == 'c':
        return (_check_tool_available('gcc'), 'C requires gcc.')
    if language == 'cpp':
        return (_check_tool_available('g++'), 'C++ requires g++.')
    if language == 'go':
        return (_check_tool_available('go'), 'Go requires the go toolchain.')
    if language == 'rust':
        return (_check_tool_available('rustc'), 'Rust requires rustc.')
    if language == 'ruby':
        return (_check_tool_available('ruby'), 'Ruby requires ruby.')
    if language == 'php':
        return (_check_tool_available('php'), 'PHP requires php.')
    if language == 'swift':
        return (_check_tool_available('swift'), 'Swift requires swift.')
    if language == 'kotlin':
        return (_check_tool_available('kotlinc') and _check_tool_available('java'), 'Kotlin requires kotlinc and java.')
    if language == 'csharp':
        return (_check_tool_available('dotnet-script'), 'C# scripting requires dotnet-script.')
    if language == 'bash':
        try:
            runner = _resolve_bash_runner()
            return True, f'Using {runner}'
        except FileNotFoundError as exc:
            return False, str(exc)
    if language == 'sql':
        return True, 'Using sqlite3 CLI or Python sqlite fallback.'
    return False, f'Unsupported language: {language}'


def _is_stub_statement(stmt):
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
        return stmt.value.value in (Ellipsis,) or isinstance(stmt.value.value, str)
    if isinstance(stmt, ast.Return):
        return stmt.value is None or (isinstance(stmt.value, ast.Constant) and stmt.value.value is None)
    if isinstance(stmt, ast.Raise):
        if isinstance(stmt.exc, ast.Call) and isinstance(stmt.exc.func, ast.Name):
            return stmt.exc.func.id == 'NotImplementedError'
        if isinstance(stmt.exc, ast.Name):
            return stmt.exc.id == 'NotImplementedError'
    return False


def _extract_simple_python_function_stub(code):
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    if len(tree.body) != 1:
        return None

    node = tree.body[0]
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    if node.decorator_list or node.args.kwonlyargs or node.args.vararg or node.args.kwarg:
        return None
    if not node.body or not all(_is_stub_statement(stmt) for stmt in node.body):
        return None

    params = [arg.arg for arg in node.args.args]
    return {
        'name': node.name,
        'params': params,
        'is_async': isinstance(node, ast.AsyncFunctionDef),
    }


def _commented_param_hint(params):
    return ', '.join(params) if params else 'none'


def _build_local_function_translation(function_info, to_lang):
    name = function_info['name']
    params = function_info['params']
    js_params = ', '.join(params)
    java_params = ', '.join(f'Object {param}' for param in params) or ''
    csharp_params = ', '.join(f'object {param}' for param in params) or ''
    php_params = ', '.join(f'${param}' for param in params)
    ruby_params = ', '.join(params)
    go_params = ', '.join(f'{param} interface{{}}' for param in params)
    kotlin_params = ', '.join(f'{param}: Any?' for param in params)
    swift_params = ', '.join(f'_{param}: Any' for param in params)
    async_prefix = 'async ' if function_info['is_async'] and to_lang in ('javascript', 'typescript') else ''

    translations = {
        'javascript': (
            f'{async_prefix}function {name}({js_params}) {{\n'
            '  // TODO: implement\n'
            '  return null;\n'
            '}\n'
        ),
        'typescript': (
            f'{async_prefix}function {name}({js_params}) {{\n'
            '  // TODO: implement\n'
            '  return null;\n'
            '}\n'
        ),
        'java': (
            'import java.util.*;\n\n'
            'public class Solution {\n'
            f'    public static Object {name}({java_params}) {{\n'
            '        // TODO: implement\n'
            '        return null;\n'
            '    }\n'
            '}\n'
        ),
        'c': (
            '#include <stdio.h>\n\n'
            f'void {name}(void) {{\n'
            f'    /* TODO: add parameter types for: {_commented_param_hint(params)} */\n'
            '}\n\n'
            'int main(void) {\n'
            '    return 0;\n'
            '}\n'
        ),
        'cpp': (
            '#include <iostream>\n'
            'using namespace std;\n\n'
            f'void {name}(/* params: {_commented_param_hint(params)} */) {{\n'
            '    // TODO: implement\n'
            '}\n\n'
            'int main() {\n'
            '    return 0;\n'
            '}\n'
        ),
        'go': (
            'package main\n\n'
            f'func {name}({go_params}) interface{{}} {{\n'
            '    // TODO: implement\n'
            '    return nil\n'
            '}\n\n'
            'func main() {}\n'
        ),
        'rust': (
            f'fn {name}(/* params: {_commented_param_hint(params)} */) {{\n'
            '    // TODO: implement\n'
            '}\n\n'
            'fn main() {}\n'
        ),
        'ruby': (
            f'def {name}({ruby_params})\n'
            '  # TODO: implement\n'
            '  nil\n'
            'end\n'
        ),
        'php': (
            '<?php\n\n'
            f'function {name}({php_params}) {{\n'
            '    // TODO: implement\n'
            '    return null;\n'
            '}\n'
        ),
        'swift': (
            'import Foundation\n\n'
            f'func {name}({swift_params}) -> Any? {{\n'
            '    // TODO: implement\n'
            '    return nil\n'
            '}\n'
        ),
        'kotlin': (
            f'fun {name}({kotlin_params}): Any? {{\n'
            '    // TODO: implement\n'
            '    return null\n'
            '}\n\n'
            'fun main() {}\n'
        ),
        'csharp': (
            'using System;\n'
            'using System.Collections.Generic;\n\n'
            'public class Solution\n'
            '{\n'
            f'    public static object {name}({csharp_params})\n'
            '    {\n'
            '        // TODO: implement\n'
            '        return null;\n'
            '    }\n'
            '}\n'
        ),
        'bash': (
            '#!/usr/bin/env bash\n'
            f'# TODO: convert the {name} algorithm to Bash.\n'
            f'# Original parameters: {_commented_param_hint(params)}\n'
        ),
        'sql': (
            '-- SQL translation is not available for Python function starter code.\n'
            f'-- Original function: {name}({_commented_param_hint(params)})\n'
        ),
    }
    return translations.get(to_lang)


def _clean_translated_code(translated):
    translated = (translated or '').strip()
    if translated.startswith('```'):
        lines = translated.split('\n')
        if lines and lines[-1].strip() == '```':
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        translated = '\n'.join(lines)
    return translated.strip()


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

    is_available, status_message = _language_runtime_status(language)
    if not is_available:
        return _simulate_execution_with_ai(language, user_code)

    # For SQL, use a special handler
    if language == 'sql':
        return _run_sql(user_code)

    # Create temp directory for compiled languages
    tmpdir = tempfile.mkdtemp(prefix='codeprep_run_', dir=config.RUNNER_TEMP_DIR)
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
    fd, path = tempfile.mkstemp(suffix='.sql', prefix='codeprep_sql_', dir=config.RUNNER_TEMP_DIR)
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
    fd, path = tempfile.mkstemp(suffix='.py', prefix='codeprep_sql_py_', dir=config.RUNNER_TEMP_DIR)
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

    if from_lang == 'python':
        stub = _extract_simple_python_function_stub(code)
        if stub:
            translated = _build_local_function_translation(stub, to_lang)
            if translated:
                return jsonify({
                    'translated_code': translated,
                    'source': 'local_template',
                })

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
        client = ai.get_client()
        response = ai.create_chat_completion(
            client,
            messages=[{'role': 'user', 'content': prompt}],
            model=ai.get_model(),
            temperature=0.1,
            max_tokens=1000,
        )
        translated = _clean_translated_code(response.choices[0].message.content)

        if translated:
            return jsonify({'translated_code': translated, 'source': 'ai'})
    except Exception as e:
        if from_lang == 'python':
            stub = _extract_simple_python_function_stub(code)
            if stub:
                translated = _build_local_function_translation(stub, to_lang)
                if translated:
                    return jsonify({
                        'translated_code': translated,
                        'source': 'local_template_fallback',
                        'warning': str(e),
                    })
        return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Translation returned no code'}), 500


@bp.route('/api/languages', methods=['GET'])
def list_languages():
    """Return list of supported languages."""
    languages = []
    label_overrides = {
        'cpp': 'C++',
        'csharp': 'C#',
        'sql': 'SQL',
        'php': 'PHP',
        'javascript': 'JavaScript',
        'typescript': 'TypeScript',
    }
    for key, cfg in LANG_CONFIG.items():
        available, status = _language_runtime_status(key)
        languages.append({
            'id': key,
            'label': label_overrides.get(key, key.title()),
            'extension': cfg['extension'],
            'available': True,
            'status': status if available else 'Available via AI Cloud Simulation',
        })
    return jsonify(languages)

def _simulate_execution_with_ai(language, code):
    """Simulate code execution using the AI model when a local compiler is unavailable."""
    import json
    client = ai.get_client()
    prompt = f"""You are a strict, deterministic execution environment for {language}.
The user has submitted code. You must thoroughly compile and execute it.
If there are compilation or syntax errors, return them in "stderr" with exit_code 1.
If the code runs successfully, return its standard output in "stdout" and set exit_code to 0.
Return ONLY a JSON object with keys "stdout", "stderr", and "exit_code". Do not include any other text.

Code:
```
{code}
```"""
    try:
        response = ai.create_chat_completion(
            client,
            messages=[{'role': 'system', 'content': 'You are a code execution engine. Respond ONLY with valid JSON.'},
                      {'role': 'user', 'content': prompt}],
            model=ai.get_model(),
            temperature=0.0,
            max_tokens=2000,
            response_format={'type': 'json_object'}
        )
        
        raw = response.choices[0].message.content or ''
        result = json.loads(raw)
        
        stdout_val = result.get('stdout', '') or ''
        stderr_val = result.get('stderr', '') or ''
        
        return jsonify({
            'stdout': str(stdout_val) + '\n[Output generated by AI Cloud Simulation]',
            'stderr': str(stderr_val),
            'exit_code': int(result.get('exit_code', 0))
        })
    except Exception as e:
        return jsonify({
            'stdout': '',
            'stderr': f'AI Simulation Failed: {str(e)}',
            'exit_code': 1
        })

