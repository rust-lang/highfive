import json

from .newpr import HighfiveHandler, UnsupportedRepoError
from .payload import Payload

import click
import dotenv
import flask
import waitress


def create_app():
    app = flask.Flask(__name__)

    # The canonical URL is /webhook, but other URLs are accepted for backward
    # compatibility.
    @app.route("/webhook", methods=['POST'])
    @app.route("/newpr.py", methods=['POST'])
    @app.route("/highfive/newpr.py", methods=['POST'])
    def new_pr():
        try:
            payload = json.loads(flask.request.form['payload'])
        except (KeyError, ValueError), _:
            return 'Error: missing or invalid payload\n', 400
        try:
            handler = HighfiveHandler(Payload(payload))
            return handler.run(flask.request.headers['X-GitHub-Event'])
        except UnsupportedRepoError:
            return 'Error: this repository is not configured!\n', 400

    @app.route('/')
    def index():
        return 'Welcome to highfive!\n'

    return app


@click.command()
@click.option('--port', default=8000)
def cli(port):
    app = create_app()
    waitress.serve(app, port=port)


def main():
    dotenv.load_dotenv()
    cli(auto_envvar_prefix='HIGHFIVE')
