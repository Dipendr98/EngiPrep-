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
from services import ai

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
    """Parse the AI response, stripping markdown fences if present."""
    text = raw_text.strip()
    # Strip markdown code fences
    if text.startswith('```'):
        text = text.split('\n', 1)[1] if '\n' in text else text[3:]
        if text.endswith('```'):
            text = text[:-3]
        text = text.strip()
    return json.loads(text)


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
        response = client.chat.completions.create(
            model=config.CHAT_MODEL,
            messages=[
                {'role': 'system', 'content': 'You are an expert coding problem designer. Always respond with valid JSON only.'},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.8,
            max_tokens=3000,
        )
        raw = response.choices[0].message.content
        problem_data = _parse_ai_response(raw)
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