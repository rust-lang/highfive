import hashlib
import hmac
import json
import sys

from .config import Config, InvalidTokenException
from .newpr import HighfiveHandler, UnsupportedRepoError
from .payload import Payload

import click
import dotenv
import flask
import waitress


def create_app(config, webhook_secret=None, config_dir=None):
    app = flask.Flask(__name__)

    # The canonical URL is /webhook, but other URLs are accepted for backward
    # compatibility.
    @app.route("/webhook", methods=['POST'])
    @app.route("/newpr.py", methods=['POST'])
    @app.route("/highfive/newpr.py", methods=['POST'])
    def new_pr():
        raw_data = flask.request.get_data()

        # Check the signature only if the secret is configured
        if 'payload' in flask.request.form and webhook_secret is not None:
            expected = hmac.new(str(webhook_secret), digestmod=hashlib.sha1)
            expected.update(raw_data)
            expected = expected.hexdigest()
            try:
                signature = str(flask.request.headers['X-Hub-Signature'])
            except KeyError:
                return 'Error: missing signature\n', 400
            if not hmac.compare_digest('sha1='+expected, signature):
                return 'Error: invalid signature\n', 403

        try:
            payload = json.loads(flask.request.form['payload'])
        except (KeyError, ValueError), _:
            return 'Error: missing or invalid payload\n', 400
        try:
            handler = HighfiveHandler(Payload(payload), config, config_dir)
            return handler.run(flask.request.headers['X-GitHub-Event'])
        except UnsupportedRepoError:
            return 'Error: this repository is not configured!\n', 400

    @app.route('/')
    def index():
        return 'Welcome to highfive!\n'

    return app


@click.command()
@click.option('--port', default=8000)
@click.option('--github-token', required=True)
@click.option("--webhook-secret")
@click.option("--config-dir")
def cli(port, github_token, webhook_secret, config_dir):
    try:
        config = Config(github_token)
    except InvalidTokenException:
        print 'error: invalid github token provided!'
        sys.exit(1)
    print 'Found a valid GitHub token for user @' + config.github_username

    app = create_app(config, webhook_secret, config_dir)
    waitress.serve(app, port=port)


def main():
    dotenv.load_dotenv()
    cli(auto_envvar_prefix='HIGHFIVE')
