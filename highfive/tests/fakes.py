from highfive import payload
import json
import os

def get_fake_filename(name):
    return os.path.join(os.path.dirname(__file__), 'fakes', name)

def get_repo_configs():
    return {
        'individuals_no_dirs': {
            "groups": { "all": ["@pnkfelix", "@nrc"] },
            "dirs": {},
        },
        'individuals_dirs': {
            "groups": { "all": ["@pnkfelix", "@nrc"] },
            "dirs": { "librustc": ["@aturon"] },
        },
        'individuals_dirs_2': {
            "groups": { "all": ["@pnkfelix", "@nrc"] },
            "dirs": { "foobazdir": ["@aturon"] },
        },
        'circular_groups': {
            "groups": {
                "all": ["some"],
                "some": ["all"],
            },
        },
        'empty': {
            "groups": { "all": [] },
            "dirs": {},
        },
    }

def get_global_configs():
    return {
        'base': {
            "groups": {
                "core": ["@alexcrichton"],
            }
        },
        'has_all': {
            "groups": { "all": ["@alexcrichton"] }
        },
    }

class Payload(object):
    @staticmethod
    def new_pr(
        number=7, pr_body='The PR comment.', pr_url='https://the.url/',
        repo_name='repo-name', repo_owner='repo-owner', pr_author='prAuthor'
    ):
        with open(get_fake_filename('open-pr.payload'), 'r') as fin:
            p = json.load(fin)

        p['number'] = number
        p['pull_request']['body'] = pr_body
        p['pull_request']['url'] = pr_url
        p['pull_request']['base']['repo']['name'] = repo_name
        p['pull_request']['base']['repo']['owner']['login'] = repo_owner
        p['pull_request']['user']['login'] = pr_author

        return payload.Payload(p)
