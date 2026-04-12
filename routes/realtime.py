import json
import os

import requests as http_requests
from flask import Blueprint, request, jsonify, Response

import config

bp = Blueprint('realtime', __name__)


def _is_openai_base_url(base_url):
    normalized = (base_url or '').strip().rstrip('/').lower()
    return normalized in ('', 'https://api.openai.com/v1')


def _resolve_realtime_api_key():
    header_base_url = request.headers.get('X-AI-Base-URL', '').strip()
    header_api_key = request.headers.get('X-AI-API-Key', '').strip()
    env_api_key = os.environ.get('OPENAI_API_KEY', '').strip()

    if header_base_url and not _is_openai_base_url(header_base_url):
        return None, (
            'Voice mode currently requires the official OpenAI realtime API. '
            'Switch AI Provider Settings to OpenAI and enter a valid OpenAI API key.'
        )

    if header_api_key and header_api_key != 'pollinations':
        return header_api_key, None

    if env_api_key and env_api_key != 'pollinations':
        return env_api_key, None

    return None, (
        'Voice mode requires a valid OpenAI API key. '
        'Open AI Provider Settings, choose OpenAI, and enter your key before starting voice mode.'
    )


@bp.route('/api/realtime/session', methods=['POST'])
def create_realtime_session():
    api_key, config_error = _resolve_realtime_api_key()
    if config_error:
        return jsonify({'error': config_error}), 400

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

    try:
        resp = http_requests.post(
            config.REALTIME_API_URL,
            headers={'Authorization': f'Bearer {api_key}'},
            files={
                'sdp': (None, sdp_offer),
                'session': (None, session_config, 'application/json'),
            },
            timeout=30,
        )
    except http_requests.RequestException as exc:
        return jsonify({
            'error': 'Could not reach the OpenAI realtime API.',
            'details': {'network_error': str(exc)},
        }), 502

    if resp.status_code not in (200, 201):
        try:
            error_payload = resp.json()
        except ValueError:
            error_payload = {'raw': resp.text}
        return jsonify({
            'error': f'OpenAI error: {resp.status_code}',
            'details': error_payload,
        }), resp.status_code

    return Response(resp.content, content_type='application/sdp')
