"""
Execution dispatcher for supported languages.
Routes code execution requests to the correct language runner.
"""
import config
from services.runners import (
    c_runner,
    cpp_runner,
    java_runner,
    javascript_runner,
    python_runner,
    sql_runner,
)

SUPPORTED_LANGUAGES = {
    'python': python_runner,
    'javascript': javascript_runner,
    'c': c_runner,
    'cpp': cpp_runner,
    'java': java_runner,
    'sql': sql_runner,
}

LANGUAGE_LABELS = {
    'python': 'Python',
    'javascript': 'JavaScript',
    'c': 'C',
    'cpp': 'C++',
    'java': 'Java',
    'sql': 'SQL',
}


def dispatch(code: str, language: str, stdin: str = '', timeout: int = config.CODE_TIMEOUT) -> dict:
    """
    Execute code in the given language.

    Returns:
        {
            'status': 'success' | 'compilation_error' | 'runtime_error' | 'timeout' | 'unsupported_language',
            'stdout': str,
            'stderr': str,
            'exit_code': int,
        }
    """
    runner = SUPPORTED_LANGUAGES.get(language)
    if not runner:
        return {
            'status': 'unsupported_language',
            'stdout': '',
            'stderr': f'Unsupported language: {language!r}. Supported: {", ".join(SUPPORTED_LANGUAGES)}',
            'exit_code': 1,
        }
    return runner.run(code, stdin=stdin, timeout=timeout)
