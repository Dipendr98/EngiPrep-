import json
import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(__file__)

SESSIONS_DIR = os.path.join(BASE_DIR, 'user_data', 'sessions')
PROBLEMS_DIR = os.path.join(BASE_DIR, 'problems')
PROMPTS_DIR = os.path.join(BASE_DIR, 'prompts')

os.makedirs(SESSIONS_DIR, exist_ok=True)

# Pollinations AI (OpenAI-compatible)
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://gen.pollinations.ai/v1')
CHAT_MODEL = os.environ.get('CHAT_MODEL', 'claude-large')

# OpenAI models (used only for realtime/voice features)
REALTIME_MODEL = 'gpt-4o-realtime-preview'
TRANSCRIPTION_MODEL = 'gpt-4o-mini-transcribe'

# Chat parameters
CHAT_TEMPERATURE = 0.7
CHAT_MAX_TOKENS = 4000
START_MAX_TOKENS = 2000
RESEARCH_TEMPERATURE = 0.6
RESEARCH_MAX_TOKENS = 3000
TEST_GEN_TEMPERATURE = 0.2
TEST_GEN_MAX_TOKENS = 2000

# Code execution
CODE_TIMEOUT = 5

# Voice / Realtime
REALTIME_API_URL = 'https://api.openai.com/v1/realtime/calls'
VOICE_NAME = 'ash'
VAD_THRESHOLD = 0.5
VAD_PREFIX_PADDING_MS = 300
VAD_SILENCE_DURATION_MS = 500

# Flask
FLASK_PORT = 5000
FLASK_DEBUG = True

# SSE headers reused by all streaming endpoints
SSE_HEADERS = {
    'Cache-Control': 'no-cache',
    'X-Accel-Buffering': 'no',
}


def _load_prompt(filename):
    with open(os.path.join(PROMPTS_DIR, filename), encoding='utf-8') as f:
        return f.read()


SYSTEM_PROMPT = _load_prompt('interviewer.txt')
SESSION_CONFIG = _load_prompt('session_config.txt')
FOCUS_PROMPTS = json.loads(_load_prompt('focus_prompts.json'))
TEST_GEN_PROMPT = _load_prompt('test_generation.txt')
VOICE_SYSTEM_PROMPT = _load_prompt('voice_interviewer.txt')
TUTOR_SYSTEM_PROMPT = _load_prompt('tutor.txt')
