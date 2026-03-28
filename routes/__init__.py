from routes.problems import bp as problems_bp
from routes.sessions import bp as sessions_bp
from routes.code import bp as code_bp
from routes.realtime import bp as realtime_bp
from routes.research import bp as research_bp

all_blueprints = [
    problems_bp,
    sessions_bp,
    code_bp,
    realtime_bp,
    research_bp,
]
