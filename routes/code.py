import ast
import os
import sys

from flask import Blueprint, request, jsonify

import config
from services import ai
from services import judge

bp = Blueprint('code', __name__)
_node_strip_types_support = None


def _resolve_tool_path(*candidates):
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        if os.path.isabs(candidate) and os.path.exists(candidate):
            return candidate

    if os.name == 'nt':
        home = os.path.expanduser('~')
        scoop_candidates = {
            'node': [
                os.path.join(home, 'scoop', 'apps', 'nodejs', 'current', 'node.exe'),
                os.path.join(home, 'scoop', 'shims', 'node.exe'),
                os.path.join(home, 'scoop', 'shims', 'node.cmd'),
            ],
            'node.exe': [
                os.path.join(home, 'scoop', 'apps', 'nodejs', 'current', 'node.exe'),
                os.path.join(home, 'scoop', 'shims', 'node.exe'),
            ],
            'gcc': [
                os.path.join(home, 'scoop', 'apps', 'gcc', 'current', 'bin', 'gcc.exe'),
                os.path.join(home, 'scoop', 'shims', 'gcc.exe'),
                os.path.join(home, 'scoop', 'shims', 'gcc.cmd'),
            ],
            'g++': [
                os.path.join(home, 'scoop', 'apps', 'gcc', 'current', 'bin', 'g++.exe'),
                os.path.join(home, 'scoop', 'shims', 'g++.exe'),
                os.path.join(home, 'scoop', 'shims', 'g++.cmd'),
            ],
            'javac': [
                os.path.join(home, 'scoop', 'apps', 'openjdk', 'current', 'bin', 'javac.exe'),
                os.path.join(home, 'scoop', 'apps', 'temurin-jdk', 'current', 'bin', 'javac.exe'),
                os.path.join(home, 'scoop', 'shims', 'javac.exe'),
                os.path.join(home, 'scoop', 'shims', 'javac.cmd'),
            ],
            'java': [
                os.path.join(home, 'scoop', 'apps', 'openjdk', 'current', 'bin', 'java.exe'),
                os.path.join(home, 'scoop', 'apps', 'temurin-jdk', 'current', 'bin', 'java.exe'),
                os.path.join(home, 'scoop', 'shims', 'java.exe'),
                os.path.join(home, 'scoop', 'shims', 'java.cmd'),
            ],
        }
        for candidate in candidates:
            for path in scoop_candidates.get(candidate, []):
                if os.path.exists(path):
                    return path
    return None


def _resolve_node_runner():
    if os.name == 'nt':
        return _resolve_tool_path('node.exe', 'node', r'C:\Program Files\nodejs\node.exe')
    return _resolve_tool_path('node')


def _require_tool(name):
    resolved = _resolve_tool_path(name)
    if resolved:
        return resolved
    raise FileNotFoundError(f'{name} is not installed or not available on PATH.')

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

def _language_execution_profile(language):
    local_available, status = _language_runtime_status(language)
    supports_simulation = language != 'python'
    if local_available:
        return {
            'local_available': True,
            'supports_simulation': supports_simulation,
            'execution_mode': 'local',
            'status': status,
        }
    if supports_simulation:
        return {
            'local_available': False,
            'supports_simulation': True,
            'execution_mode': 'simulated',
            'status': status,
        }
    return {
        'local_available': False,
        'supports_simulation': False,
        'execution_mode': 'unavailable',
        'status': status,
    }


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


def _annotation_to_python_text(annotation):
    if annotation is None:
        return None
    try:
        return ast.unparse(annotation)
    except Exception:
        return None


def _extract_simple_python_class_stub(code):
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    class_nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if len(class_nodes) != 1 or len(tree.body) != 1:
        return None

    class_node = class_nodes[0]
    if class_node.decorator_list or class_node.bases or class_node.keywords:
        return None

    methods = []
    for node in class_node.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return None
        if node.decorator_list or node.args.kwonlyargs or node.args.vararg or node.args.kwarg:
            return None
        if not node.body or not all(_is_stub_statement(stmt) for stmt in node.body):
            return None

        params = []
        for arg in node.args.args[1:]:
            params.append({
                'name': arg.arg,
                'annotation': _annotation_to_python_text(arg.annotation),
            })

        methods.append({
            'name': node.name,
            'params': params,
            'return_annotation': _annotation_to_python_text(node.returns),
            'is_async': isinstance(node, ast.AsyncFunctionDef),
        })

    return {
        'name': class_node.name,
        'methods': methods,
    }


def _commented_param_hint(params):
    return ', '.join(params) if params else 'none'


def _map_python_type(annotation, target_lang):
    normalized = (annotation or '').strip()
    if not normalized:
        defaults = {
            'java': 'Object',
            'csharp': 'object',
            'go': 'interface{}',
            'kotlin': 'Any?',
            'swift': 'Any',
            'typescript': 'any',
        }
        return defaults.get(target_lang)

    base = normalized.replace(' ', '')
    if base in ('int', 'float'):
        return {
            'java': 'int' if base == 'int' else 'double',
            'csharp': 'int' if base == 'int' else 'double',
            'go': 'int' if base == 'int' else 'float64',
            'kotlin': 'Int' if base == 'int' else 'Double',
            'swift': 'Int' if base == 'int' else 'Double',
            'typescript': 'number',
        }.get(target_lang)
    if base == 'bool':
        return {
            'java': 'boolean',
            'csharp': 'bool',
            'go': 'bool',
            'kotlin': 'Boolean',
            'swift': 'Bool',
            'typescript': 'boolean',
        }.get(target_lang)
    if base == 'str':
        return {
            'java': 'String',
            'csharp': 'string',
            'go': 'string',
            'kotlin': 'String',
            'swift': 'String',
            'typescript': 'string',
        }.get(target_lang)
    if base == 'None':
        return {
            'java': 'void',
            'csharp': 'void',
            'go': '',
            'kotlin': 'Unit',
            'swift': 'Void',
            'typescript': 'void',
        }.get(target_lang)
    if base.startswith('list[') or base.startswith('List['):
        inner = normalized[normalized.find('[') + 1:-1] if '[' in normalized and normalized.endswith(']') else ''
        mapped_inner = _map_python_type(inner, target_lang) or (
            'Object' if target_lang == 'java'
            else 'object' if target_lang == 'csharp'
            else 'interface{}' if target_lang == 'go'
            else 'Any?' if target_lang == 'kotlin'
            else 'Any' if target_lang == 'swift'
            else 'any'
        )
        return {
            'java': f'List<{mapped_inner}>',
            'csharp': f'List<{mapped_inner}>',
            'go': f'[]{mapped_inner}',
            'kotlin': f'MutableList<{mapped_inner}>',
            'swift': f'[{mapped_inner}]',
            'typescript': f'{mapped_inner}[]',
        }.get(target_lang)
    if base.startswith('dict[') or base.startswith('Dict['):
        return {
            'java': 'Map<Object, Object>',
            'csharp': 'Dictionary<object, object>',
            'go': 'map[string]interface{}',
            'kotlin': 'MutableMap<Any?, Any?>',
            'swift': '[String: Any]',
            'typescript': 'Record<string, any>',
        }.get(target_lang)
    return {
        'java': 'Object',
        'csharp': 'object',
        'go': 'interface{}',
        'kotlin': 'Any?',
        'swift': 'Any',
        'typescript': 'any',
    }.get(target_lang)


def _default_return_literal(annotation, to_lang):
    normalized = (annotation or '').strip()
    if normalized in ('None', 'NoneType'):
        return ''
    if normalized == 'bool':
        return {
            'javascript': 'false',
            'typescript': 'false',
            'java': 'false',
            'csharp': 'false',
            'go': 'false',
            'rust': 'false',
            'php': 'false',
            'swift': 'false',
            'kotlin': 'false',
        }.get(to_lang, 'false')
    if normalized in ('int', 'float'):
        return '0'
    if normalized == 'str':
        return {
            'ruby': "''",
            'php': "''",
        }.get(to_lang, '""')
    if normalized.startswith('list[') or normalized.startswith('List['):
        return {
            'javascript': '[]',
            'typescript': '[]',
            'java': 'new ArrayList<>()',
            'csharp': 'new List<object>()',
            'go': 'nil',
            'rust': 'Vec::new()',
            'ruby': '[]',
            'php': '[]',
            'swift': '[]',
            'kotlin': 'mutableListOf()',
        }.get(to_lang, 'null')
    if normalized.startswith('dict[') or normalized.startswith('Dict['):
        return {
            'javascript': '{}',
            'typescript': '{}',
            'java': 'new HashMap<>()',
            'csharp': 'new Dictionary<object, object>()',
            'go': 'nil',
            'rust': 'std::collections::HashMap::new()',
            'ruby': '{}',
            'php': '[]',
            'swift': '[:]',
            'kotlin': 'mutableMapOf()',
        }.get(to_lang, 'null')
    if normalized:
        return {
            'java': 'null',
            'csharp': 'null',
            'go': 'nil',
            'kotlin': 'null',
            'swift': 'nil',
            'typescript': 'null',
            'javascript': 'null',
            'ruby': 'nil',
            'php': 'null',
        }.get(to_lang, 'null')
    return {
        'javascript': 'null',
        'typescript': 'null',
        'java': 'null',
        'csharp': 'null',
        'go': 'nil',
        'rust': '()',
        'ruby': 'nil',
        'php': 'null',
        'swift': 'nil',
        'kotlin': 'null',
    }.get(to_lang, 'null')


def _cpp_type_hint(annotation, default='int'):
    normalized = (annotation or '').strip().replace(' ', '')
    if normalized == 'bool':
        return 'bool'
    if normalized == 'str':
        return 'string'
    if normalized == 'float':
        return 'double'
    if normalized in ('None', 'NoneType'):
        return 'void'
    return default


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
            '#include <string>\n'
            'using namespace std;\n\n'
            f'int {name}({cpp_params}) {{\n'
            '    // TODO: implement\n'
            '    return 0;\n'
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


def _build_local_class_translation(class_info, to_lang):
    class_name = class_info['name']
    methods = class_info['methods']

    if to_lang == 'javascript':
        blocks = [f'class {class_name} {{']
        if not methods:
            blocks.append('  constructor() {}')
        for method in methods:
            params = ', '.join(param['name'] for param in method['params'])
            if method['name'] == '__init__':
                blocks.extend([
                    f'  constructor({params}) {{',
                    '    // TODO: implement',
                    '  }',
                ])
                continue
            return_value = _default_return_literal(method['return_annotation'], 'javascript')
            blocks.append(f'  {method["name"]}({params}) {{')
            blocks.append('    // TODO: implement')
            if return_value:
                blocks.append(f'    return {return_value};')
            blocks.append('  }')
        blocks.append('}')
        return '\n'.join(blocks) + '\n'

    if to_lang == 'typescript':
        blocks = [f'class {class_name} {{']
        if not methods:
            blocks.append('  constructor() {}')
        for method in methods:
            params = ', '.join(
                f'{param["name"]}: {_map_python_type(param["annotation"], "typescript") or "any"}'
                for param in method['params']
            )
            if method['name'] == '__init__':
                blocks.extend([
                    f'  constructor({params}) {{',
                    '    // TODO: implement',
                    '  }',
                ])
                continue
            return_type = _map_python_type(method['return_annotation'], 'typescript') or 'any'
            return_value = _default_return_literal(method['return_annotation'], 'typescript')
            blocks.append(f'  {method["name"]}({params}): {return_type} {{')
            blocks.append('    // TODO: implement')
            if return_value:
                blocks.append(f'    return {return_value};')
            blocks.append('  }')
        blocks.append('}')
        return '\n'.join(blocks) + '\n'

    if to_lang == 'java':
        blocks = ['import java.util.*;', '', f'public class {class_name} {{']
        for method in methods:
            params = ', '.join(
                f'{_map_python_type(param["annotation"], "java") or "Object"} {param["name"]}'
                for param in method['params']
            )
            if method['name'] == '__init__':
                blocks.extend([
                    f'    public {class_name}({params}) {{',
                    '        // TODO: implement',
                    '    }',
                ])
                continue
            return_type = _map_python_type(method['return_annotation'], 'java') or 'Object'
            return_value = _default_return_literal(method['return_annotation'], 'java')
            blocks.append(f'    public {return_type} {method["name"]}({params}) {{')
            blocks.append('        // TODO: implement')
            if return_value:
                blocks.append(f'        return {return_value};')
            blocks.append('    }')
        blocks.append('}')
        return '\n'.join(blocks) + '\n'

    if to_lang == 'csharp':
        blocks = ['using System;', 'using System.Collections.Generic;', '', f'public class {class_name}', '{']
        for method in methods:
            params = ', '.join(
                f'{_map_python_type(param["annotation"], "csharp") or "object"} {param["name"]}'
                for param in method['params']
            )
            if method['name'] == '__init__':
                blocks.extend([
                    f'    public {class_name}({params})',
                    '    {',
                    '        // TODO: implement',
                    '    }',
                ])
                continue
            return_type = _map_python_type(method['return_annotation'], 'csharp') or 'object'
            return_value = _default_return_literal(method['return_annotation'], 'csharp')
            blocks.append(f'    public {return_type} {method["name"]}({params})')
            blocks.append('    {')
            blocks.append('        // TODO: implement')
            if return_value:
                blocks.append(f'        return {return_value};')
            blocks.append('    }')
        blocks.append('}')
        return '\n'.join(blocks) + '\n'

    if to_lang == 'go':
        blocks = ['package main', '', f'type {class_name} struct {{', '}', '']
        for method in methods:
            params = ', '.join(
                f'{param["name"]} {_map_python_type(param["annotation"], "go") or "interface{}"}'
                for param in method['params']
            )
            if method['name'] == '__init__':
                blocks.extend([
                    f'func New{class_name}({params}) *{class_name} {{',
                    '    // TODO: implement',
                    f'    return &{class_name}{{}}',
                    '}',
                    '',
                ])
                continue
            return_type = _map_python_type(method['return_annotation'], 'go')
            signature = f'func (s *{class_name}) {method["name"].title()}({params})'
            if return_type:
                signature += f' {return_type}'
            blocks.append(signature + ' {')
            blocks.append('    // TODO: implement')
            return_value = _default_return_literal(method['return_annotation'], 'go')
            if return_value:
                blocks.append(f'    return {return_value}')
            blocks.append('}')
            blocks.append('')
        blocks.append('func main() {}')
        return '\n'.join(blocks).rstrip() + '\n'

    if to_lang == 'ruby':
        blocks = [f'class {class_name}']
        for method in methods:
            params = ', '.join(param['name'] for param in method['params'])
            method_name = 'initialize' if method['name'] == '__init__' else method['name']
            blocks.append(f'  def {method_name}({params})')
            blocks.append('    # TODO: implement')
            return_value = _default_return_literal(method['return_annotation'], 'ruby')
            if return_value:
                blocks.append(f'    {return_value}')
            blocks.append('  end')
            blocks.append('')
        blocks.append('end')
        return '\n'.join(blocks).rstrip() + '\n'

    if to_lang == 'php':
        blocks = ['<?php', '', f'class {class_name}', '{']
        for method in methods:
            params = ', '.join(f'${param["name"]}' for param in method['params'])
            method_name = '__construct' if method['name'] == '__init__' else method['name']
            blocks.append(f'    public function {method_name}({params}) {{')
            blocks.append('        // TODO: implement')
            return_value = _default_return_literal(method['return_annotation'], 'php')
            if return_value:
                blocks.append(f'        return {return_value};')
            blocks.append('    }')
            blocks.append('')
        blocks.append('}')
        return '\n'.join(blocks).rstrip() + '\n'

    if to_lang == 'swift':
        blocks = ['import Foundation', '', f'class {class_name} {{']
        for method in methods:
            params = ', '.join(
                f'{param["name"]}: {_map_python_type(param["annotation"], "swift") or "Any"}'
                for param in method['params']
            )
            if method['name'] == '__init__':
                blocks.extend([
                    f'    init({params}) {{',
                    '        // TODO: implement',
                    '    }',
                ])
                continue
            return_type = _map_python_type(method['return_annotation'], 'swift') or 'Any'
            blocks.append(f'    func {method["name"]}({params}) -> {return_type} {{')
            blocks.append('        // TODO: implement')
            return_value = _default_return_literal(method['return_annotation'], 'swift')
            if return_value:
                blocks.append(f'        return {return_value}')
            blocks.append('    }')
        blocks.append('}')
        return '\n'.join(blocks) + '\n'

    if to_lang == 'kotlin':
        constructor_method = next((method for method in methods if method['name'] == '__init__'), None)
        constructor_params = ''
        if constructor_method:
            constructor_params = ', '.join(
                f'private val {param["name"]}: {_map_python_type(param["annotation"], "kotlin") or "Any?"}'
                for param in constructor_method['params']
            )
        blocks = [f'class {class_name}({constructor_params}) {{']
        for method in methods:
            if method['name'] == '__init__':
                continue
            params = ', '.join(
                f'{param["name"]}: {_map_python_type(param["annotation"], "kotlin") or "Any?"}'
                for param in method['params']
            )
            return_type = _map_python_type(method['return_annotation'], 'kotlin') or 'Any?'
            blocks.append(f'    fun {method["name"]}({params}): {return_type} {{')
            blocks.append('        // TODO: implement')
            return_value = _default_return_literal(method['return_annotation'], 'kotlin')
            if return_value:
                blocks.append(f'        return {return_value}')
            blocks.append('    }')
        blocks.append('}')
        return '\n'.join(blocks) + '\n'

    if to_lang == 'cpp':
        blocks = ['#include <iostream>', '#include <vector>', '#include <string>', 'using namespace std;', '', f'class {class_name} {{', 'public:']
        for method in methods:
            params = ', '.join(
                f'{_cpp_type_hint(param["annotation"])} {param["name"]}'
                for param in method['params']
            )
            if method['name'] == '__init__':
                blocks.extend([
                    f'    {class_name}({params}) {{',
                    '        // TODO: implement',
                    '    }',
                ])
                continue
            return_type = _cpp_type_hint(method['return_annotation'])
            return_value = _default_return_literal(method['return_annotation'], 'cpp')
            if return_value == 'null':
                return_value = '0'
            blocks.append(f'    {return_type} {method["name"]}({params}) {{')
            blocks.append('        // TODO: implement')
            if return_type != 'void':
                blocks.append(f'        return {return_value or 0};')
            blocks.append('    }')
        blocks.extend(['};', '', 'int main() {', '    return 0;', '}'])
        return '\n'.join(blocks) + '\n'

    if to_lang == 'c':
        return (
            '#include <stdio.h>\n\n'
            f'/* TODO: translate Python class {class_name} into a C struct and related functions. */\n'
            'int main(void) {\n'
            '    return 0;\n'
            '}\n'
        )

    if to_lang == 'rust':
        blocks = [f'struct {class_name} {{', '}', '']
        blocks.append(f'impl {class_name} {{')
        for method in methods:
            params = ', '.join(f'{param["name"]}: impl Sized' for param in method['params'])
            if method['name'] == '__init__':
                blocks.extend([
                    f'    fn new({params}) -> Self {{',
                    '        // TODO: implement',
                    f'        {class_name} {{}}',
                    '    }',
                ])
                continue
            param_list = ', '.join(filter(None, ['&mut self', params]))
            blocks.append(f'    fn {method["name"]}({param_list}) {{')
            blocks.append('        // TODO: implement')
            blocks.append('    }')
        blocks.extend(['}', '', 'fn main() {}'])
        return '\n'.join(blocks) + '\n'

    if to_lang == 'bash':
        return (
            '#!/usr/bin/env bash\n'
            f'# TODO: translate Python class {class_name} into Bash functions.\n'
        )

    if to_lang == 'sql':
        return (
            f'-- SQL translation is not available for Python class starter code: {class_name}\n'
        )

    return None


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
        class_stub = _extract_simple_python_class_stub(code)
        if class_stub:
            translated = _build_local_class_translation(class_stub, to_lang)
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

def _simulate_execution_with_ai(language, code, runtime_status=None):
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
            'exit_code': int(result.get('exit_code', 0)),
            'execution_mode': 'simulated',
            'warning': runtime_status or 'Local runtime is unavailable. Result generated via AI simulation.',
        })
    except Exception as e:
        return jsonify({
            'stdout': '',
            'stderr': f'AI Simulation Failed: {str(e)}',
            'exit_code': 1,
            'execution_mode': 'simulated',
            'warning': runtime_status or 'Local runtime is unavailable.',
        })

