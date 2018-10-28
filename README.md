Highfive [![Build Status](https://travis-ci.org/rust-lang-nursery/highfive.svg?branch=master)](https://travis-ci.org/rust-lang-nursery/highfive)
========

GitHub hooks to provide an encouraging atmosphere for new
contributors. Highfive assigns pull requests to users based on rules
in configuration files. You can see Highfive in action in several Rust
repositories. See the [rust-lang/rust pull
requests](https://github.com/rust-lang/rust/pulls), for example.

This project drives the [@rust-highfive][] bot and was originally a fork of
[servo/highfive][], used by Servo and Servo's [@highfive][] bot.  For more
history see the comments in [#35][].

[@rust-highfive]: https://github.com/rust-highfive
[servo/highfive]: https://github.com/servo/highfive
[@highfive]: https://github.com/highfive
[#35]: https://github.com/rust-lang-nursery/highfive/issues/35

### Table of Contents

1. [Installation](#installation)
2. [Testing](#testing)
3. [Adding a Project](#adding-a-project)
4. [Enabling a Repository](#enabling-a-repository)
5. [Local Development](#local-development)
6. [License](#license)

Installation
=======

To install `highfive`, you just need to execute the `setup.py` script or use
`pip` directly. Both commands have to be executed from the directory where
`setup.py` is located.

    $ python setup.py install

or

    $ pip install . # the dot is important ;)


Testing
=======

Before running tests, make sure the test-requirements are installed by running the following command:

    $ pip install -r test-requirements.txt


Once the dependencies are installed, you can run all tests by
executing:

    $ pytest

Tests are labeled as "unit", "integration", and "hermetic". All unit
tests are hermetic, but only some integration tests are hermetic. A
non-hermetic test makes network requests. To run only hermetic tests
do:

    $ pytest -m hermetic

Hermetic tests are run in PR builds. All tests are run in daily cron
builds.

Adding a Project
================

To make rust-highfive interact with a new repo, add a configuration file in
`highfive/configs`, with a filename of the form `reponame.json`. The file should look like:

```
{
    "groups":{
        "all": ["@username", "@otheruser"],
        "subteamname": ["@subteammember", "@username"]
    },
    "dirs":{
        "dirname":  ["subteamname", "@anotheruser"]
    },
    "contributing": "http://project.tld/contributing_guide.html",
    "expected_branch": "develop",
    "new_pr_labels": ["S-waiting-for-review"]
}
```

The `groups` section allows you to alias lists of usernames. You should
specify at least one user in the group "all". Others are optional.

In the `dirs` section, you map directories of the repository to users or
groups who're eligible to review PRs. This section can be left
blank.

`contributing` specifies the contribution guide link in the message which
welcomes new contributors to the repository. If `contributing` is not
present, the [Rust contributing.md][rustcontrib] will be linked instead. 

If PRs should be filed against a branch other than `master`, specify the
correct destination in the `expected_branch` field. If `expected_branch` is
left out, highfive will assume that PRs should be filed against `master`. 
The bot posts a warning on any PR that targets an unexpected branch.

`new_pr_labels` contains a list of labels to apply to each new PR. If it's left
out or empty, no new labels will be applied.

Enabling a Repository
---------------

Once the hooks for a repository are set up, visit the repository's webhook settings
page at `https://github.com/org/repo/settings/hooks`. 

Create a new webhook, pointing at your highfive instance's location:

- Enter payload URL: `http://99.88.777.666/highfive/newpr.py`
- Enter content type: `application/x-www-form-urlencoded`
- Leave the "secret" field blank
- Click on "Let me select individual events", and heck the boxes by "Issue comment" and "pull request"
- Check the box by "Active"
- Click on "Add webhook"

Local Development
-----------------

You can run Highfive on your machine and configure a repository to use
your local instance. Here is one approach for running a local server:

- Use [serve.py](/serve.py) to run the Highfive service. From the
  repository root, do:
  ```
  $ PYTHONPATH=$PYTHONPATH:$PWD python serve.py
  ```
  Now you have Highfive listening on port 8000 of your machine.
- Your Highfive instance will need to be reachable from outside of your machine. One way to do this is to use [ngrok](https://ngrok.com/) to get a temporary domain name that proxies to your Highfive instance. Additionally, you will be able to use ngrok's inspector to easily examine and replay the requests.
- Set up the webhook by following the instructions in [Enabling a
  Repo](#enabling-a-repo), substituting your local Highfive IP address
  or domain name and port number (if necessary).
- Obtain an OAuth token. In the account you are creating the token in,
  go to https://github.com/settings/tokens. Grant access to the repository scope.
- Put the authorization information obtained in the previous step into
  a file named config in the top of the repository (i.e., the
  directory containing this file). Here's a template of what it should
  look like:
  ```
  [github]
  user: OAUTH_TOKEN_USER
  token: OAUTH_TOKEN
  ```
  _Do not check in this file or commit your OAuth token to a
  repository in any other way. It is a secret._

Here are some details to be aware of:

- The beginning of `choose_reviewer` in
  [highfive/newpr.py](/highfive/newpr.py) contains logic that causes
  Highfive to ignore requests from unqualified repositories. You will
  likely need to modify this logic in order for your local Highfive to
  take action on new PRs.
- For Highfive to know how to select reviewers for your repository,
  you need a configuration file in
  [highfive/configs](/highfive/configs).
- Highfive ignores comments from the integration user near the top of
  `new_commment` in [highfive/newpr.py](/highfive/newpr.py).

[rustcontrib]: https://github.com/rust-lang/rust/blob/master/CONTRIBUTING.md 

License
=======

Highfive is licensed under the terms of both the MIT License and the
Apache License (Version 2.0).

See [LICENSE-APACHE](LICENSE-APACHE) and [LICENSE-MIT](LICENSE-MIT) for details.
