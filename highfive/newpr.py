#!/usr/bin/env python

import urllib, urllib2
import cgi
import cgitb
import json
import random
import sys
import ConfigParser
from StringIO import StringIO
import gzip
import re
import time
import socket
import os

from highfive import irc, payload

# Maximum per page is 100. Sorted by number of commits, so most of the time the
# contributor will happen early,
contributors_url = "https://api.github.com/repos/%s/%s/contributors?per_page=100"
post_comment_url = "https://api.github.com/repos/%s/%s/issues/%s/comments"
user_collabo_url = "https://api.github.com/repos/%s/%s/collaborators/%s"
issue_url = "https://api.github.com/repos/%s/%s/issues/%s"
issue_labels_url = "https://api.github.com/repos/%s/%s/issues/%s/labels"
commit_search_url = "https://api.github.com/search/commits?q=repo:%s/%s+author:%s"

welcome_with_reviewer = '@%s (or someone else)'
welcome_without_reviewer = "@nrc (NB. this repo may be misconfigured)"
raw_welcome = """Thanks for the pull request, and welcome! The Rust team is excited to review your changes, and you should hear from %s soon.

If any changes to this PR are deemed necessary, please add them as extra commits. This ensures that the reviewer can see what has changed since they last reviewed the code. Due to the way GitHub handles out-of-date commits, this should also make it reasonably obvious what issues have or haven't been addressed. Large or tricky changes may require several passes of review and changes.

Please see [the contribution instructions](%s) for more information.
"""


def welcome_msg(reviewer, config):
    if reviewer is None:
        text = welcome_without_reviewer
    else:
        text = welcome_with_reviewer % reviewer
    # Default to the Rust contribution guide if "contributing" wasn't set
    link = config.get('contributing')
    if not link:
        link = "https://github.com/rust-lang/rust/blob/master/CONTRIBUTING.md"
    return raw_welcome % (text, link)

warning_summary = ':warning: **Warning** :warning:\n\n%s'
submodule_warning_msg = 'These commits modify **submodules**.'
surprise_branch_warning = "Pull requests are usually filed against the %s branch for this repo, but this one is against %s. Please double check that you specified the right target!"


review_with_reviewer = 'r? @%s\n\n(rust_highfive has picked a reviewer for you, use r? to override)'
review_without_reviewer = '@%s: no appropriate reviewer found, use r? to override'

def review_msg(reviewer, submitter):
    return review_without_reviewer % submitter if reviewer is None \
        else review_with_reviewer % reviewer

reviewer_re = re.compile("\\b[rR]\?[:\- ]*@([a-zA-Z0-9\-]+)")
submodule_re = re.compile(".*\+Subproject\scommit\s.*", re.DOTALL|re.MULTILINE)

rustaceans_api_url = "http://www.ncameron.org/rustaceans/user?username={username}"


def _load_json_file(name):
    configs_dir = os.path.join(os.path.dirname(__file__), 'configs')

    with open(os.path.join(configs_dir, name)) as config:
        return json.load(config)

def api_req(method, url, data=None, token=None, media_type=None):
    data = None if not data else json.dumps(data)
    headers = {} if not data else {'Content-Type': 'application/json'}
    req = urllib2.Request(url, data, headers)
    req.get_method = lambda: method
    if token:
        req.add_header("Authorization", "token %s" % token)

    if media_type:
        req.add_header("Accept", media_type)
    f = urllib2.urlopen(req)
    header = f.info()
    if header.get('Content-Encoding') == 'gzip':
        buf = StringIO(f.read())
        f = gzip.GzipFile(fileobj=buf)
    body = f.read()
    return { "header": header, "body": body }

def post_comment(body, owner, repo, issue, token):
    try:
        api_req("POST", post_comment_url % (owner, repo, issue), {"body": body}, token)['body']
    except urllib2.HTTPError, e:
        if e.code == 201:
            pass
        else:
            raise e

def set_assignee(assignee, owner, repo, issue, user, token, author, to_mention):
    try:
        api_req("PATCH", issue_url % (owner, repo, issue), {"assignee": assignee}, token)['body']
    except urllib2.HTTPError, e:
        if e.code == 201:
            pass
        else:
            raise e

    if assignee:
        irc_name_of_reviewer = get_irc_nick(assignee)
        if irc_name_of_reviewer:
            client = irc.IrcClient(target="#rust-bots")
            client.send_then_quit("{}: ping to review issue https://www.github.com/{}/{}/pull/{} by {}."
                .format(irc_name_of_reviewer, owner, repo, issue, author))

    if to_mention and len(to_mention) > 0:
        message = ''
        for mention in to_mention:
            if len(message) > 0:
                message += '\n\n'
            message += "%s\n\ncc %s" % (mention['message'],
                                        ','.join([x for x in mention['reviewers'] if x != user]))
        post_comment(message, owner, repo, issue, token)

def is_collaborator(commenter, owner, repo, token):
    """Returns True if `commenter` is a collaborator in the repo."""
    try:
        api_req("GET", user_collabo_url % (owner, repo, commenter), None, token)
        return True
    except urllib2.HTTPError, e:
        if e.code == 404:
            return False
        else:
            raise e

def add_labels(labels, owner, repo, issue, token):
    api_req("POST", issue_labels_url % (owner, repo, issue), labels, token)

def is_new_contributor(username, owner, repo, token, payload):
    # If this is a fork, we do not treat anyone as a new user. This is
    # because the API endpoint called in this function indicates all
    # users in repository forks have zero commits.
    if payload['repository', 'fork']:
        return False

    try:
        result = api_req(
            'GET', commit_search_url % (owner, repo, username), None, token,
            'application/vnd.github.cloak-preview'
        )
        return json.loads(result['body'])['total_count'] == 0
    except urllib2.HTTPError, e:
        if e.code == 422:
            return True
        else:
            raise e

# If the user specified a reviewer, return the username, otherwise returns None.
def find_reviewer(msg):
    match = reviewer_re.search(msg)
    return match.group(1) if match else None

# Choose a reviewer for the PR
def choose_reviewer(repo, owner, diff, exclude, config):
    if not (owner == 'rust-lang' or \
            owner == 'rust-lang-nursery' or \
            owner == 'rust-lang-deprecated' or \
            (owner == 'nrc' and repo == 'highfive')):
        return ('test_user_selection_ignore_this', None)

    # Get JSON data on reviewers.
    dirs = config.get('dirs', {})
    groups = config['groups']
    mentions = config.get('mentions', {})

    # fill in the default groups, ensuring that overwriting is an
    # error.
    global_ = _load_json_file('_global.json')
    for name, people in global_['groups'].iteritems():
        assert name not in groups, "group %s overlaps with _global.json" % name
        groups[name] = people


    most_changed = None
    to_mention = []
    # If there's directories with specially assigned groups/users
    # inspect the diff to find the directory (under src) with the most
    # additions
    if dirs:
        counts = {}
        cur_dir = None
        for line in diff.split('\n'):
            if line.startswith("diff --git "):
                # update cur_dir
                cur_dir = None
                start = line.find(" b/src/") + len(" b/src/")
                if start == -1:
                    continue
                end = line.find("/", start)
                if end == -1:
                    continue
                full_end = line.rfind("/", start)

                cur_dir = line[start:end]
                full_dir = line[start:full_end] if full_end != -1 else ""

                # A few heuristics to get better reviewers
                if cur_dir.startswith('librustc'):
                    cur_dir = 'librustc'
                if cur_dir == 'test':
                    cur_dir = None
                if len(full_dir) > 0:
                    for entry in mentions:
                        if full_dir.startswith(entry) and entry not in to_mention:
                            to_mention.append(entry)
                if cur_dir and cur_dir not in counts:
                    counts[cur_dir] = 0
                continue

            if cur_dir and (not line.startswith('+++')) and line.startswith('+'):
                counts[cur_dir] += 1

        # Find the largest count.
        most_changes = 0
        for dir, changes in counts.iteritems():
            if changes > most_changes:
                most_changes = changes
                most_changed = dir

    # lookup that directory in the json file to find the potential reviewers
    potential = groups['all']
    if most_changed and most_changed in dirs:
        potential.extend(dirs[most_changed])
    if not potential:
        potential = groups['core']


    # expand the reviewers list by group
    reviewers = []
    seen = {"all"}
    while potential:
        p = potential.pop()
        if p.startswith('@'):
            # remove the '@' prefix from each username
            reviewers.append(p[1:])
        elif p in groups:
            # avoid infinite loops
            assert p not in seen, "group %s refers to itself" % p
            seen.add(p)
            # we allow groups in groups, so they need to be queued to be resolved
            potential.extend(groups[p])

    if exclude in reviewers:
        reviewers.remove(exclude)

    if reviewers:
        random.seed()
        mention_list = []
        for mention in to_mention:
            mention_list.append(mentions[mention])
        return (random.choice(reviewers), mention_list)
    # no eligible reviewer found
    return (None, None)

def modifies_submodule(diff):
    return submodule_re.match(diff)

def unexpected_branch(payload, config):
    """ returns (expected_branch, actual_branch) if they differ, else False
    """

    # If unspecified, assume master.
    expected_target = config.get('expected_branch', 'master')

    # ie we want "stable" in this: "base": { "label": "rust-lang:stable"...
    actual_target = payload['pull_request', 'base', 'label'].split(':')[1]

    return (expected_target, actual_target) \
        if expected_target != actual_target else False

def get_irc_nick(gh_name):
    """ returns None if the request status code is not 200,
     if the user does not exist on the rustacean database,
     or if the user has no `irc` field associated with their username
    """
    try:
        data = urllib2.urlopen(rustaceans_api_url.format(username=gh_name))
        if data.getcode() == 200:
            rustacean_data = json.loads(data.read())
            if rustacean_data:
                return rustacean_data[0].get("irc")
    except urllib2.HTTPError:
        pass

    return None

def post_warnings(payload, config, diff, owner, repo, issue, token):
    warnings = []

    surprise = unexpected_branch(payload, config)
    if surprise:
        warnings.append(surprise_branch_warning % surprise)

    if modifies_submodule(diff):
        warnings.append(submodule_warning_msg)

    if warnings:
        post_comment(warning_summary % '\n'.join(map(lambda x: '* ' + x, warnings)), owner, repo, issue, token)

def new_pr(payload, user, token):
    owner = payload['pull_request', 'base', 'repo', 'owner', 'login']
    repo = payload['pull_request', 'base', 'repo', 'name']

    author = payload['pull_request', 'user', 'login']
    issue = str(payload["number"])
    diff = api_req(
        "GET", payload["pull_request", "url"], None, token,
        "application/vnd.github.v3.diff",
    )['body']

    msg = payload['pull_request', 'body']
    reviewer = find_reviewer(msg)
    post_msg = False
    to_mention = None

    config = _load_json_file(repo + '.json')

    if not reviewer:
        post_msg = True
        reviewer, to_mention = choose_reviewer(repo, owner, diff, author, config)

    set_assignee(reviewer, owner, repo, issue, user, token, author, to_mention)

    if is_new_contributor(author, owner, repo, token, payload):
        post_comment(welcome_msg(reviewer, config), owner, repo, issue, token)
    elif post_msg:
        post_comment(review_msg(reviewer, author), owner, repo, issue, token)

    post_warnings(payload, config, diff, owner, repo, issue, token)

    if config.get("new_pr_labels"):
        add_labels(config["new_pr_labels"], owner, repo, issue, token)


def new_comment(payload, user, token):
    # Check the issue is a PR and is open.
    if payload['issue', 'state'] != 'open' or 'pull_request' not in payload['issue']:
        return

    commenter = payload['comment', 'user', 'login']
    # Ignore our own comments.
    if commenter == user:
        return

    owner = payload['repository', 'owner', 'login']
    repo = payload['repository', 'name']

    # Check the commenter is the submitter of the PR or the previous assignee.
    author = payload['issue', 'user', 'login']
    if not (author == commenter or (payload['issue', 'assignee'] and commenter == payload['issue', 'assignee', 'login'])):
        # Check if commenter is a collaborator.
        if not is_collaborator(commenter, owner, repo, token):
            return

    # Check for r? and set the assignee.
    msg = payload['comment', 'body']
    reviewer = find_reviewer(msg)
    if reviewer:
        issue = str(payload['issue', 'number'])
        set_assignee(reviewer, owner, repo, issue, user, token, author, None)

class HighfiveHandler(object):
    def __init__(self, payload):
        self.payload = payload

        self.config = ConfigParser.RawConfigParser()
        self.config.read('./config')

    def run(self):
        user = self.config.get('github', 'user')
        token = self.config.get('github', 'token')

        if self.payload["action"] == "opened":
            new_pr(self.payload, user, token)
        elif self.payload["action"] == "created":
            new_comment(self.payload, user, token)
        else:
            print self.payload["action"]
            sys.exit(0)


if __name__ == "__main__":
    print "Content-Type: text/html;charset=utf-8"
    print

    cgitb.enable()

    post = cgi.FieldStorage()
    payload_raw = post.getfirst("payload",'')
    handler = HighfiveHandler(payload.Payload(json.loads(payload_raw)))
    handler.run()
