import os
import shutil
import subprocess
import tempfile

import config


def run(code: str, stdin: str = '', timeout: int = config.CODE_TIMEOUT) -> dict:
    tmpdir = tempfile.mkdtemp(prefix='engiprep_js_', dir=config.RUNNER_TEMP_DIR)
    filepath = os.path.join(tmpdir, 'solution.js')
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)
        result = subprocess.run(
            ['node', filepath],
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
            'stderr': f'Timeout: execution exceeded {timeout}s',
            'exit_code': 124,
        }
    except FileNotFoundError:
        return {
            'status': 'runtime_error',
            'stdout': '',
            'stderr': 'Node.js not found. Make sure node is installed.',
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
