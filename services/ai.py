import json
import os

from flask import request as flask_request
from openai import OpenAI

import config

# Default client singleton (uses .env / config defaults).
_default_client = None

# Provider presets for the frontend
PROVIDER_PRESETS = [
    {
        'id': 'pollinations',
        'name': 'Pollinations AI',
        'base_url': 'https://text.pollinations.ai/openai',
        'default_model': 'openai',
        'requires_key': False,
        'description': 'Pollinations AI — free, no API key needed. OpenAI-compatible.',
        'models': ['openai', 'openai-large', 'mistral', 'llama'],
    },
    {
        'id': 'openrouter',
        'name': 'OpenRouter',
        'base_url': 'https://openrouter.ai/api/v1',
        'default_model': 'anthropic/claude-sonnet-4-20250514',
        'requires_key': True,
        'description': 'Access 100+ models with one API key. Get a key at openrouter.ai',
        'models': [
            'anthropic/claude-sonnet-4-20250514',
            'anthropic/claude-3.5-sonnet',
            'openai/gpt-4o',
            'openai/gpt-4o-mini',
            'google/gemini-2.0-flash-001',
            'meta-llama/llama-3.1-70b-instruct',
            'mistralai/mistral-large-latest',
        ],
    },
    {
        'id': 'openai',
        'name': 'OpenAI',
        'base_url': 'https://api.openai.com/v1',
        'default_model': 'gpt-4o',
        'requires_key': True,
        'description': 'Official OpenAI API. Get a key at platform.openai.com',
        'models': ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
    },
    {
        'id': 'anthropic',
        'name': 'Anthropic (Claude)',
        'base_url': 'https://api.anthropic.com/v1',
        'default_model': 'claude-sonnet-4-20250514',
        'requires_key': True,
        'description': 'Official Claude API. Get a key at console.anthropic.com',
        'models': ['claude-sonnet-4-20250514', 'claude-3-5-sonnet-20241022', 'claude-3-haiku-20240307'],
        'note': 'Requires anthropic SDK or OpenAI-compatible proxy',
    },
    {
        'id': 'nvidia',
        'name': 'NVIDIA NIM',
        'base_url': 'https://integrate.api.nvidia.com/v1',
        'default_model': 'meta/llama-3.1-405b-instruct',
        'requires_key': True,
        'description': 'NVIDIA AI Foundation models. Get a key at build.nvidia.com',
        'models': [
            'meta/llama-3.1-405b-instruct',
            'meta/llama-3.1-70b-instruct',
            'mistralai/mistral-large-latest',
        ],
    },
    {
        'id': 'groq',
        'name': 'Groq',
        'base_url': 'https://api.groq.com/openai/v1',
        'default_model': 'llama-3.1-70b-versatile',
        'requires_key': True,
        'description': 'Ultra-fast inference. Get a key at console.groq.com',
        'models': ['llama-3.1-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768'],
    },
    {
        'id': 'together',
        'name': 'Together AI',
        'base_url': 'https://api.together.xyz/v1',
        'default_model': 'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo',
        'requires_key': True,
        'description': 'Open-source models at scale. Get a key at together.ai',
        'models': [
            'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo',
            'mistralai/Mixtral-8x7B-Instruct-v0.1',
        ],
    },
    {
        'id': 'custom',
        'name': 'Custom Provider',
        'base_url': '',
        'default_model': '',
        'requires_key': True,
        'description': 'Any OpenAI-compatible API endpoint',
        'models': [],
    },
]


def _get_default_client():
    """Return a cached default client using .env / config settings."""
    global _default_client
    if _default_client is None:
        api_key = os.environ.get('OPENAI_API_KEY', 'pollinations')
        base_url = config.OPENAI_BASE_URL
        _default_client = OpenAI(api_key=api_key, base_url=base_url)
    return _default_client


def get_client():
    """Return an OpenAI-compatible client.

    If the incoming Flask request contains provider headers
    (X-AI-Base-URL, X-AI-API-Key), create a per-request client.
    Otherwise fall back to the default singleton.
    """
    try:
        base_url = flask_request.headers.get('X-AI-Base-URL', '').strip()
        api_key = flask_request.headers.get('X-AI-API-Key', '').strip()
    except RuntimeError:
        # Outside of a request context
        return _get_default_client()

    if base_url:
        key = api_key or 'pollinations'
        return OpenAI(api_key=key, base_url=base_url)

    return _get_default_client()


def get_model():
    """Return the model name to use.

    Checks the X-AI-Model request header first, then falls back to config.
    """
    try:
        model = flask_request.headers.get('X-AI-Model', '').strip()
        if model:
            return model
    except RuntimeError:
        pass
    return config.CHAT_MODEL


def stream_chat(client, messages, temperature=None, max_tokens=None, model=None):
    """Yield text chunks from a streaming chat completion."""
    stream = client.chat.completions.create(
        model=model or get_model(),
        messages=messages,
        stream=True,
        temperature=temperature if temperature is not None else config.CHAT_TEMPERATURE,
        max_tokens=max_tokens if max_tokens is not None else config.CHAT_MAX_TOKENS,
    )

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def sse_stream(client, messages, temperature=None, max_tokens=None, model=None):
    """Full SSE generator that yields data lines and a done sentinel."""
    try:
        for text in stream_chat(client, messages, temperature, max_tokens, model):
            yield f"data: {json.dumps({'content': text})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e) or type(e).__name__})}\n\n"


def create_chat_completion(
    client,
    messages,
    temperature=None,
    max_tokens=None,
    model=None,
    response_format=None,
):
    """Create a chat completion with a safe fallback for optional structured output hints."""
    kwargs = {
        'model': model or get_model(),
        'messages': messages,
        'temperature': temperature if temperature is not None else config.CHAT_TEMPERATURE,
        'max_tokens': max_tokens if max_tokens is not None else config.CHAT_MAX_TOKENS,
    }

    if response_format is None:
        return client.chat.completions.create(**kwargs)

    try:
        return client.chat.completions.create(
            **kwargs,
            response_format=response_format,
        )
    except Exception:
        return client.chat.completions.create(**kwargs)


def generate_test_cases(client, messages, model=None):
    """Ask the model to produce structured test cases from the interview conversation."""
    system_content = (
        config.TEST_GEN_PROMPT
        + "\n\nIMPORTANT: You MUST respond with valid JSON only. "
        "No markdown, no code fences, no extra text."
    )

    try:
        response = create_chat_completion(
            client,
            messages=[
                {'role': 'system', 'content': system_content},
                *[m for m in messages if m['role'] != 'system'],
            ],
            model=model or get_model(),
            temperature=config.TEST_GEN_TEMPERATURE,
            max_tokens=config.TEST_GEN_MAX_TOKENS,
            response_format={'type': 'json_object'},
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
