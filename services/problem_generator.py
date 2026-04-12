"""AI-powered problem generator that creates LeetCode-style practice problems.

Uses the Pollinations API (Claude) to generate new coding problems across
various topics and difficulty levels, saving them as YAML files compatible
with the existing problem bank.
"""

import json
import os
import re
from glob import glob

import yaml

import config
from services import ai, problems

# Topics organized by category for diverse problem generation
TOPIC_POOLS = {
    'arrays': [
        'two pointers', 'sliding window', 'prefix sum', 'kadane algorithm',
        'merge intervals', 'matrix traversal', 'rotate array', 'subarray problems',
        'dutch national flag', 'next permutation',
    ],
    'strings': [
        'palindrome', 'anagram', 'substring search', 'string matching',
        'character frequency', 'string compression', 'parentheses validation',
        'longest common substring', 'regex matching', 'string reversal',
    ],
    'linked lists': [
        'reverse linked list', 'detect cycle', 'merge sorted lists',
        'remove nth node', 'intersection of lists', 'partition list',
        'copy list with random pointer', 'flatten multilevel list',
    ],
    'trees': [
        'binary tree traversal', 'BST operations', 'tree depth',
        'lowest common ancestor', 'serialize deserialize tree',
        'balanced tree check', 'path sum', 'tree construction from traversals',
    ],
    'graphs': [
        'BFS', 'DFS', 'topological sort', 'shortest path', 'union find',
        'connected components', 'cycle detection in graph', 'bipartite check',
        'minimum spanning tree', 'graph coloring',
    ],
    'dynamic programming': [
        'fibonacci variants', 'knapsack', 'longest common subsequence',
        'coin change', 'edit distance', 'matrix chain multiplication',
        'longest increasing subsequence', 'partition equal subset sum',
        'word break', 'house robber',
    ],
    'search': [
        'binary search variants', 'search in rotated array', 'find peak element',
        'search 2D matrix', 'kth smallest element', 'median of two sorted arrays',
        'first and last position', 'search insert position',
    ],
    'backtracking': [
        'permutations', 'combinations', 'subsets', 'n-queens',
        'sudoku solver', 'word search', 'combination sum',
        'generate parentheses', 'letter combinations',
    ],
    'stateful': [
        'LRU cache', 'min stack', 'queue using stacks', 'trie',
        'design hashmap', 'design hashset', 'iterator pattern',
        'circular buffer', 'ordered set', 'frequency stack',
    ],
    'streaming': [
        'moving average', 'top k frequent', 'stream median',
        'sliding window maximum', 'rate limiter', 'event counter',
        'data stream deduplication', 'running statistics',
    ],
    'cybersecurity': [
        'input validation and sanitization', 'SQL injection prevention',
        'XSS filter implementation', 'password strength validator',
        'JWT token parser and validator', 'CSRF token generator',
        'rate limiter for brute force prevention', 'IP allowlist/blocklist',
        'log anomaly detector', 'file integrity checker',
        'encryption and decryption', 'hash collision detector',
        'certificate chain validator', 'access control list parser',
        'network packet analyzer', 'port scanner detector',
        'base64 and hex encoding', 'secret rotation manager',
        'RBAC permission resolver', 'audit trail logger',
        'vulnerability scanner output parser', 'firewall rule evaluator',
        'CIDR subnet calculator', 'OAuth flow validator',
        'secure random token generator', 'malware signature matcher',
    ],
    'fullstack': [
        'REST API endpoint design', 'URL router implementation',
        'middleware pipeline', 'request validator',
        'pagination cursor builder', 'query string parser',
        'form data validator', 'cookie parser and serializer',
        'HTML template engine', 'CSS specificity calculator',
        'JSON schema validator', 'GraphQL query parser',
        'WebSocket message handler', 'HTTP cache header parser',
        'CORS policy evaluator', 'multipart form parser',
        'database migration planner', 'ORM query builder',
        'session store implementation', 'API rate limiter',
        'webhook signature verifier', 'content negotiation',
        'redirect chain resolver', 'sitemap generator',
        'responsive breakpoint calculator', 'state machine for forms',
    ],
}

DIFFICULTIES = ['Easy', 'Medium', 'Hard']

GENERATE_PROMPT = """You are an expert coding interview problem designer. Generate a NEW, ORIGINAL coding problem suitable for technical interview practice.

Requirements:
- Topic area: {topic}
- Difficulty: {difficulty}
- Category: {category}
- The problem must be ORIGINAL - not a direct copy of any well-known LeetCode/HackerRank problem
- It should test the specified topic/skill area
- Include a realistic scenario that gives context (like a real engineering use case)
- The function signature should be in Python
- Include 3-4 test cases with clear inputs and expected outputs
- Include 2 follow-up questions for candidates who finish early

You MUST respond with valid JSON in this exact format:
{{
  "title": "Problem Title",
  "category": "{category}",
  "difficulty": "{difficulty}",
  "summary": "One-line summary of the problem",
  "description": "Full problem description explaining what to implement",
  "scenario": "A realistic engineering scenario (2-3 sentences) explaining why this problem matters in practice",
  "constraints": ["constraint 1", "constraint 2"],
  "examples": [
    {{"input": "function_name(args)", "output": "expected_output"}},
    {{"input": "function_name(args)", "output": "expected_output"}}
  ],
  "starter_code": "def function_name(params):\\n    pass",
  "function_name": "function_name",
  "key_skills": ["skill1", "skill2"],
  "follow_ups": ["Follow-up question 1", "Follow-up question 2"],
  "test_cases": [
    {{
      "label": "basic case",
      "input": {{"param1": "value1"}},
      "expected": "expected_value"
    }},
    {{
      "label": "edge case",
      "input": {{"param1": "value2"}},
      "expected": "expected_value"
    }},
    {{
      "label": "larger input",
      "input": {{"param1": "value3"}},
      "expected": "expected_value"
    }}
  ],
  "explanation": "Brief explanation of the optimal approach and key insights",
  "references": ["Reference topic 1 to study", "Reference topic 2 to study"]
}}

IMPORTANT: Return ONLY valid JSON. No markdown, no code fences, no extra text."""

FALLBACK_CONSTRAINTS = [
    'Aim for an efficient solution with clear tradeoffs.',
    'Handle empty inputs and edge cases explicitly.',
]

FALLBACK_FOLLOW_UPS = [
    'How would you optimize the solution for larger inputs?',
    'What tradeoffs would change if updates arrived in real time?',
]

FALLBACK_REFERENCES = [
    'Time and space complexity analysis',
    'Edge-case driven testing',
]


def _next_problem_id():
    """Find the next available problem ID."""
    max_id = 0
    for path in glob(os.path.join(config.PROBLEMS_DIR, '*.yaml')):
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
                if data and 'id' in data:
                    max_id = max(max_id, data['id'])
        except Exception:
            continue
    return max_id + 1


def _parse_ai_response(raw_text):
    """Parse the AI response into JSON, tolerating common formatting noise."""
    text = raw_text.strip().replace('\ufeff', '')
    candidates = [text]

    if text.startswith('```'):
        fenced = text.split('\n', 1)[1] if '\n' in text else text[3:]
        if fenced.endswith('```'):
            fenced = fenced[:-3]
        candidates.append(fenced.strip())

    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start:end + 1])

    decoder = json.JSONDecoder()
    errors = []

    for candidate in candidates:
        normalized = (
            candidate.strip()
            .replace('\u201c', '"')
            .replace('\u201d', '"')
            .replace('\u2018', "'")
            .replace('\u2019', "'")
        )
        for attempt in (normalized, re.sub(r',(\s*[}\]])', r'\1', normalized)):
            try:
                parsed = json.loads(attempt)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError as exc:
                errors.append(str(exc))
                try:
                    parsed, _ = decoder.raw_decode(attempt)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue

    raise ValueError(errors[-1] if errors else 'Model did not return valid JSON')


def _stringify(value, default=''):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False)


def _string_list(value, fallback):
    if not isinstance(value, list):
        value = fallback
    cleaned = [_stringify(item) for item in value if _stringify(item)]
    return cleaned or list(fallback)


def _normalize_examples(value, function_name):
    if not isinstance(value, list):
        value = []

    examples = []
    for item in value[:4]:
        if not isinstance(item, dict):
            continue
        example_input = _stringify(item.get('input'))
        example_output = _stringify(item.get('output'))
        if example_input and example_output:
            examples.append({
                'input': example_input,
                'output': example_output,
            })

    if examples:
        return examples

    placeholder_call = f'{function_name}(...)' if function_name else 'solve(...)'
    return [{'input': placeholder_call, 'output': 'expected_output'}]


def _normalize_test_cases(value):
    if not isinstance(value, list):
        return []

    cases = []
    for index, item in enumerate(value[:6], start=1):
        if not isinstance(item, dict):
            continue
        raw_input = item.get('input', {})
        if isinstance(raw_input, dict):
            normalized_input = raw_input
        else:
            normalized_input = {'value': raw_input}

        cases.append({
            'label': _stringify(item.get('label'), f'case {index}') or f'case {index}',
            'input': normalized_input,
            'expected': item.get('expected'),
        })

    return cases


def _infer_function_name(starter_code):
    match = re.search(r'def\s+([A-Za-z_]\w*)\s*\(', starter_code or '')
    if match:
        return match.group(1)
    return ''


def _normalize_problem_data(problem_data, category, difficulty, topic):
    if not isinstance(problem_data, dict):
        raise ValueError('Model response was not a JSON object')

    starter_code = _stringify(problem_data.get('starter_code'))
    function_name = _stringify(problem_data.get('function_name')) or _infer_function_name(starter_code)
    if not function_name:
        function_name = _slugify(problem_data.get('title', '') or topic or 'generated_problem').replace('-', '_')
        starter_code = starter_code or f'def {function_name}(value):\n    pass'
    elif not starter_code:
        starter_code = f'def {function_name}(value):\n    pass'

    normalized = {
        'title': _stringify(problem_data.get('title'), f'{difficulty} {topic.title()} Challenge'),
        'category': _stringify(problem_data.get('category'), category) or category,
        'difficulty': _stringify(problem_data.get('difficulty'), difficulty) or difficulty,
        'summary': _stringify(problem_data.get('summary'), f'Solve a {difficulty.lower()} {topic} challenge.'),
        'description': _stringify(problem_data.get('description'), f'Implement {function_name} for this {topic} problem.'),
        'scenario': _stringify(problem_data.get('scenario'), f'This exercise practices {topic} in a realistic engineering setting.'),
        'constraints': _string_list(problem_data.get('constraints'), FALLBACK_CONSTRAINTS),
        'starter_code': starter_code,
        'function_name': function_name,
        'key_skills': _string_list(problem_data.get('key_skills'), [topic]),
        'follow_ups': _string_list(problem_data.get('follow_ups'), FALLBACK_FOLLOW_UPS),
        'explanation': _stringify(problem_data.get('explanation'), 'Focus on the core data flow, edge cases, and complexity tradeoffs.'),
        'references': _string_list(problem_data.get('references'), FALLBACK_REFERENCES),
    }
    normalized['examples'] = _normalize_examples(problem_data.get('examples'), function_name)
    normalized['test_cases'] = _normalize_test_cases(problem_data.get('test_cases'))

    if not normalized['test_cases']:
        normalized['test_cases'] = [
            {
                'label': 'example case',
                'input': {'value': 'replace_with_input'},
                'expected': 'replace_with_expected_output',
            }
        ]

    return normalized


def _generate_problem_payload(client, prompt, category, difficulty, topic):
    model = ai.get_model()
    messages = [
        {
            'role': 'system',
            'content': (
                'You are an expert coding problem designer. '
                'Always respond with valid JSON only. '
                'Do not include markdown or explanations outside the JSON object.'
            ),
        },
        {'role': 'user', 'content': prompt},
    ]

    response = ai.create_chat_completion(
        client,
        messages=messages,
        model=model,
        temperature=0.35,
        max_tokens=3000,
        response_format={'type': 'json_object'},
    )
    raw = response.choices[0].message.content or ''

    try:
        return _normalize_problem_data(_parse_ai_response(raw), category, difficulty, topic)
    except Exception:
        repair_messages = [
            {
                'role': 'system',
                'content': (
                    'Convert the provided content into one valid JSON object for a coding interview problem. '
                    'Preserve the intent, fill missing fields sensibly, and return JSON only.'
                ),
            },
            {
                'role': 'user',
                'content': (
                    f'{prompt}\n\n'
                    'Previous model output:\n'
                    f'{raw}'
                ),
            },
        ]
        repair_response = ai.create_chat_completion(
            client,
            messages=repair_messages,
            model=model,
            temperature=0.1,
            max_tokens=3000,
            response_format={'type': 'json_object'},
        )
        repaired_raw = repair_response.choices[0].message.content or ''
        return _normalize_problem_data(_parse_ai_response(repaired_raw), category, difficulty, topic)


def generate_problem(category=None, difficulty=None, topic=None):
    """Generate a new problem using AI and save it as a YAML file.

    Args:
        category: Problem category (e.g., 'arrays', 'trees'). Random if None.
        difficulty: 'Easy', 'Medium', or 'Hard'. Random if None.
        topic: Specific topic hint. Random from category pool if None.

    Returns:
        dict with the generated problem data, or None on failure.
    """
    import random

    # Pick category, difficulty, topic if not specified
    if not category:
        category = random.choice(list(TOPIC_POOLS.keys()))
    if not difficulty:
        difficulty = random.choice(DIFFICULTIES)
    if not topic:
        pool = TOPIC_POOLS.get(category, ['general algorithms'])
        topic = random.choice(pool)

    client = ai.get_client()
    prompt = GENERATE_PROMPT.format(
        topic=topic,
        difficulty=difficulty,
        category=category,
    )

    try:
        problem_data = _generate_problem_payload(client, prompt, category, difficulty, topic)
    except Exception as e:
        return {'error': f'AI generation failed: {str(e)}'}

    # Assign ID and save
    problem_id = _next_problem_id()
    problem_data['id'] = problem_id
    problem_data['test_type'] = 'function'

    # Ensure required fields
    problem_data.setdefault('category', category)
    problem_data.setdefault('difficulty', difficulty)
    problem_data.setdefault('key_skills', [topic])

    # Save as YAML
    filename = f"{problem_id:03d}-{_slugify(problem_data.get('title', 'generated'))}.yaml"
    filepath = os.path.join(config.PROBLEMS_DIR, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        yaml.dump(problem_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    problems.invalidate_cache()
    return problem_data


def generate_problem_ephemeral(category=None, difficulty=None, topic=None):
    """Generate a new problem using AI but do NOT save it to disk.

    The problem is returned with a temporary negative ID so it won't
    collide with real problems. It exists only in the frontend's memory.
    """
    import random

    if not category:
        category = random.choice(list(TOPIC_POOLS.keys()))
    if not difficulty:
        difficulty = random.choice(DIFFICULTIES)
    if not topic:
        pool = TOPIC_POOLS.get(category, ['general algorithms'])
        topic = random.choice(pool)

    client = ai.get_client()
    prompt = GENERATE_PROMPT.format(
        topic=topic,
        difficulty=difficulty,
        category=category,
    )

    try:
        problem_data = _generate_problem_payload(client, prompt, category, difficulty, topic)
    except Exception as e:
        return {'error': f'AI generation failed: {str(e)}'}

    # Assign a temporary negative ID (won't be saved)
    import time
    problem_data['id'] = -int(time.time() * 1000) % 1000000
    problem_data['test_type'] = 'function'
    problem_data['_ephemeral'] = True

    problem_data.setdefault('category', category)
    problem_data.setdefault('difficulty', difficulty)
    problem_data.setdefault('key_skills', [topic])

    return problem_data


def generate_batch(count=5, category=None, difficulty=None):
    """Generate multiple problems at once.

    Args:
        count: Number of problems to generate (1-10).
        category: Optional category filter.
        difficulty: Optional difficulty filter.

    Returns:
        List of generated problem dicts.
    """
    count = max(1, min(count, 10))
    results = []
    for _ in range(count):
        result = generate_problem(category=category, difficulty=difficulty)
        results.append(result)
    return results


def _slugify(text):
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text[:50].strip('-')
