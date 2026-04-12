import ast
import os
import subprocess
import sys
import tempfile
import shutil
import uuid

from flask import Blueprint, request, jsonify

import config
from services import ai

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


def _native_binary_path(dir_path, stem='solution'):
    suffix = '.exe' if os.name == 'nt' else ''
    return os.path.join(dir_path, stem + suffix)


def _create_run_workspace():
    """Create a per-run workspace without tempfile.mkdtemp's restrictive permissions."""
    path = os.path.join(config.RUNNER_TEMP_DIR, f'codeprep_run_{uuid.uuid4().hex[:12]}')
    os.mkdir(path)
    return path


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


def _node_supports_strip_types():
    global _node_strip_types_support
    if _node_strip_types_support is not None:
        return _node_strip_types_support

    node = _resolve_node_runner()
    if not node:
        _node_strip_types_support = False
        return False

    try:
        result = subprocess.run(
            [node, '--experimental-strip-types', '-e', 'console.log("ok")'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        _node_strip_types_support = result.returncode == 0
    except Exception:
        _node_strip_types_support = False
    return _node_strip_types_support


def _typescript_run_command(path):
    try:
        return [_resolve_typescript_runner(), '--transpile-only', path]
    except FileNotFoundError:
        node = _resolve_node_runner()
        if node and _node_supports_strip_types():
            return [node, '--experimental-strip-types', path]
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
        'run': lambda path: [_require_tool('node'), path],
    },
    'typescript': {
        'extension': '.ts',
        'compile': None,
        'run': _typescript_run_command,
    },
    'java': {
        'extension': '.java',
        'compile': lambda path, dir: [_require_tool('javac'), path],
        'run': lambda path, dir: [_require_tool('java'), '-cp', dir, _java_class_name(path)],
    },
    'c': {
        'extension': '.c',
        'compile': lambda path, dir: [_require_tool('gcc'), '-o', _native_binary_path(dir), path, '-lm'],
        'run': lambda path, dir: [_native_binary_path(dir)],
    },
    'cpp': {
        'extension': '.cpp',
        'compile': lambda path, dir: [_require_tool('g++'), '-o', _native_binary_path(dir), path, '-lm', '-lstdc++'],
        'run': lambda path, dir: [_native_binary_path(dir)],
    },
    'go': {
        'extension': '.go',
        'compile': None,
        'run': lambda path: [_require_tool('go'), 'run', path],
    },
    'rust': {
        'extension': '.rs',
        'compile': lambda path, dir: [_require_tool('rustc'), '-o', _native_binary_path(dir), path],
        'run': lambda path, dir: [_native_binary_path(dir)],
    },
    'ruby': {
        'extension': '.rb',
        'compile': None,
        'run': lambda path: [_require_tool('ruby'), path],
    },
    'php': {
        'extension': '.php',
        'compile': None,
        'run': lambda path: [_require_tool('php'), path],
    },
    'swift': {
        'extension': '.swift',
        'compile': None,
        'run': lambda path: [_require_tool('swift'), path],
    },
    'kotlin': {
        'extension': '.kt',
        'compile': lambda path, dir: [_require_tool('kotlinc'), path, '-include-runtime', '-d', os.path.join(dir, 'out.jar')],
        'run': lambda path, dir: [_require_tool('java'), '-jar', os.path.join(dir, 'out.jar')],
    },
    'csharp': {
        'extension': '.cs',
        'compile': None,
        'run': lambda path: [_require_tool('dotnet-script'), path],
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
    if _resolve_tool_path(cmd):
        return True
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
        return True, f'Using {sys.executable}'
    if language == 'javascript':
        node = _resolve_node_runner()
        if node:
            return True, f'Using {node}'
        return False, 'Node.js is required for JavaScript execution.'
    if language == 'typescript':
        try:
            runner = _resolve_typescript_runner()
            return True, f'Using {runner}'
        except FileNotFoundError:
            if _node_supports_strip_types():
                return True, 'Using Node.js built-in TypeScript stripping.'
            if _check_tool_available('node'):
                return True, 'Using Node fallback for JS-compatible TypeScript code.'
            return False, 'TypeScript requires ts-node or Node.js to be installed.'
    if language == 'java':
        javac = _resolve_tool_path('javac')
        java = _resolve_tool_path('java')
        if javac and java:
            return True, f'Using {javac} and {java}'
        return False, 'Java requires both javac and java.'
    if language == 'c':
        gcc = _resolve_tool_path('gcc')
        if gcc:
            return True, f'Using {gcc}'
        return False, 'C requires gcc.'
    if language == 'cpp':
        gpp = _resolve_tool_path('g++')
        if gpp:
            return True, f'Using {gpp}'
        return False, 'C++ requires g++.'
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
        kotlinc = _resolve_tool_path('kotlinc')
        java = _resolve_tool_path('java')
        if kotlinc and java:
            return True, f'Using {kotlinc} and {java}'
        return False, 'Kotlin requires kotlinc and java.'
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
    csharp_params = ', '.join(f'object {param}' for param in params) or ''
    php_params = ', '.join(f'${param}' for param in params)
    ruby_params = ', '.join(params)
    go_params = ', '.join(f'{param} interface{{}}' for param in params)
    kotlin_params = ', '.join(f'{param}: Any?' for param in params)
    swift_params = ', '.join(f'_{param}: Any' for param in params)
    async_prefix = 'async ' if function_info['is_async'] and to_lang in ('javascript', 'typescript') else ''
    cpp_params = ', '.join(f'int {param}' for param in params)

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

    profile = _language_execution_profile(language)
    if not profile['local_available']:
        if profile['supports_simulation']:
            return _simulate_execution_with_ai(language, user_code, profile['status'])
        return jsonify({
            'stdout': '',
            'stderr': profile['status'],
            'exit_code': 1,
            'execution_mode': 'unavailable',
        })

    # For SQL, use a special handler
    if language == 'sql':
        return _run_sql(user_code)

    # Create temp directory for compiled languages
    tmpdir = _create_run_workspace()
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
                        'execution_mode': 'local',
                    })
            except subprocess.TimeoutExpired:
                return jsonify({
                    'stdout': '',
                    'stderr': f'Compilation timeout (>{config.CODE_TIMEOUT}s)',
                    'exit_code': 1,
                    'execution_mode': 'local',
                })
            except FileNotFoundError as e:
                return jsonify({
                    'stdout': '',
                    'stderr': f'Compiler not found. Make sure the {language} compiler is installed.\n{e}',
                    'exit_code': 1,
                    'execution_mode': 'local',
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
                'execution_mode': 'local',
            })
        except subprocess.TimeoutExpired:
            return jsonify({
                'stdout': '',
                'stderr': f'Timeout: code took too long (>{config.CODE_TIMEOUT}s)',
                'exit_code': 1,
                'execution_mode': 'local',
            })
        except FileNotFoundError as e:
            return jsonify({
                'stdout': '',
                'stderr': f'Runtime not found. Make sure {language} is installed on the system.\n{e}',
                'exit_code': 1,
                'execution_mode': 'local',
            })

    except Exception as e:
        return jsonify({
            'stdout': '',
            'stderr': f'Runner error: {e}',
            'exit_code': 1,
            'execution_mode': 'local',
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
                'execution_mode': 'local',
            })
        except FileNotFoundError:
            # Fallback: try python's sqlite3 module
            return _run_sql_python(user_code)
        except subprocess.TimeoutExpired:
            return jsonify({
                'stdout': '',
                'stderr': f'Timeout: SQL took too long (>{config.CODE_TIMEOUT}s)',
                'exit_code': 1,
                'execution_mode': 'local',
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
            'execution_mode': 'local',
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            'stdout': '',
            'stderr': f'Timeout: SQL took too long (>{config.CODE_TIMEOUT}s)',
            'exit_code': 1,
            'execution_mode': 'local',
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
        class_stub = _extract_simple_python_class_stub(code)
        if class_stub:
            translated = _build_local_class_translation(class_stub, to_lang)
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
            class_stub = _extract_simple_python_class_stub(code)
            if class_stub:
                translated = _build_local_class_translation(class_stub, to_lang)
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
            'available': available,
            'execution_mode': 'local' if available else 'simulated',
            'supports_simulation': key != 'python',
            'status': status if available else f'{status} AI cloud simulation is available as a fallback.',
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

