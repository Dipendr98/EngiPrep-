from flask import Blueprint, request, jsonify

from services import problems

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
