import os
import subprocess
import sys
import tempfile

from flask import Blueprint, request, jsonify

import config

bp = Blueprint('code', __name__)


@bp.route('/api/run', methods=['POST'])
def run_code():
    data = request.json or {}
    user_code = data.get('code', '')
    if not user_code.strip():
        return jsonify({'error': 'No code provided'}), 400

    fd, path = tempfile.mkstemp(suffix='.py', prefix='codeprep_run_')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(user_code)
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True, timeout=config.CODE_TIMEOUT,
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
    except Exception as e:
        return jsonify({
            'stdout': '',
            'stderr': f'Runner error: {e}',
            'exit_code': 1,
        })
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
