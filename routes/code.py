import ast
import os
import sys

from flask import Blueprint, request, jsonify

import config
from services import ai
from services import judge

bp = Blueprint('code', __name__)

# Supported languages metadata (used for /api/languages and translation)
LANG_CONFIG = {
    'python': {
        'extension': '.py',
        'label': 'Python',
    },
    'javascript': {
        'extension': '.js',
        'label': 'JavaScript',
    },
    'c': {
        'extension': '.c',
        'label': 'C',
    },
    'cpp': {
        'extension': '.cpp',
        'label': 'C++',
    },
    'java': {
        'extension': '.java',
        'label': 'Java',
    },
    'sql': {
        'extension': '.sql',
        'label': 'SQL',
    },
}


# ---------------------------------------------------------------------------
# Python stub extraction helpers (used for local translate-code fast path)
# ---------------------------------------------------------------------------

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
    async_prefix = 'async ' if function_info['is_async'] and to_lang == 'javascript' else ''

    translations = {
        'javascript': (
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route('/api/run', methods=['POST'])
def run_code():
    data = request.json or {}
    user_code = data.get('code', '')
    language = data.get('language', 'python')
    stdin = data.get('stdin', '')

    if not user_code.strip():
        return jsonify({'error': 'No code provided'}), 400

    if language not in LANG_CONFIG:
        return jsonify({
            'stdout': '',
            'stderr': f'Unsupported language: {language!r}. Supported: {", ".join(LANG_CONFIG)}',
            'exit_code': 1,
            'status': 'unsupported_language',
        })

    result = judge.dispatch(user_code, language, stdin=stdin, timeout=config.CODE_TIMEOUT)
    return jsonify({
        'stdout': result['stdout'],
        'stderr': result['stderr'],
        'exit_code': result['exit_code'],
        'status': result['status'],
    })


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

    # Fast path: local template for simple Python stubs
    if from_lang == 'python':
        stub = _extract_simple_python_function_stub(code)
        if stub:
            translated = _build_local_function_translation(stub, to_lang)
            if translated:
                return jsonify({
                    'translated_code': translated,
                    'source': 'local_template',
                })

    from_name = LANG_CONFIG.get(from_lang, {}).get('label', from_lang)
    to_name = LANG_CONFIG.get(to_lang, {}).get('label', to_lang)

    prompt = (
        f'Convert the following {from_name} starter code skeleton to {to_name}.\n'
        f'This is a coding interview problem{chr(34) + problem_title + chr(34) if problem_title else ""}.\n\n'
        'Rules:\n'
        '- Keep the same class/function structure and method signatures\n'
        '- Translate types appropriately\n'
        '- Keep method/function names the same\n'
        f'- Use idiomatic {to_name} style and conventions\n'
        '- Keep the body as empty/stub\n'
        '- Return ONLY the translated code, no explanation or markdown\n\n'
        f'{from_name} code:\n```\n{code}\n```\n\n{to_name} code:'
    )

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
    except Exception as exc:
        # AI failed — try local template fallback
        if from_lang == 'python':
            stub = _extract_simple_python_function_stub(code)
            if stub:
                translated = _build_local_function_translation(stub, to_lang)
                if translated:
                    return jsonify({
                        'translated_code': translated,
                        'source': 'local_template_fallback',
                        'warning': str(exc),
                    })
        return jsonify({'error': str(exc)}), 500

    return jsonify({'error': 'Translation returned no code'}), 500


@bp.route('/api/languages', methods=['GET'])
def list_languages():
    """Return list of supported languages with availability status."""
    languages = []
    for key, cfg in LANG_CONFIG.items():
        languages.append({
            'id': key,
            'label': cfg['label'],
            'extension': cfg['extension'],
            'available': True,
            'status': f'{cfg["label"]} is supported.',
        })
    return jsonify(languages)
