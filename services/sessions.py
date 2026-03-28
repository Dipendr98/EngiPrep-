import json
import os
import uuid
from datetime import datetime

from config import SESSIONS_DIR


def load(session_id):
    path = os.path.join(SESSIONS_DIR, f'{session_id}.json')
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return None


def save(session):
    path = os.path.join(SESSIONS_DIR, f'{session["id"]}.json')
    with open(path, 'w') as f:
        json.dump(session, f, indent=2)


def list_all():
    results = []
    for fname in sorted(os.listdir(SESSIONS_DIR), reverse=True):
        if fname.endswith('.json'):
            with open(os.path.join(SESSIONS_DIR, fname), 'r') as f:
                s = json.load(f)
                results.append({
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
    return results


def delete(session_id):
    path = os.path.join(SESSIONS_DIR, f'{session_id}.json')
    if os.path.exists(path):
        os.remove(path)


def create(focus, mode, problem_id, problem_title, system_message):
    session_id = str(uuid.uuid4())[:8]
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
    save(session)
    return session
