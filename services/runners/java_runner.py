import os
import re
import shutil
import subprocess
import tempfile

import config


def _extract_class_name(code: str) -> str:
    match = re.search(r'public\s+class\s+(\w+)', code)
    return match.group(1) if match else 'Solution'


def run(code: str, stdin: str = '', timeout: int = config.CODE_TIMEOUT) -> dict:
    tmpdir = tempfile.mkdtemp(prefix='engiprep_java_', dir=config.RUNNER_TEMP_DIR)
    class_name = _extract_class_name(code)
    filepath = os.path.join(tmpdir, class_name + '.java')
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)

        # Compile
        compile_result = subprocess.run(
            ['javac', filepath],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tmpdir,
        )
        if compile_result.returncode != 0:
            return {
                'status': 'compilation_error',
                'stdout': compile_result.stdout,
                'stderr': compile_result.stderr,
                'exit_code': compile_result.returncode,
            }

        # Run
        result = subprocess.run(
            ['java', '-cp', tmpdir, class_name],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tmpdir,
        )
        status = 'success' if result.returncode == 0 else 'runtime_error'
        return {
            'status': status,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'exit_code': result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            'status': 'timeout',
            'stdout': '',
            'stderr': f'Timeout: exceeded {timeout}s',
            'exit_code': 124,
        }
    except FileNotFoundError:
        return {
            'status': 'compilation_error',
            'stdout': '',
            'stderr': 'javac/java not found. Make sure OpenJDK is installed.',
            'exit_code': 1,
        }
    except Exception as exc:
        return {
            'status': 'runtime_error',
            'stdout': '',
            'stderr': str(exc),
            'exit_code': 1,
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
