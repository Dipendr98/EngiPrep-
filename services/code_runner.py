import json
import subprocess
import sys
import tempfile
import os

import config


HARNESS_TEMPLATE = '''
import asyncio
import json
import sys

# ── User code ──
__USER_CODE__

# ── Test harness ──
_fn = __FUNCTION_NAME_REPR__
_tests = json.loads(__TEST_CASES_JSON_REPR__)

def _maybe_await(_value):
    if asyncio.iscoroutine(_value):
        return asyncio.run(_value)
    return _value

def _resolve_refs(_value, _scope):
    if isinstance(_value, dict) and "__ref__" in _value:
        return _scope[_value["__ref__"]]
    if isinstance(_value, list):
        return [_resolve_refs(_item, _scope) for _item in _value]
    if isinstance(_value, dict):
        return {_key: _resolve_refs(_item, _scope) for _key, _item in _value.items()}
    return _value

_results = []
for _i, _tc in enumerate(_tests):
    _label = _tc.get("label")
    _scope = dict(globals())
    _setup = _tc.get("setup_code")
    if _setup:
        exec(_setup, _scope, _scope)
    _inp = _resolve_refs(_tc.get("input", {}), _scope)
    _args = _resolve_refs(_tc.get("args"), _scope)
    _kwargs = _resolve_refs(_tc.get("kwargs"), _scope)
    _exp = _resolve_refs(_tc.get("expected"), _scope)
    _exp_err = _tc.get("expected_error")
    _callable = _tc.get("function_name") or _fn
    try:
        if _args is not None:
            _actual = _maybe_await(_scope[_callable](*_args))
            _call = f"{_callable}({', '.join(repr(_arg) for _arg in _args)})"
        elif _kwargs is not None:
            _actual = _maybe_await(_scope[_callable](**_kwargs))
            _call = _callable + "(" + ", ".join(f"{_k}={repr(_v)}" for _k, _v in _kwargs.items()) + ")"
        else:
            _actual = _maybe_await(_scope[_callable](**_inp))
            _call = _callable + "(" + ", ".join(f"{_k}={repr(_v)}" for _k, _v in _inp.items()) + ")"
        _passed = _exp_err is None and _actual == _exp
        _results.append({"index": _i, "label": _label, "input": _inp, "expected": _exp, "actual": _actual, "passed": _passed, "error": None, "call": _call})
    except Exception as _e:
        _err = f"{type(_e).__name__}: {_e}"
        _passed = _exp_err is not None and _exp_err.lower() in _err.lower()
        _results.append({"index": _i, "label": _label, "input": _inp, "expected": _exp, "actual": None, "passed": _passed, "error": None if _passed else _err, "expected_error": _exp_err, "call": _callable})

print("__RESULTS__" + json.dumps(_results, default=str))
'''


CLASS_HARNESS_TEMPLATE = '''
import asyncio
import json
import sys
import time

# ── User code ──
__USER_CODE__

# ── Test harness ──
_class_name = __CLASS_NAME_REPR__
_tests = json.loads(__TEST_CASES_JSON_REPR__)

def _maybe_await(_value):
    if asyncio.iscoroutine(_value):
        return asyncio.run(_value)
    return _value

def _resolve_refs(_value, _scope):
    if isinstance(_value, dict) and "__ref__" in _value:
        return _scope[_value["__ref__"]]
    if isinstance(_value, list):
        return [_resolve_refs(_item, _scope) for _item in _value]
    if isinstance(_value, dict):
        return {_key: _resolve_refs(_item, _scope) for _key, _item in _value.items()}
    return _value

def _format_arg(_value):
    if isinstance(_value, dict) and "__ref__" in _value:
        return _value["__ref__"]
    return repr(_value)

_results = []
for _i, _tc in enumerate(_tests):
    _label = _tc.get("label")
    _scope = dict(globals())
    _setup = _tc.get("setup_code")
    if _setup:
        exec(_setup, _scope, _scope)

    _init_args = _resolve_refs(_tc.get("init_args", []), _scope)
    _init_kwargs = _resolve_refs(_tc.get("init_kwargs", {}), _scope)
    _raw_init_args = _tc.get("init_args", [])
    _raw_init_kwargs = _tc.get("init_kwargs", {})

    try:
        _obj = globals()[_class_name](*_init_args, **_init_kwargs)
        _scope["obj"] = _obj
    except Exception as _e:
        _err = f"{type(_e).__name__}: {_e}"
        _results.append({
            "index": _i,
            "step": 0,
            "label": _label,
            "expected": None,
            "actual": None,
            "passed": False,
            "error": _err,
            "call": f"{_class_name}(...)",
        })
        continue

    _ops = _tc.get("ops", [])
    _op_args = _tc.get("op_args", [])
    _expected = _tc.get("expected", [])
    _expected_errors = _tc.get("expected_errors", [None] * len(_ops))
    _save_as = _tc.get("save_as", [None] * len(_ops))
    _compare = _tc.get("compare", [True] * len(_ops))
    _case_failed = False

    for _step_index, _op in enumerate(_ops):
        _raw_args = _op_args[_step_index] if _step_index < len(_op_args) else []
        _resolved_args = _resolve_refs(_raw_args, _scope)
        _exp = _resolve_refs(_expected[_step_index], _scope) if _step_index < len(_expected) else None
        _exp_err = _expected_errors[_step_index] if _step_index < len(_expected_errors) else None
        _should_compare = _compare[_step_index] if _step_index < len(_compare) else True

        if _init_kwargs:
            _init_display = ", ".join(
                [*[_format_arg(_arg) for _arg in _raw_init_args], *[f"{_key}={_format_arg(_value)}" for _key, _value in _raw_init_kwargs.items()]]
            )
        else:
            _init_display = ", ".join(_format_arg(_arg) for _arg in _raw_init_args)

        if _op == "__sleep__":
            _call = f"time.sleep({_resolved_args[0]!r})"
        elif _op == "__eval__":
            _call = str(_raw_args[0])
        else:
            _call = f"{_class_name}({_init_display}) :: {_op}({', '.join(_format_arg(_arg) for _arg in _raw_args)})"

        try:
            if _op == "__sleep__":
                time.sleep(_resolved_args[0])
                _actual = None
            elif _op == "__eval__":
                _actual = _maybe_await(eval(_raw_args[0], _scope, _scope))
            else:
                _actual = _maybe_await(getattr(_obj, _op)(*_resolved_args))
            _passed = _exp_err is None and (_actual == _exp if _should_compare else True)
            _error = None
            _save_name = _save_as[_step_index] if _step_index < len(_save_as) else None
            if _save_name:
                _scope[_save_name] = _actual
        except Exception as _e:
            _actual = None
            _err = f"{type(_e).__name__}: {_e}"
            _passed = _exp_err is not None and _exp_err.lower() in _err.lower()
            _error = None if _passed else _err

        _results.append({
            "index": _i,
            "step": _step_index + 1,
            "label": _label,
            "expected": _exp,
            "actual": _actual,
            "passed": _passed,
            "error": _error,
            "expected_error": _exp_err,
            "call": _call,
        })
        if not _passed:
            _case_failed = True
            break

    if _case_failed:
        continue

print("__RESULTS__" + json.dumps(_results, default=str))
'''


def run(user_code: str, function_name: str, test_cases: list, timeout: int = config.CODE_TIMEOUT) -> dict:
    """
    Execute user_code against test_cases by calling function_name.

    Returns {
        "success": bool,
        "results": [{"index", "input", "expected", "actual", "passed", "error"}],
        "error": str or None  (top-level error like syntax/timeout)
    }
    """
    harness = (
        HARNESS_TEMPLATE
        .replace('__USER_CODE__', user_code)
        .replace('__FUNCTION_NAME_REPR__', repr(function_name))
        .replace('__TEST_CASES_JSON_REPR__', repr(json.dumps(test_cases)))
    )

    return _run_harness(harness, timeout=timeout)


def run_class(user_code: str, class_name: str, test_cases: list, timeout: int = config.CODE_TIMEOUT) -> dict:
    """Execute user_code against class-style test cases."""
    harness = (
        CLASS_HARNESS_TEMPLATE
        .replace('__USER_CODE__', user_code)
        .replace('__CLASS_NAME_REPR__', repr(class_name))
        .replace('__TEST_CASES_JSON_REPR__', repr(json.dumps(test_cases)))
    )

    return _run_harness(harness, timeout=timeout)


def _run_harness(harness: str, timeout: int = config.CODE_TIMEOUT) -> dict:
    """Execute a generated harness file and parse structured results."""

    fd, path = tempfile.mkstemp(suffix='.py', prefix='codeprep_')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(harness)

        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        stdout = result.stdout
        stderr = result.stderr

        if result.returncode != 0 and '__RESULTS__' not in stdout:
            error_msg = stderr.strip() if stderr.strip() else f'Process exited with code {result.returncode}'
            lines = error_msg.split('\n')
            cleaned = _clean_traceback(lines)
            return {
                'success': False,
                'results': [],
                'error': cleaned,
            }

        if '__RESULTS__' in stdout:
            json_str = stdout.split('__RESULTS__', 1)[1].strip()
            results = json.loads(json_str)
            return {
                'success': True,
                'results': results,
                'error': None,
            }

        return {
            'success': False,
            'results': [],
            'error': stderr.strip() or 'No output from test harness',
        }

    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'results': [],
            'error': f'Timeout: code took too long to execute (>{timeout}s)',
        }
    except Exception as e:
        return {
            'success': False,
            'results': [],
            'error': f'Runner error: {e}',
        }
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _clean_traceback(lines: list) -> str:
    """Strip temp file paths from traceback to show cleaner errors."""
    cleaned = []
    for line in lines:
        if 'codeprep_' in line and 'File "' in line:
            line = line.replace(line.split('"')[1], '<your code>')
        cleaned.append(line)
    return '\n'.join(cleaned)


def format_results_for_context(run_result: dict, function_name: str) -> str:
    """Format run results into a text summary to inject into conversation context."""
    if run_result['error'] and not run_result['results']:
        return f"[TEST RESULTS]\nCode execution failed:\n{run_result['error']}"

    results = run_result['results']
    passed = sum(1 for r in results if r['passed'])
    total = len(results)

    lines = [f"[TEST RESULTS]", f"Executed against {total} test cases: {passed}/{total} passed."]
    for r in results:
        label_prefix = f"{r['label']} :: " if r.get('label') else ''
        call = r.get('call') or function_name
        if r.get('step'):
            call = f"step {r['step']} {call}"
        if r['passed']:
            if r.get('expected_error'):
                lines.append(f"  PASS: {label_prefix}{call} -> raised {r['expected_error']}")
            else:
                lines.append(f"  PASS: {label_prefix}{call} -> {repr(r['actual'])}")
        elif r['error']:
            lines.append(f"  FAIL: {label_prefix}{call} -> {r['error']}")
        elif r.get('expected_error'):
            lines.append(f"  FAIL: {label_prefix}{call} -> expected error containing {repr(r['expected_error'])}")
        else:
            lines.append(f"  FAIL: {label_prefix}{call} -> expected {repr(r['expected'])}, got {repr(r['actual'])}")

    return '\n'.join(lines)
