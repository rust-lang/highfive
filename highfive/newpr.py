#!/usr/bin/env python3

import gzip
import json
import os
import random
import re
import urllib
from configparser import ConfigParser
from copy import deepcopy
from io import StringIO

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

Please see [the contribution instructions](%s) for more information.
"""

warning_summary = ':warning: **Warning** :warning:\n\n%s'
submodule_warning_msg = 'These commits modify **submodules**.'
targets_warning_msg = 'These commits modify **compiler targets**. (See the [Target Tier Policy](https://doc.rust-lang.org/nightly/rustc/target-tier-policy.html).)'
surprise_branch_warning = "Pull requests are usually filed against the %s branch for this repo, but this one is against %s. Please double check that you specified the right target!"

review_with_reviewer = 'r? @%s\n\n(rust-highfive has picked a reviewer for you, use r? to override)'
review_without_reviewer = '@%s: no appropriate reviewer found, use r? to override'

reviewer_re = re.compile(r"\b[rR]\?[:\- ]*(?:@?([a-zA-Z0-9\-]+)/)?(@?[a-zA-Z0-9\-]+)")
submodule_re = re.compile(r".*\+Subproject\scommit\s.*", re.DOTALL | re.MULTILINE)
target_re = re.compile("^[+-]{3} [ab]/compiler/rustc_target/src/spec/", re.MULTILINE)

class UnsupportedRepoError(IOError):
    pass


class HighfiveHandler(object):
    def __init__(self, payload, config, config_dir=None):
        self.payload = payload

        self.integration_user = config.github_username
        self.integration_token = config.github_token

        self.config_dir = config_dir
        self.repo_config = self.load_repo_config()

    def load_repo_config(self):
        """Load the repository configuration."""
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
            return 'OK, handled new PR\n'
        elif event == "issue_comment" and self.payload["action"] == "created":
            msg = self.new_comment()
            if msg is None:
                return 'OK\n'
            else:
                return f"OK: {msg}\n"
        else:
            return 'Unsupported webhook event.\n'

    def _load_json_file(self, name):
        config_dir = self.config_dir
        if not self.config_dir:
            config_dir = os.path.join(os.path.dirname(__file__), 'configs')

        with open(os.path.join(config_dir, name)) as config:
            return json.load(config)

    def modifies_submodule(self, diff):
        return submodule_re.match(diff)

    def modifies_targets(self, diff):
        return target_re.search(diff)

    def api_req(self, method, url, data=None, media_type=None):
        data = None if not data else json.dumps(data).encode("utf-8")
        headers = {} if not data else {'Content-Type': 'application/json'}
        req = urllib.request.Request(url, data, headers)
        req.get_method = lambda: method
        if self.integration_token:
            req.add_header("Authorization", "token %s" % self.integration_token)

        if media_type:
            req.add_header("Accept", media_type)
        f = urllib.request.urlopen(req)
        header = f.info()
        if header.get('Content-Encoding') == 'gzip':
            buf = StringIO(f.read())
            f = gzip.GzipFile(fileobj=buf)
        body = f.read().decode("utf-8")
        return {"header": header, "body": body}

    def set_assignee(self, assignee, owner, repo, issue, user, author, to_mention):
        if assignee == 'ghost':
            raise Exception("Skipping assignment: ghost user disables automation").with_traceback(None)

        try:
            self.api_req(
                "PATCH", issue_url % (owner, repo, issue),
                {"assignee": assignee}
            )['body']
        except urllib.error.HTTPError as e:
            if e.code == 201:
                pass
            else:
                print(f"failed to assign {assignee} to {owner}/{repo}#{issue}")
                raise e

        self.run_commands(to_mention, owner, repo, issue, user)

    def run_commands(self, to_mention, owner, repo, issue, user):
        commands = {}
        if to_mention and len(to_mention) > 0:
            message = ''
            for mention in to_mention:
                if len(message) > 0:
                    message += '\n\n'
                msg = mention.get('message')
                reviewers = [x for x in mention['reviewers'] if x != user]

                if msg is not None:
                    if len(reviewers) > 0:
                        msg += '\n\n'
                else:
                    msg = ''

                if len(reviewers) > 0:
                    message += "%scc %s" % (msg, ','.join(reviewers))
                else:
                    message += msg

                cmd = mention.get('command')
                if cmd is not None:
                    commands[cmd] = self.payload['pull_request', 'head', 'sha']
            for cmd in commands:
                if len(message) > 0:
                    message += '\n\n'
                message += "%s %s" % (cmd, commands[cmd])
            if len(message) > 0:
                self.post_comment(message, owner, repo, issue)

    def is_collaborator(self, commenter, owner, repo):
        """Returns True if `commenter` is a collaborator in the repo."""
        try:
            self.api_req(
                "GET", user_collabo_url % (owner, repo, commenter), None
            )
            return True
        except urllib.error.HTTPError as e:
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

        if self.modifies_targets(diff):
            warnings.append(targets_warning_msg)

        if warnings:
            self.post_comment(warning_summary % '\n'.join(map(lambda x: '* ' + x, warnings)), owner, repo, issue)

    def post_comment(self, body, owner, repo, issue):
        try:
            self.api_req(
                "POST", post_comment_url % (owner, repo, issue), {"body": body}
            )['body']
        except urllib.error.HTTPError as e:
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
            link = "https://rustc-dev-guide.rust-lang.org/contributing.html"
        return raw_welcome % (text, link)

    def review_msg(self, reviewer, submitter):
        return review_without_reviewer % submitter if reviewer is None \
            else review_with_reviewer % reviewer

    def unexpected_branch(self):
        """ returns (expected_branch, actual_branch) if they differ, else False"""

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
        except urllib.error.HTTPError as e:
            if e.code == 422:
                return True
            else:
                raise e

    def get_groups(self):
        groups = deepcopy(self.repo_config['groups'] if 'groups' in self.repo_config else {})

        # fill in the default groups, ensuring that overwriting is an
        # error.
        global_ = self._load_json_file('_global.json')
        for name, people in global_['groups'].items():
            assert name not in groups, "group %s overlaps with _global.json" % name
            groups[name] = people

        return groups

    def find_reviewer(self, msg, exclude):
        """
        If the user specified a reviewer, return the username, otherwise returns
        None.
        """
        if msg is not None:
            match = reviewer_re.search(msg)
            if match:
                groups = self.get_groups()
                potential = groups.get(match.group(2)) or groups.get("%s/%s" % (match.group(1), match.group(2))) or []
                picked = self.pick_reviewer(groups, potential, exclude)
                if picked:
                    return picked
                if match.group(1) is None and match.group(2):
                    if match.group(2).startswith('@'):
                        return match.group(2)[1:]


    def choose_reviewer(self, repo, owner, diff, exclude):
        """Choose a reviewer for the PR."""
        # Get JSON data on reviewers.
        dirs = self.repo_config.get('dirs', {})
        groups = self.get_groups()

        # Map of `dirs` path to the number of changes found in that path.
        counts = {}
        # If there's directories with specially assigned groups/users
        # inspect the diff to find the directory with the most additions
        if dirs:
            # List of the longest `dirs` paths that match the current path.
            # This is a list to handle the situation if multiple paths of the
            # same length match.
            longest_dir_paths = []
            for line in diff.split('\n'):
                if line.startswith("diff --git "):
                    # update longest_dir_paths
                    longest_dir_paths = []
                    parts = line[line.find(" b/") + len(" b/"):].split("/")
                    if not parts:
                        continue

                    # Find the longest `dirs` entries that match this path.
                    longest = {}
                    for dir_path in dirs:
                        dir_parts = dir_path.split('/')
                        if parts[:len(dir_parts)] == dir_parts:
                            longest[dir_path] = len(dir_parts)
                    max_count = max(longest.values(), default=0)
                    longest_dir_paths = [
                        path for (path, count) in longest.items()
                            if count == max_count
                    ]
                    continue

                if ((not line.startswith('+++')) and line.startswith('+')) or \
                   ((not line.startswith('---')) and line.startswith('-')):
                    for path in longest_dir_paths:
                        counts[path] = counts.get(path, 0) + 1

        # `all` is always included.
        potential = groups['all']
        # Include the `dirs` entries with the maximum number of matches.
        max_count = max(counts.values(), default=0)
        max_paths = [path for (path, count) in counts.items() if count == max_count]
        for path in max_paths:
            potential.extend(dirs[path])
        if not potential:
            potential = groups['core']

        return self.pick_reviewer(groups, potential, exclude)

    def pick_reviewer(self, groups, potential, exclude):
        # expand the reviewers list by group
        reviewers = []
        seen = {"all"}
        while potential:
            p = potential.pop()
            if p.startswith('@'):
                # remove the '@' prefix from each username
                username = p[1:]

                # If no one should be excluded add the reviewer
                if exclude == None:
                    reviewers.append(username)

                # ensure we don't assign someone to their own PR due with a case-insensitive test
                elif username.lower() != exclude.lower():
                    reviewers.append(username)
            elif p in groups:
                # avoid infinite loops
                if p not in seen:
                    seen.add(p)
                    # we allow groups in groups, so they need to be queued to be resolved
                    potential.extend(groups[p])

        if reviewers:
            random.seed()
            return random.choice(reviewers)
        # no eligible reviewer found
        return None

    def get_to_mention(self, diff, author):
        """
        Get the list of people to mention.
        """
        mentions = self.repo_config.get('mentions', {})
        if not mentions:
            return []

        to_mention = set()
        # If there's directories with specially assigned groups/users
        # inspect the diff to find the directory with the most additions
        for line in diff.split('\n'):
            if line.startswith("diff --git "):
                parts = line[line.find(" b/") + len(" b/"):].split("/")
                if not parts:
                    continue
                full_dir = "/".join(parts)

                if len(full_dir) > 0:
                    for entry in mentions:
                        # Check if this entry is a prefix
                        eparts = entry.split("/")
                        if (len(eparts) <= len(parts) and
                            all(a==b for a,b in zip(parts, eparts))
                        ):
                            to_mention.add(entry)
                        elif entry.endswith('.rs') and full_dir.endswith(entry):
                            to_mention.add(entry)

        mention_list = []
        for mention in to_mention:
            entry = mentions[mention]
            if author not in entry["reviewers"]:
                mention_list.append(entry)
        return mention_list

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
            reviewer = self.find_reviewer(msg, author)
            post_msg = False

            if not reviewer:
                post_msg = True
                reviewer = self.choose_reviewer(
                    repo, owner, diff, author
                )
            to_mention = self.get_to_mention(diff, author)

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
            return "skipped - closed issue"

        commenter = self.payload['comment', 'user', 'login']
        # Ignore our own comments.
        if commenter == self.integration_user:
            return "skipped - our own comment"

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
                return "skipped, comment not by author, collaborator, or assignee"

        # Check for r? and set the assignee.
        msg = self.payload['comment', 'body']
        reviewer = self.find_reviewer(msg, author)
        if reviewer:
            issue = str(self.payload['issue', 'number'])
            self.set_assignee(
                reviewer, owner, repo, issue, self.integration_user,
                author, None
            )
            return f"set assignee to {reviewer}"
        else:
            return "no reviewer found"
