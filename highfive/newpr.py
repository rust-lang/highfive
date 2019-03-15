#!/usr/bin/env python

import urllib2
import cgi
import cgitb
from copy import deepcopy
import json
import random
import ConfigParser
from StringIO import StringIO
import gzip
import re
import os

from highfive import irc, payload

# Maximum per page is 100. Sorted by number of commits, so most of the time the
# contributor will happen early,
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

warning_summary = ':warning: **Warning** :warning:\n\n%s'
submodule_warning_msg = 'These commits modify **submodules**.'
surprise_branch_warning = "Pull requests are usually filed against the %s branch for this repo, but this one is against %s. Please double check that you specified the right target!"

review_with_reviewer = 'r? @%s\n\n(rust_highfive has picked a reviewer for you, use r? to override)'
review_without_reviewer = '@%s: no appropriate reviewer found, use r? to override'

reviewer_re = re.compile("\\b[rR]\?[:\- ]*@([a-zA-Z0-9\-]+)")
submodule_re = re.compile(".*\+Subproject\scommit\s.*", re.DOTALL|re.MULTILINE)

rustaceans_api_url = "http://www.ncameron.org/rustaceans/user?username={username}"

class UnsupportedRepoError(IOError):
    pass

class HighfiveHandler(object):
    def __init__(self, payload, config):
        self.payload = payload

        self.integration_user = config.github_username
        self.integration_token = config.github_token

        self.repo_config = self.load_repo_config()

    def load_repo_config(self):
        '''Load the repository configuration.'''
        (org, repo) = self.payload['repository', 'full_name'].split('/')
        try:
            return self._load_json_file(os.path.join(org, repo) + '.json')
        except IOError:
            raise UnsupportedRepoError

    def run(self, event):
        if event == "ping":
            return "Ping received! The webhook is configured correctly!\n"
        elif event == "pull_request" and self.payload["action"] == "opened":
            self.new_pr()
            return 'OK\n'
        elif event == "issue_comment" and self.payload["action"] == "created":
            self.new_comment()
            return 'OK\n'
        else:
            return 'Unsupported webhook event.\n'

    def _load_json_file(self, name):
        configs_dir = os.path.join(os.path.dirname(__file__), 'configs')

        with open(os.path.join(configs_dir, name)) as config:
            return json.load(config)

    def modifies_submodule(self, diff):
        return submodule_re.match(diff)

    def api_req(self, method, url, data=None, media_type=None):
        data = None if not data else json.dumps(data)
        headers = {} if not data else {'Content-Type': 'application/json'}
        req = urllib2.Request(url, data, headers)
        req.get_method = lambda: method
        if self.integration_token:
            req.add_header("Authorization", "token %s" % self.integration_token)

        if media_type:
            req.add_header("Accept", media_type)
        f = urllib2.urlopen(req)
        header = f.info()
        if header.get('Content-Encoding') == 'gzip':
            buf = StringIO(f.read())
            f = gzip.GzipFile(fileobj=buf)
        body = f.read()
        return { "header": header, "body": body }

    def set_assignee(self, assignee, owner, repo, issue, user, author, to_mention):
        try:
            self.api_req(
                "PATCH", issue_url % (owner, repo, issue),
                {"assignee": assignee}
            )['body']
        except urllib2.HTTPError, e:
            if e.code == 201:
                pass
            else:
                raise e

        if assignee:
            irc_name_of_reviewer = self.get_irc_nick(assignee)
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
            self.post_comment(message, owner, repo, issue)

    def get_irc_nick(self, gh_name):
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

    def is_collaborator(self, commenter, owner, repo):
        """Returns True if `commenter` is a collaborator in the repo."""
        try:
            self.api_req(
                "GET", user_collabo_url % (owner, repo, commenter), None
            )
            return True
        except urllib2.HTTPError, e:
            if e.code == 404:
                return False
            else:
                raise e

    def post_warnings(self, diff, owner, repo, issue):
        warnings = []

        surprise = self.unexpected_branch()
        if surprise:
            warnings.append(surprise_branch_warning % surprise)

        if self.modifies_submodule(diff):
            warnings.append(submodule_warning_msg)

        if warnings:
            self.post_comment(warning_summary % '\n'.join(map(lambda x: '* ' + x, warnings)), owner, repo, issue)

    def post_comment(self, body, owner, repo, issue):
        try:
            self.api_req(
                "POST", post_comment_url % (owner, repo, issue), {"body": body}
            )['body']
        except urllib2.HTTPError, e:
            if e.code == 201:
                pass
            else:
                raise e

    def welcome_msg(self, reviewer):
        if reviewer is None:
            text = welcome_without_reviewer
        else:
            text = welcome_with_reviewer % reviewer
        # Default to the Rust contribution guide if "contributing" wasn't set
        link = self.repo_config.get('contributing')
        if not link:
            link = "https://github.com/rust-lang/rust/blob/master/CONTRIBUTING.md"
        return raw_welcome % (text, link)

    def review_msg(self, reviewer, submitter):
        return review_without_reviewer % submitter if reviewer is None \
            else review_with_reviewer % reviewer

    def unexpected_branch(self):
        """ returns (expected_branch, actual_branch) if they differ, else False
        """

        # If unspecified, assume master.
        expected_target = self.repo_config.get('expected_branch', 'master')

        # ie we want "stable" in this: "base": { "label": "rust-lang:stable"...
        actual_target = self.payload['pull_request', 'base', 'label'].split(':')[1]

        return (expected_target, actual_target) \
            if expected_target != actual_target else False

    def is_new_contributor(self, username, owner, repo):
        # If this is a fork, we do not treat anyone as a new user. This is
        # because the API endpoint called in this function indicates all
        # users in repository forks have zero commits.
        if self.payload['repository', 'fork']:
            return False

        try:
            result = self.api_req(
                'GET', commit_search_url % (owner, repo, username), None,
                'application/vnd.github.cloak-preview'
            )
            return json.loads(result['body'])['total_count'] == 0
        except urllib2.HTTPError, e:
            if e.code == 422:
                return True
            else:
                raise e

    def find_reviewer(self, msg):
        '''
        If the user specified a reviewer, return the username, otherwise returns
        None.
        '''
        if msg is not None:
            match = reviewer_re.search(msg)
            return match.group(1) if match else None

    def choose_reviewer(self, repo, owner, diff, exclude):
        '''Choose a reviewer for the PR.'''
        # Get JSON data on reviewers.
        dirs = self.repo_config.get('dirs', {})
        groups = deepcopy(self.repo_config['groups'])
        mentions = self.repo_config.get('mentions', {})

        # fill in the default groups, ensuring that overwriting is an
        # error.
        global_ = self._load_json_file('_global.json')
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
                            elif (entry.endswith('.rs') and full_dir.endswith(entry)
                                  and entry not in to_mention):
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

    def add_labels(self, owner, repo, issue):
        self.api_req(
            'POST', issue_labels_url % (owner, repo, issue),
            self.repo_config['new_pr_labels']
        )

    def new_pr(self):
        owner = self.payload['pull_request', 'base', 'repo', 'owner', 'login']
        repo = self.payload['pull_request', 'base', 'repo', 'name']

        author = self.payload['pull_request', 'user', 'login']
        issue = str(self.payload["number"])
        diff = self.api_req(
            "GET", self.payload["pull_request", "url"], None,
            "application/vnd.github.v3.diff",
        )['body']

        if not self.payload['pull_request', 'assignees']:
            # Only try to set an assignee if one isn't already set.
            msg = self.payload['pull_request', 'body']
            reviewer = self.find_reviewer(msg)
            post_msg = False
            to_mention = None

            if not reviewer:
                post_msg = True
                reviewer, to_mention = self.choose_reviewer(
                    repo, owner, diff, author
                )

            self.set_assignee(
                reviewer, owner, repo, issue, self.integration_user,
                author, to_mention
            )

            if self.is_new_contributor(author, owner, repo):
                self.post_comment(
                    self.welcome_msg(reviewer), owner, repo, issue
                )
            elif post_msg:
                self.post_comment(
                    self.review_msg(reviewer, author), owner, repo, issue
                )

        self.post_warnings(diff, owner, repo, issue)

        if self.repo_config.get("new_pr_labels"):
            self.add_labels(owner, repo, issue)

    def new_comment(self):
        # Check the issue is a PR and is open.
        if self.payload['issue', 'state'] != 'open' \
           or 'pull_request' not in self.payload['issue']:
            return

        commenter = self.payload['comment', 'user', 'login']
        # Ignore our own comments.
        if commenter == self.integration_user:
            return

        owner = self.payload['repository', 'owner', 'login']
        repo = self.payload['repository', 'name']

        # Check the commenter is the submitter of the PR or the previous assignee.
        author = self.payload['issue', 'user', 'login']
        if not (author == commenter or (
                    self.payload['issue', 'assignee'] \
                    and commenter == self.payload['issue', 'assignee', 'login']
        )):
            # Check if commenter is a collaborator.
            if not self.is_collaborator(commenter, owner, repo):
                return

        # Check for r? and set the assignee.
        msg = self.payload['comment', 'body']
        reviewer = self.find_reviewer(msg)
        if reviewer:
            issue = str(self.payload['issue', 'number'])
            self.set_assignee(
                reviewer, owner, repo, issue, self.integration_user,
                author, None
            )
