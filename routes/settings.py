from flask import Blueprint, jsonify

from services.ai import PROVIDER_PRESETS

bp = Blueprint('settings', __name__)


@bp.route('/api/providers')
def list_providers():
    """Return the list of supported AI provider presets."""
    return jsonify(PROVIDER_PRESETS)