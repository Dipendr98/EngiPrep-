from flask import Flask, render_template

import config
from routes import all_blueprints


app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


for bp in all_blueprints:
    app.register_blueprint(bp)


if __name__ == '__main__':
    # Use 'stat' reloader to avoid watchdog triggering spurious restarts
    # when the OpenAI SDK accesses its internal files on Windows.
    app.run(
        debug=config.FLASK_DEBUG,
        port=config.FLASK_PORT,
        use_reloader=True,
        reloader_type='stat',
    )
