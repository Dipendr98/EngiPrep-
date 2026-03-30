import json
import os

from openai import OpenAI

import config

# Lazy-loaded client singleton.
_client = None


def get_client():
    """Return a cached OpenAI-compatible client pointing at the Pollinations API.

    The client is created lazily on first call so that environment variables
    (loaded from .env by config.py) are available.
    """
    global _client
    if _client is None:
        api_key = os.environ.get('OPENAI_API_KEY', 'pollinations')
        base_url = config.OPENAI_BASE_URL
        _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client


def stream_chat(client, messages, temperature=None, max_tokens=None):
    """Yield SSE-formatted chunks from a streaming chat completion.

    Yields tuples of (event_line, delta_text) so callers can accumulate
    the full response while forwarding events to the client.
    """
    stream = client.chat.completions.create(
        model=config.CHAT_MODEL,
        messages=messages,
        stream=True,
        temperature=temperature if temperature is not None else config.CHAT_TEMPERATURE,
        max_tokens=max_tokens if max_tokens is not None else config.CHAT_MAX_TOKENS,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def sse_stream(client, messages, temperature=None, max_tokens=None):
    """Full SSE generator that yields data lines and a done sentinel."""
    try:
        for text in stream_chat(client, messages, temperature, max_tokens):
            yield f"data: {json.dumps({'content': text})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


def generate_test_cases(client, messages):
    """Ask the model to produce structured test cases from the interview conversation.

    Note: The Pollinations / Claude API may not support the ``response_format``
    parameter, so we instruct the model via the system prompt to return JSON
    and parse the response manually.
    """
    system_content = (
        config.TEST_GEN_PROMPT
        + "\n\nIMPORTANT: You MUST respond with valid JSON only. "
        "No markdown, no code fences, no extra text."
    )

    try:
        response = client.chat.completions.create(
            model=config.CHAT_MODEL,
            messages=[
                {'role': 'system', 'content': system_content},
                *[m for m in messages if m['role'] != 'system'],
            ],
            temperature=config.TEST_GEN_TEMPERATURE,
            max_tokens=config.TEST_GEN_MAX_TOKENS,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if the model wraps its answer
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1] if '\n' in raw else raw[3:]
            if raw.endswith('```'):
                raw = raw[:-3]
            raw = raw.strip()
        result = json.loads(raw)
        fn = result.get('function_name')
        cases = result.get('test_cases', [])
        if not fn or not cases:
            return None, []
        return fn, cases
    except Exception:
        return None, []