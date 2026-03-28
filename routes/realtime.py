import json
import os

import requests as http_requests
from flask import Blueprint, request, jsonify, Response

import config

bp = Blueprint('realtime', __name__)


@bp.route('/api/realtime/session', methods=['POST'])
def create_realtime_session():
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'OPENAI_API_KEY not set'}), 400

    sdp_offer = request.data.decode('utf-8')
    if not sdp_offer:
        return jsonify({'error': 'No SDP offer provided'}), 400

    focus = request.args.get('focus', 'general')
    focus_instruction = config.FOCUS_PROMPTS.get(focus, config.FOCUS_PROMPTS['general'])
    instructions = (
        config.VOICE_SYSTEM_PROMPT + "\n\n" + config.SESSION_CONFIG
        + f"\n\nProblem selection guidance: {focus_instruction}"
    )

    session_config = json.dumps({
        "type": "realtime",
        "model": config.REALTIME_MODEL,
        "output_modalities": ["audio"],
        "instructions": instructions,
        "audio": {
            "input": {
                "transcription": {
                    "model": config.TRANSCRIPTION_MODEL,
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": config.VAD_THRESHOLD,
                    "prefix_padding_ms": config.VAD_PREFIX_PADDING_MS,
                    "silence_duration_ms": config.VAD_SILENCE_DURATION_MS,
                },
            },
            "output": {
                "voice": config.VOICE_NAME,
            },
        },
    })

    resp = http_requests.post(
        config.REALTIME_API_URL,
        headers={'Authorization': f'Bearer {api_key}'},
        files={
            'sdp': (None, sdp_offer),
            'session': (None, session_config, 'application/json'),
        },
    )

    if resp.status_code not in (200, 201):
        return jsonify({'error': f'OpenAI error: {resp.status_code} {resp.text}'}), resp.status_code

    return Response(resp.content, content_type='application/sdp')
