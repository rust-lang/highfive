from __future__ import print_function

import datetime
import hashlib
import hmac
import json
import sys
import traceback

import click
import dotenv
import flask
import waitress

from .config import Config, InvalidTokenException
from .newpr import HighfiveHandler, UnsupportedRepoError
from .payload import Payload


def create_app(config, webhook_secrets=None, config_dir=None):
    if webhook_secrets is None:
        webhook_secrets = []

    app = flask.Flask(__name__)

    # The canonical URL is /webhook, but other URLs are accepted for backward
    # compatibility.
    @app.route("/webhook", methods=['POST'])
    @app.route("/newpr.py", methods=['POST'])
    @app.route("/highfive/newpr.py", methods=['POST'])
    def new_pr():
        raw_data = flask.request.get_data()

        # Load all the headers
        try:
            event = str(flask.request.headers['X-GitHub-Event'])
            delivery = str(flask.request.headers['X-GitHub-Delivery'])
            signature = str(flask.request.headers['X-Hub-Signature'])
        except KeyError:
            return 'Error: some required webhook headers are missing\n', 400

        # Check the signature only if the secret is configured
        if 'payload' in flask.request.form and webhook_secrets:
            for webhook_secret in webhook_secrets:
                expected = hmac.new(webhook_secret.encode("utf-8"), digestmod=hashlib.sha1)
                expected.update(raw_data)
                expected = expected.hexdigest()
                if hmac.compare_digest('sha1=' + expected, signature):
                    break
            else:
                return 'Error: invalid signature\n', 403
        try:
            payload = json.loads(flask.request.form['payload'])
        except (KeyError, ValueError):
            return 'Error: missing or invalid payload\n', 400
        try:
            handler = HighfiveHandler(Payload(payload), config, config_dir)
            return handler.run(event)
        except UnsupportedRepoError:
            return 'Error: this repository is not configured!\n', 400
        except:
            print()
            print('An exception occured while processing a webhook!')
            print('Time:', datetime.datetime.now())
            print('Delivery ID:', delivery)
            print('Event name:', event)
            print('Payload:', json.dumps(payload))
            print(traceback.format_exc())
            return 'Internal server error\n', 500

    @app.route('/')
    def index():
        return 'Welcome to highfive!\n'

    return app


@click.command()
@click.option('--port', default=8000)
@click.option('--github-token', required=True)
@click.option("webhook_secrets", "--webhook-secret", multiple=True)
@click.option("--config-dir")
def cli(port, github_token, webhook_secrets, config_dir):
    try:
        config = Config(github_token)
    except InvalidTokenException:
        print('error: invalid github token provided!')
        sys.exit(1)
    print('Found a valid GitHub token for user @' + config.github_username)

    app = create_app(config, webhook_secrets, config_dir)
    waitress.serve(app, port=port)


def main():
    dotenv.load_dotenv()
    cli(auto_envvar_prefix='HIGHFIVE')
