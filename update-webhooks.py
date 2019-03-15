#!/usr/bin/env python3
#
# This script goes over all the repositories in the highfive configuration and
# sets the webhook to point to the highfive instance
#

# URLs of old highfive instances
# Webhooks with this URL will be edited to point to the new instance
REPLACE_OLD_URLS = [
    "https://www.ncameron.org/highfive/newpr.py",
    "https://internal-secret-rust-bots.rust-lang.org/highfive/newpr.py",
]

# URL of the current instance
CURRENT_URL = "https://highfive.infra.rust-lang.org/webhook"

# Events the current instance requires
EVENTS = [
    "issue_comment",
    "pull_request",
]

import json
import os
import requests

class GitHubApi:
    def __init__(self, token):
        self.token = token
        self.client = requests.Session()

    def req(self, method, url, *args, data=None):
        """Make a request against the GitHub API"""
        if not url.startswith("https://"):
            url = "https://api.github.com/%s" % url
        url = url % args
        resp = self.client.request(method, url, json=data, headers={
            "Authorization": "token %s" % self.token,
        })
        return resp.json()

def find_config_files(path):
    """Return all the configuration files in a directory"""
    result = []
    for file in os.listdir(path):
        if file[0] == "_":
            continue
        file = os.path.join(path, file)
        if os.path.isdir(file):
            result += find_config_files(file)
        elif file.endswith(".json"):
            result.append(file)
    return result

def update_webhook(config, api, secret):
    """Update the webhook of a single file"""
    name = os.path.basename(config).rsplit(".", 1)[0]
    org = os.path.basename(os.path.dirname(config))

    hooks = api.req("GET", "repos/%s/%s/hooks", org, name)
    replace = None
    if "message" in hooks:
        print("Error: can't access %s/%s, do you have admin perms on the repo?" % (org, name))
        return
    for hook in hooks:
        if "url" not in hook["config"]:
            continue
        url = hook["config"]["url"]

        if url == CURRENT_URL:
            # Update the webhook if the events changed
            if hook["events"] != EVENTS:
                replace = hook["id"]
                break
            print("Already correct: %s/%s" % (org, name))
            return
        elif url in REPLACE_OLD_URLS:
            # Found the hook to replace
            replace = hook["id"]
            break

    if replace is None:
        api.req("POST", "repos/%s/%s/hooks", org, name, data={
            "config": {
                "url": CURRENT_URL,
                "secret": secret,
                "content_type": "form",
                "insecure_ssl": 0,
            },
            "events": EVENTS,
            "active": True,
        })
        print("Added: %s/%s" % (org, name))
    else:
        api.req("PATCH", "repos/%s/%s/hooks/%s", org, name, replace, data={
            "config": {
                "url": CURRENT_URL,
                "secret": secret,
                "content_type": "form",
                "insecure_ssl": 0,
            },
            "events": EVENTS,
            "active": True,
        })
        print("Fixed: %s/%s" % (org, name))

if __name__ == "__main__":
    if "GITHUB_TOKEN" not in os.environ:
        print("Error: you need to set the $GITHUB_TOKEN env var!")
        exit(1)
    api = GitHubApi(os.environ["GITHUB_TOKEN"])

    secret = input("Please enter the webhooks' secret key: ")

    for config in find_config_files("highfive/configs"):
        update_webhook(config, api, secret)
