import json
import os
import subprocess
import sys
import tempfile
import uuid
import time
from glob import glob

import yaml
import requests as http_requests  # named to avoid conflict with flask.request
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from openai import OpenAI
import code_runner

load_dotenv()

app = Flask(__name__)

SESSIONS_DIR = os.path.join(os.path.dirname(__file__), 'user_data', 'sessions')
os.makedirs(SESSIONS_DIR, exist_ok=True)

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), 'prompts')

def _load_prompt(filename):
    with open(os.path.join(_PROMPTS_DIR, filename), encoding='utf-8') as f:
        return f.read()

SYSTEM_PROMPT = _load_prompt('interviewer.txt')
SESSION_CONFIG = _load_prompt('session_config.txt')
FOCUS_PROMPTS = json.loads(_load_prompt('focus_prompts.json'))
TEST_GEN_PROMPT = _load_prompt('test_generation.txt')
VOICE_SYSTEM_PROMPT = _load_prompt('voice_interviewer.txt')
TUTOR_SYSTEM_PROMPT = _load_prompt('tutor.txt')


def get_client():
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def load_session(session_id):
    path = os.path.join(SESSIONS_DIR, f'{session_id}.json')
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return None


def save_session(session):
    path = os.path.join(SESSIONS_DIR, f'{session["id"]}.json')
    with open(path, 'w') as f:
        json.dump(session, f, indent=2)


@app.route('/')
def index():
    return render_template('index.html')


PROBLEMS_DIR = os.path.join(os.path.dirname(__file__), 'problems')


def load_problems():
    problems = []
    for path in sorted(glob(os.path.join(PROBLEMS_DIR, '*.yaml'))):
        with open(path) as f:
            problems.append(yaml.safe_load(f))
    return problems


def get_problem_by_id(problem_id):
    if problem_id is None:
        return None

    for problem in load_problems():
        if problem.get('id') == problem_id:
            return problem
    return None


def serialize_problem_for_list(problem):
    return {
        'id': problem['id'],
        'title': problem['title'],
        'category': problem['category'],
        'difficulty': problem['difficulty'],
        'summary': problem.get('summary', ''),
        'starter_code': problem.get('starter_code', ''),
        'key_skills': problem.get('key_skills', []),
    }


def build_problem_block(problem):
    follow_ups = "\n".join(f"- {f}" for f in problem.get('follow_ups', []))
    constraints = "\n".join(f"- {c}" for c in problem.get('constraints', []))
    examples = []
    for example in problem.get('examples', [])[:2]:
        examples.append(
            "Input:\n"
            f"{example.get('input', '').strip()}\n\n"
            "Output:\n"
            f"{example.get('output', '').strip()}"
        )
    examples_block = "\n\n".join(examples)

    interface_block = ""
    if problem.get('starter_code'):
        interface_block = (
            "\n\nRequired interface (the candidate's code should match this shape):"
            f"\n```python\n{problem['starter_code']}\n```"
        )

    return (
        f"\n\nYou MUST use this specific problem for the interview:"
        f"\n\nTitle: {problem['title']}"
        f"\nDifficulty: {problem['difficulty']}"
        f"\nCategory: {problem['category']}"
        f"\n\nScenario:\n{problem.get('scenario', '').strip()}"
        f"\n\nProblem:\n{problem['description']}"
        f"\n\nConstraints:\n{constraints or '- No additional constraints provided.'}"
        f"{interface_block}"
        f"\n\nExample cases:\n{examples_block or 'Use the problem statement and interface above.'}"
        f"\n\nSuggested follow-ups (use if the candidate is doing well):\n{follow_ups or '- No suggested follow-ups.'}"
        f"\n\nPresent this problem in your own words as a natural interviewer would. Do not read it verbatim."
        f"\nBe explicit about the required function or class name if the candidate asks."
    )


def run_pre_canned_tests(user_code, problem):
    test_cases = problem.get('test_cases') or []
    if not test_cases:
        return None

    test_type = problem.get('test_type', 'function')
    if test_type == 'class':
        class_name = problem.get('class_name')
        if not class_name:
            return None
        run_result = code_runner.run_class(user_code, class_name, test_cases)
        return {
            'test_type': 'class',
            'display_name': class_name,
            'success': run_result['success'],
            'results': run_result['results'],
            'error': run_result['error'],
        }

    function_name = problem.get('function_name')
    if not function_name:
        return None

    run_result = code_runner.run(user_code, function_name, test_cases)
    return {
        'test_type': 'function',
        'display_name': function_name,
        'success': run_result['success'],
        'results': run_result['results'],
        'error': run_result['error'],
    }


def run_tests_for_session(session, user_code, client):
    problem = get_problem_by_id(session.get('problem_id'))
    if problem:
        pre_canned = run_pre_canned_tests(user_code, problem)
        if pre_canned is not None:
            return pre_canned

    fn_name, test_cases = generate_test_cases(client, session['messages'])
    if not fn_name or not test_cases:
        return None

    run_result = code_runner.run(user_code, fn_name, test_cases)
    return {
        'test_type': 'function',
        'display_name': fn_name,
        'success': run_result['success'],
        'results': run_result['results'],
        'error': run_result['error'],
    }


@app.route('/api/check-key')
def check_key():
    client = get_client()
    return jsonify({'has_key': client is not None})


@app.route('/api/problems')
def list_problems():
    problems = load_problems()
    category = request.args.get('category')
    if category:
        problems = [p for p in problems if p['category'] == category]
    return jsonify([serialize_problem_for_list(problem) for problem in problems])


@app.route('/api/problems/<int:problem_id>')
def get_problem(problem_id):
    problem = get_problem_by_id(problem_id)
    if not problem:
        return jsonify({'error': 'Problem not found'}), 404
    return jsonify({
        'id': problem['id'],
        'title': problem['title'],
        'category': problem['category'],
        'difficulty': problem['difficulty'],
        'summary': problem.get('summary', ''),
        'description': problem.get('description', ''),
        'scenario': problem.get('scenario', ''),
        'constraints': problem.get('constraints', []),
        'examples': problem.get('examples', []),
        'key_skills': problem.get('key_skills', []),
        'follow_ups': problem.get('follow_ups', []),
        'starter_code': problem.get('starter_code', ''),
        'explanation': problem.get('explanation', ''),
        'references': problem.get('references', []),
    })


@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    sessions = []
    for fname in sorted(os.listdir(SESSIONS_DIR), reverse=True):
        if fname.endswith('.json'):
            with open(os.path.join(SESSIONS_DIR, fname), 'r') as f:
                s = json.load(f)
                sessions.append({
                    'id': s['id'],
                    'focus': s.get('focus', 'general'),
                    'problem_id': s.get('problem_id'),
                    'problem_title': s.get('problem_title'),
                    'started_at': s['started_at'],
                    'message_count': len([m for m in s['messages'] if m['role'] != 'system']),
                    'rating': s.get('rating'),
                    'status': s.get('status', 'active'),
                    'mode': s.get('mode', 'text'),
                })
    return jsonify(sessions)


@app.route('/api/sessions', methods=['POST'])
def create_session():
    client = get_client()
    if not client:
        return jsonify({'error': 'OPENAI_API_KEY not set. Run: export OPENAI_API_KEY=your_key'}), 400

    data = request.json or {}
    focus = data.get('focus', 'general')
    mode = data.get('mode', 'text')
    problem_id = data.get('problem_id')
    focus_instruction = FOCUS_PROMPTS.get(focus, FOCUS_PROMPTS['general'])

    session_id = str(uuid.uuid4())[:8]

    problem_block = ""
    problem_title = None
    if problem_id:
        problem = get_problem_by_id(problem_id)
        if problem:
            problem_title = problem['title']
            problem_block = build_problem_block(problem)
    else:
        problem_block = (
            f"\n\nProblem selection guidance: {focus_instruction}"
            f"\nGenerate a novel, original problem in this category. Do not reuse well-known interview questions."
        )

    system_message = SYSTEM_PROMPT + "\n\n" + SESSION_CONFIG + problem_block

    session = {
        'id': session_id,
        'focus': focus,
        'mode': mode,
        'problem_id': problem_id,
        'problem_title': problem_title,
        'started_at': datetime.now().isoformat(),
        'status': 'active',
        'messages': [{'role': 'system', 'content': system_message}],
        'rating': None,
    }
    save_session(session)
    return jsonify({'id': session_id})


@app.route('/api/sessions/<session_id>')
def get_session(session_id):
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    visible = [m for m in session['messages'] if m['role'] != 'system']
    return jsonify({
        'id': session['id'],
        'focus': session.get('focus', 'general'),
        'problem_id': session.get('problem_id'),
        'problem_title': session.get('problem_title'),
        'started_at': session['started_at'],
        'status': session.get('status', 'active'),
        'messages': visible,
        'rating': session.get('rating'),
        'code': session.get('code', ''),
    })





def generate_test_cases(client, messages):
    """Ask GPT-4o to produce structured test cases from the interview conversation."""
    try:
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=[
                {'role': 'system', 'content': TEST_GEN_PROMPT},
                *[m for m in messages if m['role'] != 'system'],
            ],
            response_format={'type': 'json_object'},
            temperature=0.2,
            max_tokens=2000,
        )
        result = json.loads(response.choices[0].message.content)
        fn = result.get('function_name')
        cases = result.get('test_cases', [])
        if not fn or not cases:
            return None, []
        return fn, cases
    except Exception:
        return None, []


@app.route('/api/sessions/<session_id>/chat', methods=['POST'])
def chat(session_id):
    client = get_client()
    if not client:
        return jsonify({'error': 'OPENAI_API_KEY not set'}), 400

    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.json
    user_message = data.get('message', '')
    code = data.get('code', '')

    if code.strip():
        session['code'] = code

    content = user_message
    if code.strip():
        content += f"\n\n[CODE]\n```python\n{code}\n```"

    test_results_data = None
    test_context = ''

    if code.strip():
        test_results_data = run_tests_for_session(session, code, client)
        if test_results_data:
            test_context = code_runner.format_results_for_context(
                {
                    'success': test_results_data['success'],
                    'results': test_results_data['results'],
                    'error': test_results_data['error'],
                },
                test_results_data['display_name'],
            )
            content += f"\n\n{test_context}"

    session['messages'].append({'role': 'user', 'content': content})
    save_session(session)

    def generate():
        try:
            if test_results_data is not None:
                yield f"data: {json.dumps({'test_results': test_results_data})}\n\n"

            stream = client.chat.completions.create(
                model='gpt-4o',
                messages=session['messages'],
                stream=True,
                temperature=0.7,
                max_tokens=4000,
            )

            full_response = ''
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_response += delta.content
                    yield f"data: {json.dumps({'content': delta.content})}\n\n"

            session['messages'].append({'role': 'assistant', 'content': full_response})

            lower = full_response.lower()
            if any(term in lower for term in ['interview outcome', 'strong hire', 'no hire', 'lean hire']):
                rating_checks = [
                    ('strong hire', 'Strong Hire'),
                    ('lean no hire', 'No Hire'),
                    ('no hire', 'No Hire'),
                    ('lean hire', 'Lean Hire'),
                    ('mixed', 'Mixed'),
                    ('hire', 'Hire'),
                ]
                for key, label in rating_checks:
                    if key in lower:
                        session['rating'] = label
                        break

            save_session(session)
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/api/sessions/<session_id>/start', methods=['POST'])
def start_interview(session_id):
    """Send the first message to kick off the interview."""
    client = get_client()
    if not client:
        return jsonify({'error': 'OPENAI_API_KEY not set'}), 400

    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    intro = "Hi, I'm ready for the interview. Let's get started."
    session['messages'].append({'role': 'user', 'content': intro})
    save_session(session)

    def generate():
        try:
            stream = client.chat.completions.create(
                model='gpt-4o',
                messages=session['messages'],
                stream=True,
                temperature=0.7,
                max_tokens=2000,
            )

            full_response = ''
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_response += delta.content
                    yield f"data: {json.dumps({'content': delta.content})}\n\n"

            session['messages'].append({'role': 'assistant', 'content': full_response})
            save_session(session)
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/api/run', methods=['POST'])
def run_code():
    """Execute code and return stdout/stderr without any test harness."""
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
            capture_output=True, text=True, timeout=5,
        )
        return jsonify({
            'stdout': result.stdout,
            'stderr': result.stderr,
            'exit_code': result.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            'stdout': '',
            'stderr': 'Timeout: code took too long (>5s)',
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


@app.route('/api/sessions/<session_id>/run-tests', methods=['POST'])
def run_tests(session_id):
    """Auto-generate test cases from conversation context and run them against submitted code."""
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.json or {}
    user_code = data.get('code', '')
    if not user_code.strip():
        return jsonify({'error': 'No code provided'}), 400

    session['code'] = user_code
    save_session(session)

    client = get_client()
    test_results = run_tests_for_session(session, user_code, client)
    if not test_results:
        if not client:
            return jsonify({'error': 'OPENAI_API_KEY not set'}), 400
        return jsonify({'error': 'Could not auto-generate test cases. Make sure the interviewer has presented a problem first.'}), 400

    return jsonify(test_results)


@app.route('/api/sessions/<session_id>/code', methods=['PUT'])
def save_code(session_id):
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    data = request.json or {}
    session['code'] = data.get('code', '')
    save_session(session)
    return jsonify({'success': True})


@app.route('/api/sessions/<session_id>/end', methods=['POST'])
def end_session(session_id):
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    session['status'] = 'completed'
    session['ended_at'] = datetime.now().isoformat()
    save_session(session)
    return jsonify({'success': True})


@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    path = os.path.join(SESSIONS_DIR, f'{session_id}.json')
    if os.path.exists(path):
        os.remove(path)
    return jsonify({'success': True})





@app.route('/api/realtime/session', methods=['POST'])
def create_realtime_session():
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'OPENAI_API_KEY not set'}), 400

    sdp_offer = request.data.decode('utf-8')
    if not sdp_offer:
        return jsonify({'error': 'No SDP offer provided'}), 400

    focus = request.args.get('focus', 'general')
    focus_instruction = FOCUS_PROMPTS.get(focus, FOCUS_PROMPTS['general'])
    instructions = VOICE_SYSTEM_PROMPT + "\n\n" + SESSION_CONFIG + f"\n\nProblem selection guidance: {focus_instruction}"

    session_config = json.dumps({
        "type": "realtime",
        "model": "gpt-4o-realtime-preview",
        "output_modalities": ["audio"],
        "instructions": instructions,
        "audio": {
            "input": {
                "transcription": {
                    "model": "gpt-4o-mini-transcribe"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500
                }
            },
            "output": {
                "voice": "ash"
            }
        }
    })

    resp = http_requests.post(
        'https://api.openai.com/v1/realtime/calls',
        headers={
            'Authorization': f'Bearer {api_key}',
        },
        files={
            'sdp': (None, sdp_offer),
            'session': (None, session_config, 'application/json'),
        },
    )

    if resp.status_code != 200 and resp.status_code != 201:
        return jsonify({'error': f'OpenAI error: {resp.status_code} {resp.text}'}), resp.status_code

    return Response(resp.content, content_type='application/sdp')


@app.route('/api/sessions/<session_id>/transcript', methods=['POST'])
def save_transcript(session_id):
    """Save voice transcript messages to the session for history."""
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.json
    messages = data.get('messages', [])
    for msg in messages:
        session['messages'].append({
            'role': msg.get('role', 'user'),
            'content': msg.get('content', ''),
        })
    session['mode'] = 'voice'
    save_session(session)
    return jsonify({'success': True})





@app.route('/api/research/chat', methods=['POST'])
def research_chat():
    client = get_client()
    if not client:
        return jsonify({'error': 'OPENAI_API_KEY not set'}), 400

    data = request.json or {}
    problem_id = data.get('problem_id')
    user_message = data.get('message', '')
    history = data.get('history', [])

    if not user_message.strip():
        return jsonify({'error': 'No message provided'}), 400

    problem = get_problem_by_id(problem_id)
    problem_context = ""
    if problem:
        constraints = "\n".join(f"- {c}" for c in problem.get('constraints', []))
        problem_context = (
            f"\n\nThe student is studying this problem:"
            f"\n\nTitle: {problem['title']}"
            f"\nDifficulty: {problem['difficulty']}"
            f"\nCategory: {problem['category']}"
            f"\n\nScenario:\n{problem.get('scenario', '').strip()}"
            f"\n\nProblem:\n{problem.get('description', '').strip()}"
            f"\n\nConstraints:\n{constraints}"
            f"\n\nKey skills: {', '.join(problem.get('key_skills', []))}"
        )
        if problem.get('explanation'):
            problem_context += f"\n\nReference explanation (use to inform your answers):\n{problem['explanation']}"
        if problem.get('references'):
            refs = "\n".join(f"- {ref}" for ref in problem['references'])
            problem_context += f"\n\nReference topics and study material:\n{refs}"

    system_message = TUTOR_SYSTEM_PROMPT + problem_context

    messages = [{'role': 'system', 'content': system_message}]
    for msg in history:
        messages.append({'role': msg.get('role', 'user'), 'content': msg.get('content', '')})
    messages.append({'role': 'user', 'content': user_message})

    def generate():
        try:
            stream = client.chat.completions.create(
                model='gpt-4o',
                messages=messages,
                stream=True,
                temperature=0.6,
                max_tokens=3000,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield f"data: {json.dumps({'content': delta.content})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000)
