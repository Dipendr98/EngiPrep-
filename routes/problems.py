from flask import Blueprint, request, jsonify

from services import problems
from services import problem_generator

bp = Blueprint('problems', __name__)


@bp.route('/api/problems')
def list_problems():
    all_problems = problems.load_all()
    category = request.args.get('category')
    if category:
        all_problems = [p for p in all_problems if p['category'] == category]
    return jsonify([problems.serialize_for_list(p) for p in all_problems])


@bp.route('/api/problems/<int:problem_id>')
def get_problem(problem_id):
    problem = problems.get_by_id(problem_id)
    if not problem:
        return jsonify({'error': 'Problem not found'}), 404
    return jsonify(problems.serialize_full(problem))


@bp.route('/api/problems/generate', methods=['POST'])
def generate_problem():
    """Generate a new AI-powered practice problem.

    Request body (all optional):
        category: str - Problem category (e.g., 'arrays', 'trees', 'dynamic programming')
        difficulty: str - 'Easy', 'Medium', or 'Hard'
        topic: str - Specific topic hint (e.g., 'sliding window', 'BFS')
        count: int - Number of problems to generate (1-5, default 1)
    """
    data = request.get_json(silent=True) or {}
    category = data.get('category')
    difficulty = data.get('difficulty')
    topic = data.get('topic')
    count = data.get('count', 1)

    # Validate inputs
    if difficulty and difficulty not in ('Easy', 'Medium', 'Hard'):
        return jsonify({'error': 'difficulty must be Easy, Medium, or Hard'}), 400
    if count and not isinstance(count, int):
        return jsonify({'error': 'count must be an integer'}), 400
    count = max(1, min(int(count), 5))

    if count == 1:
        result = problem_generator.generate_problem(
            category=category, difficulty=difficulty, topic=topic
        )
        if result and result.get('error'):
            return jsonify(result), 500
        return jsonify({
            'generated': [problems.serialize_for_list(result)],
            'message': f'Generated 1 new problem: {result.get("title", "Unknown")}',
        })
    else:
        results = problem_generator.generate_batch(
            count=count, category=category, difficulty=difficulty
        )
        generated = []
        errors = []
        for r in results:
            if r and r.get('error'):
                errors.append(r['error'])
            else:
                generated.append(problems.serialize_for_list(r))
        return jsonify({
            'generated': generated,
            'errors': errors,
            'message': f'Generated {len(generated)} new problem(s)',
        })


@bp.route('/api/problems/categories')
def list_categories():
    """Return available categories and topics for problem generation."""
    return jsonify({
        'categories': list(problem_generator.TOPIC_POOLS.keys()),
        'topics': problem_generator.TOPIC_POOLS,
        'difficulties': problem_generator.DIFFICULTIES,
    })
