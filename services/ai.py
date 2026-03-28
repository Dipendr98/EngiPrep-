import json
import os

from openai import OpenAI

import config


def get_client():
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


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
    """Ask the model to produce structured test cases from the interview conversation."""
    try:
        response = client.chat.completions.create(
            model=config.CHAT_MODEL,
            messages=[
                {'role': 'system', 'content': config.TEST_GEN_PROMPT},
                *[m for m in messages if m['role'] != 'system'],
            ],
            response_format={'type': 'json_object'},
            temperature=config.TEST_GEN_TEMPERATURE,
            max_tokens=config.TEST_GEN_MAX_TOKENS,
        )
        result = json.loads(response.choices[0].message.content)
        fn = result.get('function_name')
        cases = result.get('test_cases', [])
        if not fn or not cases:
            return None, []
        return fn, cases
    except Exception:
        return None, []
