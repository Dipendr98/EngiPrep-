from flask import Blueprint, request, jsonify, Response, stream_with_context

import ai
import config
import problems

bp = Blueprint('research', __name__)


@bp.route('/api/research/chat', methods=['POST'])
def research_chat():
    client = ai.get_client()
    if not client:
        return jsonify({'error': 'OPENAI_API_KEY not set'}), 400

    data = request.json or {}
    problem_id = data.get('problem_id')
    user_message = data.get('message', '')
    history = data.get('history', [])

    if not user_message.strip():
        return jsonify({'error': 'No message provided'}), 400

    problem = problems.get_by_id(problem_id)
    problem_context = ""
    if problem:
        problem_context = problems.build_study_context(problem)

    system_message = config.TUTOR_SYSTEM_PROMPT + problem_context

    messages = [{'role': 'system', 'content': system_message}]
    for msg in history:
        messages.append({'role': msg.get('role', 'user'), 'content': msg.get('content', '')})
    messages.append({'role': 'user', 'content': user_message})

    def generate():
        yield from ai.sse_stream(
            client, messages,
            temperature=config.RESEARCH_TEMPERATURE,
            max_tokens=config.RESEARCH_MAX_TOKENS,
        )

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers=config.SSE_HEADERS,
    )
