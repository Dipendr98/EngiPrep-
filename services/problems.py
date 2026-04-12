from glob import glob
import os

import yaml

from config import PROBLEMS_DIR


_problems_cache = None


def load_all():
    global _problems_cache
    if _problems_cache is None:
        _problems_cache = []
        for path in sorted(glob(os.path.join(PROBLEMS_DIR, '*.yaml'))):
            with open(path) as f:
                _problems_cache.append(yaml.safe_load(f))
    return _problems_cache


def invalidate_cache():
    global _problems_cache
    _problems_cache = None


def get_by_id(problem_id):
    if problem_id is None:
        return None
    for problem in load_all():
        if problem.get('id') == problem_id:
            return problem
    return None


def serialize_for_list(problem):
    return {
        'id': problem['id'],
        'title': problem['title'],
        'category': problem['category'],
        'difficulty': problem['difficulty'],
        'summary': problem.get('summary', ''),
        'starter_code': problem.get('starter_code', ''),
        'key_skills': problem.get('key_skills', []),
    }


def serialize_full(problem):
    return {
        'id': problem['id'],
        'title': problem['title'],
        'category': problem['category'],
        'difficulty': problem['difficulty'],
        'summary': problem.get('summary', ''),
        'description': problem.get('description', ''),
        'scenario': problem.get('scenario', ''),
        'constraints': problem.get('constraints', []),
        'examples': problem.get('examples', []),
        'key_skills': problem.get('key_skills', []),
        'follow_ups': problem.get('follow_ups', []),
        'starter_code': problem.get('starter_code', ''),
        'explanation': problem.get('explanation', ''),
        'references': problem.get('references', []),
    }


def build_problem_block(problem):
    follow_ups = "\n".join(f"- {f}" for f in problem.get('follow_ups', []))
    constraints = "\n".join(f"- {c}" for c in problem.get('constraints', []))
    examples = []
    for example in problem.get('examples', [])[:2]:
        examples.append(
            "Input:\n"
            f"{example.get('input', '').strip()}\n\n"
            "Output:\n"
            f"{example.get('output', '').strip()}"
        )
    examples_block = "\n\n".join(examples)

    interface_block = ""
    if problem.get('starter_code'):
        interface_block = (
            "\n\nRequired interface (the candidate's code should match this shape):"
            f"\n```python\n{problem['starter_code']}\n```"
        )

    return (
        f"\n\nYou MUST use this specific problem for the interview:"
        f"\n\nTitle: {problem['title']}"
        f"\nDifficulty: {problem['difficulty']}"
        f"\nCategory: {problem['category']}"
        f"\n\nScenario:\n{problem.get('scenario', '').strip()}"
        f"\n\nProblem:\n{problem['description']}"
        f"\n\nConstraints:\n{constraints or '- No additional constraints provided.'}"
        f"{interface_block}"
        f"\n\nExample cases:\n{examples_block or 'Use the problem statement and interface above.'}"
        f"\n\nSuggested follow-ups (use if the candidate is doing well):\n{follow_ups or '- No suggested follow-ups.'}"
        f"\n\nPresent this problem in your own words as a natural interviewer would. Do not read it verbatim."
        f"\nBe explicit about the required function or class name if the candidate asks."
    )


def build_study_context(problem):
    """Build the problem context string used by the research/tutor chat."""
    constraints = "\n".join(f"- {c}" for c in problem.get('constraints', []))
    context = (
        f"\n\nThe student is studying this problem:"
        f"\n\nTitle: {problem['title']}"
        f"\nDifficulty: {problem['difficulty']}"
        f"\nCategory: {problem['category']}"
        f"\n\nScenario:\n{problem.get('scenario', '').strip()}"
        f"\n\nProblem:\n{problem.get('description', '').strip()}"
        f"\n\nConstraints:\n{constraints}"
        f"\n\nKey skills: {', '.join(problem.get('key_skills', []))}"
    )
    if problem.get('explanation'):
        context += f"\n\nReference explanation (use to inform your answers):\n{problem['explanation']}"
    if problem.get('references'):
        refs = "\n".join(f"- {ref}" for ref in problem['references'])
        context += f"\n\nReference topics and study material:\n{refs}"
    return context
