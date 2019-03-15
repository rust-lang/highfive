import requests


class InvalidTokenException(Exception):
    pass


class Config(object):
    def __init__(self, github_token):
        if not github_token:
            raise InvalidTokenException()
        self.github_token = github_token
        self.github_username = self.fetch_github_username()

    def fetch_github_username(self):
        response = requests.get('https://api.github.com/user', headers={
            'Authorization': 'token ' + self.github_token
        })
        if response.status_code != 200:
            raise InvalidTokenException()
        return response.json()['login']
