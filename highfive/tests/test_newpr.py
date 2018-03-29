from copy import deepcopy
from highfive import newpr
from highfive.tests import base
import json
import mock
from nose.plugins.attrib import attr
from urllib2 import HTTPError

@attr(type='unit')
class TestNewPR(base.BaseTest):
    def setUp(self):
        super(TestNewPR, self).setUp()

    def tearDown(self):
        super(TestNewPR, self).tearDown()

class TestNewPRGeneral(TestNewPR):
    def test_welcome_msg(self):
        base_msg = """Thanks for the pull request, and welcome! The Rust team is excited to review your changes, and you should hear from %s soon.

If any changes to this PR are deemed necessary, please add them as extra commits. This ensures that the reviewer can see what has changed since they last reviewed the code. Due to the way GitHub handles out-of-date commits, this should also make it reasonably obvious what issues have or haven't been addressed. Large or tricky changes may require several passes of review and changes.

Please see [the contribution instructions](%s) for more information.
"""

        # No reviewer, no config contributing link.
        self.assertEqual(
            newpr.welcome_msg(None, {}),
            base_msg % (
                '@nrc (NB. this repo may be misconfigured)',
                'https://github.com/rust-lang/rust/blob/master/CONTRIBUTING.md'
            )
        )

        # Has reviewer, no config contributing link.
        self.assertEqual(
            newpr.welcome_msg('userA', {}),
            base_msg % (
                '@userA (or someone else)',
                'https://github.com/rust-lang/rust/blob/master/CONTRIBUTING.md'
            )
        )

        # No reviewer, has config contributing link.
        self.assertEqual(
            newpr.welcome_msg(None, {'contributing': 'https://something'}),
            base_msg % (
                '@nrc (NB. this repo may be misconfigured)',
                'https://something'
            )
        )

        # Has reviewer, has config contributing link.
        self.assertEqual(
            newpr.welcome_msg('userA', {'contributing': 'https://something'}),
            base_msg % (
                '@userA (or someone else)',
                'https://something'
            )
        )

    def test_review_msg(self):
        # No reviewer.
        self.assertEqual(
            newpr.review_msg(None, 'userB'),
            '@userB: no appropriate reviewer found, use r? to override'
        )

        # Has reviewer.
        self.assertEqual(
            newpr.review_msg('userA', 'userB'),
            'r? @userA\n\n(rust_highfive has picked a reviewer for you, use r? to override)'
        )

    @mock.patch('os.path.dirname')
    def test_load_json_file(self, mock_dirname):
        mock_dirname.return_value = '/the/path'
        contents = ['some json']
        with mock.patch(
            '__builtin__.open', mock.mock_open(read_data=json.dumps(contents))
        ) as mock_file:
            self.assertEqual(newpr._load_json_file('a-config.json'), contents)
            mock_file.assert_called_with('/the/path/configs/a-config.json')

    @mock.patch('highfive.newpr.api_req')
    def test_post_comment_success(self, mock_api_req):
        mock_api_req.return_value = {'body': 'response body!'}
        self.assertIsNone(
            newpr.post_comment(
                'Request body!', 'repo-owner', 'repo-name', 7,
                'integrationUser', 'credential'
            )
        )
        mock_api_req.assert_called_with(
            'POST', 'https://api.github.com/repos/repo-owner/repo-name/issues/7/comments',
            {'body': 'Request body!'}, 'integrationUser', 'credential'
        )

    @mock.patch('highfive.newpr.api_req')
    def test_post_comment_error_201(self, mock_api_req):
        mock_api_req.return_value = {}
        mock_api_req.side_effect = HTTPError(None, 201, None, None, None)
        self.assertIsNone(
            newpr.post_comment(
                'Request body!', 'repo-owner', 'repo-name', 7,
                'integrationUser', 'credential'
            )
        )
        mock_api_req.assert_called_with(
            'POST', 'https://api.github.com/repos/repo-owner/repo-name/issues/7/comments',
            {'body': 'Request body!'}, 'integrationUser', 'credential'
        )

    @mock.patch('highfive.newpr.api_req')
    def test_post_comment_error(self, mock_api_req):
        mock_api_req.return_value = {}
        mock_api_req.side_effect = HTTPError(None, 422, None, None, None)
        self.assertRaises(
            HTTPError, newpr.post_comment, 'Request body!', 'repo-owner',
            'repo-name', 7, 'integrationUser', 'credential'
        )
        mock_api_req.assert_called_with(
            'POST', 'https://api.github.com/repos/repo-owner/repo-name/issues/7/comments',
            {'body': 'Request body!'}, 'integrationUser', 'credential'
        )

    @mock.patch('highfive.newpr.api_req')
    def test_is_collaborator_true(self, mock_api_req):
        self.assertTrue(
            newpr.is_collaborator(
                'commentUser', 'repo-owner', 'repo-name', 'integrationUser',
                'credential'
            )
        )
        mock_api_req.assert_called_with(
            'GET',
            'https://api.github.com/repos/repo-owner/repo-name/collaborators/commentUser',
            None, 'integrationUser', 'credential'
        )

    @mock.patch('highfive.newpr.api_req')
    def test_is_collaborator_false(self, mock_api_req):
        mock_api_req.side_effect = HTTPError(None, 404, None, None, None)
        self.assertFalse(
            newpr.is_collaborator(
                'commentUser', 'repo-owner', 'repo-name', 'integrationUser',
                'credential'
            )
        )
        mock_api_req.assert_called_with(
            'GET',
            'https://api.github.com/repos/repo-owner/repo-name/collaborators/commentUser',
            None, 'integrationUser', 'credential'
        )

    @mock.patch('highfive.newpr.api_req')
    def test_is_collaborator_error(self, mock_api_req):
        mock_api_req.side_effect = HTTPError(None, 500, None, None, None)
        self.assertRaises(
            HTTPError, newpr.is_collaborator, 'commentUser', 'repo-owner',
            'repo-name', 'integrationUser', 'credential'
        )
        mock_api_req.assert_called_with(
            'GET',
            'https://api.github.com/repos/repo-owner/repo-name/collaborators/commentUser',
            None, 'integrationUser', 'credential'
        )

    @mock.patch('highfive.newpr.api_req')
    def test_add_labels_success(self, mock_api_req):
        mock_api_req.return_value = {'body': 'response body!'}
        labels = ['label1', 'label2']
        self.assertIsNone(
            newpr.add_labels(
                labels, 'repo-owner', 'repo-name', 7, 'integrationUser',
                'credential'
            )
        )
        mock_api_req.assert_called_with(
            'POST', 'https://api.github.com/repos/repo-owner/repo-name/issues/7/labels',
            labels, 'integrationUser', 'credential'
        )

    @mock.patch('highfive.newpr.api_req')
    def test_add_labels_error(self, mock_api_req):
        mock_api_req.return_value = {}
        mock_api_req.side_effect = HTTPError(None, 422, None, None, None)
        labels = ['label1', 'label2']
        self.assertRaises(
            HTTPError, newpr.add_labels, labels, 'repo-owner', 'repo-name',
            7, 'integrationUser', 'credential'
        )
        mock_api_req.assert_called_with(
            'POST', 'https://api.github.com/repos/repo-owner/repo-name/issues/7/labels',
            labels, 'integrationUser', 'credential'
        )

    def test_submodule(self):
        submodule_diff = self._load_fake('submodule.diff')
        self.assertTrue(newpr.modifies_submodule(submodule_diff))

        normal_diff = self._load_fake('normal.diff')
        self.assertFalse(newpr.modifies_submodule(normal_diff))

    def test_expected_branch_default_expected_no_match(self):
        payload = {'pull_request': {'base': {'label': 'repo-owner:dev'}}}
        config = {}
        self.assertEqual(
            newpr.unexpected_branch(payload, config),
            ('master', 'dev')
        )

    def test_expected_branch_default_expected_match(self):
        payload = {'pull_request': {'base': {'label': 'repo-owner:master'}}}
        config = {}
        self.assertFalse(newpr.unexpected_branch(payload, config))

    def test_expected_branch_custom_expected_no_match(self):
        payload = {'pull_request': {'base': {'label': 'repo-owner:master'}}}
        config = {'expected_branch': 'dev' }
        self.assertEqual(
            newpr.unexpected_branch(payload, config),
            ('dev', 'master')
        )

    def test_expected_branch_custom_expected_match(self):
        payload = {'pull_request': {'base': {'label':'repo-owner:dev'}}}
        config = {'expected_branch': 'dev' }
        self.assertFalse(newpr.unexpected_branch(payload, config))

    def test_find_reviewer(self):
        found_cases = (
            ('r? @foo', 'foo'),
            ('R? @foo', 'foo'),
            ('....@!##$@#%r? @foo', 'foo'),
            ('r?:-:-:- @foo', 'foo'),
            ('Lorem ipsum dolor sit amet, r?@foo consectetur', 'foo'),
            ('r? @8iAke', '8iAke'),
            ('r? @D--a--s-h', 'D--a--s-h'),
            ('r? @foo$', 'foo'),
        )
        not_found_cases = (
            'rr? @foo',
            'r @foo',
            'r?! @foo',
            'r? foo',
            'r? @',
        )

        for (msg, reviewer) in found_cases:
            self.assertEqual(
                newpr.find_reviewer(msg), reviewer,
                "expected '%s' from '%s'" % (reviewer, msg)
            )

        for msg in not_found_cases:
            self.assertIsNone(
                newpr.find_reviewer(msg),
                "expected '%s' to have no reviewer extracted" % msg
            )

    def setup_get_irc_nick_mocks(self, mock_urllib2, status_code, data=None):
        mock_data = mock.Mock()
        mock_data.getcode.return_value = status_code
        mock_data.read.return_value = data
        mock_urllib2.urlopen.return_value = mock_data
        return mock_data

    @mock.patch('highfive.newpr.urllib2')
    def test_get_irc_nick_non_200(self, mock_urllib2):
        mock_data = self.setup_get_irc_nick_mocks(mock_urllib2, 300)
        self.assertIsNone(newpr.get_irc_nick('foo'))

        mock_urllib2.urlopen.assert_called_with(
            'http://www.ncameron.org/rustaceans/user?username=foo'
        )
        mock_data.getcode.assert_called()
        mock_data.read.assert_not_called()

    @mock.patch('highfive.newpr.urllib2')
    def test_get_irc_nick_no_data(self, mock_urllib2):
        mock_data = self.setup_get_irc_nick_mocks(mock_urllib2, 200, '[]')
        self.assertIsNone(newpr.get_irc_nick('foo'))

        mock_urllib2.urlopen.assert_called_with(
            'http://www.ncameron.org/rustaceans/user?username=foo'
        )
        mock_data.getcode.assert_called()
        mock_data.read.assert_called()

    @mock.patch('highfive.newpr.urllib2')
    def test_get_irc_nick_has_data(self, mock_urllib2):
        mock_data = self.setup_get_irc_nick_mocks(
            mock_urllib2, 200,
            '[{"username":"nrc","name":"Nick Cameron","irc":"nrc","email":"nrc@ncameron.org","discourse":"nrc","reddit":"nick29581","twitter":"@nick_r_cameron","blog":"https://www.ncameron.org/blog","website":"https://www.ncameron.org","notes":"<p>I work on the Rust compiler, language design, and tooling. I lead the dev tools team and am part of the core team. I&#39;m part of the research team at Mozilla.</p>\\n","avatar":"https://avatars.githubusercontent.com/nrc","irc_channels":["rust-dev-tools","rust","rust-internals","rust-lang","rustc","servo"]}]'
        )
        self.assertEqual(newpr.get_irc_nick('nrc'), 'nrc')

        mock_urllib2.urlopen.assert_called_with(
            'http://www.ncameron.org/rustaceans/user?username=nrc'
        )
        mock_data.getcode.assert_called()
        mock_data.read.assert_called()

class TestApiReq(TestNewPR):
    @classmethod
    def setUpClass(cls):
        cls.method = 'METHOD'
        cls.url = 'https://foo.bar'

    def setUp(self):
        super(TestApiReq, self).setUp()

        self.patchers = {
            'urlopen': mock.patch('urllib2.urlopen'),
            'Request': mock.patch('urllib2.Request'),
            'StringIO': mock.patch('highfive.newpr.StringIO'),
            'GzipFile': mock.patch('gzip.GzipFile'),
        }
        self.mocks = {k: v.start() for k,v in self.patchers.iteritems()}

        self.req = self.mocks['Request'].return_value

        self.res = self.mocks['urlopen'].return_value
        self.res.info.return_value = {'Content-Encoding': 'gzip'}

        self.body = self.res.read.return_value = 'body1'

        self.gzipped_body = self.mocks['GzipFile'].return_value.read
        self.gzipped_body.return_value = 'body2'

    def tearDown(self):
        super(TestApiReq, self).tearDown()

        for patcher in self.patchers.itervalues():
            patcher.stop()

    def verify_mock_calls(self, header_calls, gzipped):
        self.mocks['Request'].assert_called_with(
            self.url, json.dumps(self.data) if self.data else self.data,
            {'Content-Type': 'application/json'} if self.data else {}
        )
        self.assertEqual(self.req.get_method(), 'METHOD')

        self.assertEqual(len(self.req.add_header.mock_calls), len(header_calls))
        self.req.add_header.assert_has_calls(header_calls)

        self.mocks['urlopen'].assert_called_with(self.req)
        self.res.info.assert_called_once()
        self.res.read.assert_called_once()

        if gzipped:
            self.mocks['StringIO'].assert_called_with(self.body)
            self.mocks['GzipFile'].assert_called_with(
                fileobj=self.mocks['StringIO'].return_value
            )
            self.gzipped_body.assert_called_once()
        else:
            self.mocks['StringIO'].assert_not_called()
            self.mocks['GzipFile'].assert_not_called()
            self.gzipped_body.assert_not_called()

    def call_api_req(self):
        return newpr.api_req(
            self.method, self.url, self.data, token=self.token,
            media_type=self.media_type
        )

    def test1(self):
        """No data, no token, no media_type, header (gzip/no gzip)"""
        (self.data, self.token, self.media_type) = (None, None, None)

        self.assertEqual(
            self.call_api_req(),
            {'header': {'Content-Encoding': 'gzip'}, 'body': 'body2'}
        )
        self.verify_mock_calls([], True)

    def test2(self):
        """Has data, no token, no media_type, response gzipped"""
        (self.data, self.token, self.media_type) = (
            {'some': 'data'}, None, None
        )

        self.assertEqual(
            self.call_api_req(),
            {'header': {'Content-Encoding': 'gzip'}, 'body': 'body2'}
        )
        self.verify_mock_calls([], True)

    def test3(self):
        """Has data, has token, no media_type, response gzipped"""
        (self.data, self.token, self.media_type) = (
            {'some': 'data'}, 'credential', None
        )

        self.assertEqual(
            self.call_api_req(),
            {'header': {'Content-Encoding': 'gzip'}, 'body': 'body2'}
        )
        calls = [
            mock.call('Authorization', 'token %s' % self.token),
        ]
        self.verify_mock_calls(calls, True)

    def test4(self):
        """Has data, no token, has media_type, response gzipped"""
        (self.data, self.token, self.media_type) = (
            {'some': 'data'}, None, 'this.media.type'
        )

        self.assertEqual(
            self.call_api_req(),
            {'header': {'Content-Encoding': 'gzip'}, 'body': 'body2'}
        )
        calls = [
            mock.call('Accept', self.media_type),
        ]
        self.verify_mock_calls(calls, True)

    def test5(self):
        """Has data, has token, has media_type, response gzipped"""
        (self.data, self.token, self.media_type) = (
            {'some': 'data'}, 'credential', 'the.media.type'
        )

        self.assertEqual(
            self.call_api_req(),
            {'header': {'Content-Encoding': 'gzip'}, 'body': 'body2'}
        )
        calls = [
            mock.call('Authorization', 'token %s' % self.token),
            mock.call('Accept', self.media_type),
        ]
        self.verify_mock_calls(calls, True)

    def test6(self):
        """Has data, has token, has media_type, response not gzipped"""
        (self.data, self.token, self.media_type) = (
            {'some': 'data'}, 'credential', 'the.media.type'
        )

        self.res.info.return_value = {}

        self.assertEqual(
            self.call_api_req(),
            {'header': {}, 'body': 'body1'}
        )
        calls = [
            mock.call('Authorization', 'token %s' % self.token),
            mock.call('Accept', self.media_type),
        ]
        self.verify_mock_calls(calls, False)

class TestSetAssignee(TestNewPR):
    @classmethod
    def setUpClass(cls):
        cls.assignee = 'assigneeUser'
        cls.author = 'authorUser'
        cls.owner = 'repo-owner'
        cls.repo = 'repo-name'
        cls.issue = 7
        cls.user = 'integrationUser'
        cls.token = 'credential'

    def setUp(self):
        super(TestSetAssignee, self).setUp()

        self.patchers = {
            'api_req': mock.patch('highfive.newpr.api_req'),
            'get_irc_nick': mock.patch('highfive.newpr.get_irc_nick'),
            'post_comment': mock.patch('highfive.newpr.post_comment'),
            'IrcClient': mock.patch('highfive.irc.IrcClient'),
        }
        self.mocks = {k: v.start() for k,v in self.patchers.iteritems()}
        self.mocks['client'] = self.mocks['IrcClient'].return_value

    def tearDown(self):
        super(TestSetAssignee, self).tearDown()

        for patcher in self.patchers.itervalues():
            patcher.stop()

    def set_assignee(self, assignee='', to_mention=None):
        assignee = self.assignee if assignee == '' else assignee
        return newpr.set_assignee(
            assignee, self.owner, self.repo, self.issue, self.user, self.token,
            self.author, to_mention or []
        )

    def assert_api_req_call(self, assignee=''):
        assignee = self.assignee if assignee == '' else assignee
        self.mocks['api_req'].assert_called_once_with(
            'PATCH',
            'https://api.github.com/repos/%s/%s/issues/%s' % (
                self.owner, self.repo, self.issue
            ),
            {"assignee": assignee}, self.user, self.token
        )

    def test_api_req_good(self):
        self.mocks['get_irc_nick'].return_value = None
        self.set_assignee()

        self.assert_api_req_call()
        self.mocks['get_irc_nick'].assert_called_once_with(self.assignee)
        self.mocks['IrcClient'].assert_not_called()
        self.mocks['client'].send_then_quit.assert_not_called()
        self.mocks['post_comment'].assert_not_called()

    def test_api_req_201(self):
        self.mocks['api_req'].side_effect = HTTPError(None, 201, None, None, None)
        self.mocks['get_irc_nick'].return_value = None
        self.set_assignee()

        self.assert_api_req_call()
        self.mocks['get_irc_nick'].assert_called_once_with(self.assignee)
        self.mocks['IrcClient'].assert_not_called()
        self.mocks['client'].send_then_quit.assert_not_called()
        self.mocks['post_comment'].assert_not_called()

    def test_api_req_error(self):
        self.mocks['api_req'].side_effect = HTTPError(None, 403, None, None, None)
        self.assertRaises(HTTPError, self.set_assignee)

        self.assert_api_req_call()
        self.mocks['get_irc_nick'].assert_not_called()
        self.mocks['IrcClient'].assert_not_called()
        self.mocks['client'].send_then_quit.assert_not_called()
        self.mocks['post_comment'].assert_not_called()

    def test_has_nick(self):
        irc_nick = 'nick'
        self.mocks['get_irc_nick'].return_value = irc_nick

        self.set_assignee()

        self.assert_api_req_call()
        self.mocks['get_irc_nick'].assert_called_once_with(self.assignee)
        self.mocks['IrcClient'].assert_called_once_with(target='#rust-bots')
        self.mocks['client'].send_then_quit.assert_called_once_with(
            "{}: ping to review issue https://www.github.com/{}/{}/pull/{} by {}.".format(
                irc_nick, self.owner, self.repo, self.issue, self.author
            )
        )
        self.mocks['post_comment'].assert_not_called()

    def test_has_to_mention(self):
        self.mocks['get_irc_nick'].return_value = None

        to_mention = [
            {
                'message': 'This is important',
                'reviewers': ['@userA', '@userB', 'integrationUser', '@userC'],
            },
            {
                'message': 'Also important',
                'reviewers': ['@userD'],
            },
        ]
        self.set_assignee(to_mention=to_mention)

        self.assert_api_req_call()
        self.mocks['get_irc_nick'].assert_called_once_with(self.assignee)
        self.mocks['IrcClient'].assert_not_called()
        self.mocks['client'].send_then_quit.assert_not_called()
        self.mocks['post_comment'].assert_called_once_with(
            'This is important\n\ncc @userA,@userB,@userC\n\nAlso important\n\ncc @userD',
            self.owner, self.repo, self.issue, self.user, self.token
        )

    def test_no_assignee(self):
        self.set_assignee(None)

        self.assert_api_req_call(None)
        self.mocks['get_irc_nick'].assert_not_called()
        self.mocks['IrcClient'].assert_not_called()
        self.mocks['client'].send_then_quit.assert_not_called()
        self.mocks['post_comment'].assert_not_called()

class TestIsNewContributor(TestNewPR):
    @classmethod
    def setUpClass(cls):
        cls.username = 'commitUser'
        cls.owner = 'repo-owner'
        cls.repo = 'repo-name'
        cls.user = 'integrationUser'
        cls.token = 'credential'

    def setUp(self):
        super(TestIsNewContributor, self).setUp()
        self.payload = {'repository': {'fork': False}}
        self.patchers = {
            'api_req': mock.patch('highfive.newpr.api_req'),
        }
        self.mocks = {k: v.start() for k,v in self.patchers.iteritems()}

    def tearDown(self):
        super(TestIsNewContributor, self).tearDown()

        for patcher in self.patchers.itervalues():
            patcher.stop()

    def is_new_contributor(self):
        return newpr.is_new_contributor(
            self.username, self.owner, self.repo, self.user, self.token,
            self.payload
        )

    def api_return(self, total_count):
        return {
            'body': json.dumps({'total_count': total_count}),
            'header': {},
        }

    def assert_api_req_call(self):
        self.mocks['api_req'].assert_called_once_with(
            'GET',
            'https://api.github.com/search/commits?q=repo:%s/%s+author:%s' % (
                self.owner, self.repo, self.username
            ), None, self.user, self.token,
            'application/vnd.github.cloak-preview'
        )

    def test_is_new_contributor_fork(self):
        self.payload['repository']['fork'] = True
        self.assertFalse(self.is_new_contributor())
        self.mocks['api_req'].assert_not_called()

    def test_is_new_contributor_has_commits(self):
        self.mocks['api_req'].return_value = self.api_return(5)
        self.assertTrue(self.is_new_contributor())
        self.assert_api_req_call()

    def test_is_new_contributor_no_commits(self):
        self.mocks['api_req'].return_value = self.api_return(0)
        self.assertFalse(self.is_new_contributor())
        self.assert_api_req_call()

    def test_is_new_contributor_nonexistent_user(self):
        self.mocks['api_req'].side_effect = HTTPError(None, 422, None, None, None)
        self.assertFalse(self.is_new_contributor())
        self.assert_api_req_call()

    def test_is_new_contributor_error(self):
        self.mocks['api_req'].side_effect = HTTPError(None, 403, None, None, None)
        self.assertRaises(HTTPError, self.is_new_contributor)
        self.assert_api_req_call()

class TestPostWarnings(TestNewPR):
    @classmethod
    def setUpClass(cls):
        cls.payload = {'the': 'payload'}
        cls.config = {'the': 'config'}
        cls.diff = 'the diff'
        cls.owner = 'repo-owner'
        cls.repo = 'repo-name'
        cls.issue = 7
        cls.user = 'integrationUser'
        cls.token = 'credential'

    def setUp(self):
        super(TestPostWarnings, self).setUp()

        self.patchers = {
            'unexpected_branch': mock.patch('highfive.newpr.unexpected_branch'),
            'modifies_submodule': mock.patch('highfive.newpr.modifies_submodule'),
            'post_comment': mock.patch('highfive.newpr.post_comment'),
        }
        self.mocks = {k: v.start() for k,v in self.patchers.iteritems()}

    def tearDown(self):
        super(TestPostWarnings, self).tearDown()

        for patcher in self.patchers.itervalues():
            patcher.stop()

    def post_warnings(self):
        newpr.post_warnings(
            self.payload, self.config, self.diff, self.owner, self.repo,
            self.issue, self.user, self.token
        )

    def test_no_warnings(self):
        self.mocks['unexpected_branch'].return_value = False
        self.mocks['modifies_submodule'].return_value = False

        self.post_warnings()

        self.mocks['unexpected_branch'].assert_called_with(
            self.payload, self.config
        )
        self.mocks['modifies_submodule'].assert_called_with(self.diff)
        self.mocks['post_comment'].assert_not_called()

    def test_unexpected_branch(self):
        self.mocks['unexpected_branch'].return_value = (
            'master', 'something-else'
        )
        self.mocks['modifies_submodule'].return_value = False

        self.post_warnings()

        self.mocks['unexpected_branch'].assert_called_with(
            self.payload, self.config
        )
        self.mocks['modifies_submodule'].assert_called_with(self.diff)

        expected_warning = """<img src="http://www.joshmatthews.net/warning.svg" alt="warning" height=20> **Warning** <img src="http://www.joshmatthews.net/warning.svg" alt="warning" height=20>

* Pull requests are usually filed against the master branch for this repo, but this one is against something-else. Please double check that you specified the right target!"""
        self.mocks['post_comment'].assert_called_with(
            expected_warning, self.owner, self.repo, self.issue, self.user,
            self.token
        )

    def test_modifies_submodule(self):
        self.mocks['unexpected_branch'].return_value = False
        self.mocks['modifies_submodule'].return_value = True

        self.post_warnings()

        self.mocks['unexpected_branch'].assert_called_with(
            self.payload, self.config
        )
        self.mocks['modifies_submodule'].assert_called_with(self.diff)

        expected_warning = """<img src="http://www.joshmatthews.net/warning.svg" alt="warning" height=20> **Warning** <img src="http://www.joshmatthews.net/warning.svg" alt="warning" height=20>

* These commits modify **submodules**."""
        self.mocks['post_comment'].assert_called_with(
            expected_warning, self.owner, self.repo, self.issue, self.user,
            self.token
        )

    def test_unexpected_branch_modifies_submodule(self):
        self.mocks['unexpected_branch'].return_value = (
            'master', 'something-else'
        )
        self.mocks['modifies_submodule'].return_value = True

        self.post_warnings()

        self.mocks['unexpected_branch'].assert_called_with(
            self.payload, self.config
        )
        self.mocks['modifies_submodule'].assert_called_with(self.diff)

        expected_warning = """<img src="http://www.joshmatthews.net/warning.svg" alt="warning" height=20> **Warning** <img src="http://www.joshmatthews.net/warning.svg" alt="warning" height=20>

* Pull requests are usually filed against the master branch for this repo, but this one is against something-else. Please double check that you specified the right target!
* These commits modify **submodules**."""
        self.mocks['post_comment'].assert_called_with(
            expected_warning, self.owner, self.repo, self.issue, self.user,
            self.token
        )

class TestNewComment(TestNewPR):
    def setUp(self):
        super(TestNewComment, self).setUp()

        self.patchers = {
            'is_collaborator': mock.patch('highfive.newpr.is_collaborator'),
            'find_reviewer': mock.patch('highfive.newpr.find_reviewer'),
            'set_assignee': mock.patch('highfive.newpr.set_assignee'),
        }
        self.mocks = {k: v.start() for k,v in self.patchers.iteritems()}

    def tearDown(self):
        super(TestNewComment, self).tearDown()

        for patcher in self.patchers.itervalues():
            patcher.stop()

    @staticmethod
    def make_payload(
        state='open', is_pull_request=True, commenter='userA',
        repo='repo-name', owner='repo-owner', author='userB',
        comment='comment!', issue_number=7, assignee=None
    ):
        payload = {
            'issue': {
                'state': state,
                'number': issue_number,
                'assignee': None,
                'user': {
                    'login': author,
                },
            },
            'comment': {
                'user': {
                    'login': commenter,
                },
                'body': comment,
            },
            'repository': {
                'name': repo,
                'owner': {
                    'login': owner,
                },
            },
        }

        if is_pull_request:
            payload['issue']['pull_request'] = {}
        if assignee is not None:
            payload['issue']['assignee'] = {'login': assignee}

        return payload

    def test_not_open(self):
        payload = self.make_payload(state='closed')

        self.assertIsNone(newpr.new_comment(payload, 'user', 'credential'))
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_not_called()
        self.mocks['set_assignee'].assert_not_called()

    def test_not_pr(self):
        payload = self.make_payload(is_pull_request=False)

        self.assertIsNone(newpr.new_comment(payload, 'user', 'credential'))
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_not_called()
        self.mocks['set_assignee'].assert_not_called()

    def test_commenter_is_integration_user(self):
        payload = self.make_payload(commenter='integrationUser')

        self.assertIsNone(
            newpr.new_comment(payload, 'integrationUser', 'credential')
        )
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_not_called()
        self.mocks['set_assignee'].assert_not_called()

    def test_unauthorized_assigner(self):
        payload = self.make_payload(
            author='userA', commenter='userB', assignee='userC'
        )

        self.mocks['is_collaborator'].return_value = False
        self.assertIsNone(
            newpr.new_comment(payload, 'integrationUser', 'credential')
        )
        self.mocks['is_collaborator'].assert_called_with(
            'userB', 'repo-owner', 'repo-name', 'integrationUser', 'credential'
        )
        self.mocks['find_reviewer'].assert_not_called()
        self.mocks['set_assignee'].assert_not_called()

    # There are three ways to make it past the authorized assigner
    # check. The next three methods excercise those paths.
    def test_authorized_assigner_author_is_commenter(self):
        payload = self.make_payload(
            author='userA', commenter='userA', assignee='userC'
        )

        newpr.new_comment(payload, 'integrationUser', 'credential')
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_called()

    def test_authorized_assigner_commenter_is_assignee(self):
        payload = self.make_payload(
            author='userA', commenter='userB', assignee='userB'
        )

        newpr.new_comment(payload, 'integrationUser', 'credential')
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_called()

    def test_authorized_assigner_commenter_is_collaborator(self):
        payload = self.make_payload(
            author='userA', commenter='userB', assignee='userC'
        )

        self.mocks['is_collaborator'].return_value = True
        newpr.new_comment(payload, 'integrationUser', 'credential')
        self.mocks['is_collaborator'].assert_called_with(
            'userB', 'repo-owner', 'repo-name', 'integrationUser', 'credential'
        )
        self.mocks['find_reviewer'].assert_called()

    def test_no_reviewer(self):
        payload = self.make_payload(author='userA', commenter='userA')

        self.mocks['find_reviewer'].return_value = None
        newpr.new_comment(payload, 'integrationUser', 'credential')
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_called_with('comment!')
        self.mocks['set_assignee'].assert_not_called()

    def test_has_reviewer(self):
        payload = self.make_payload(author='userA', commenter='userA')

        self.mocks['find_reviewer'].return_value = 'userD'
        newpr.new_comment(payload, 'integrationUser', 'credential')
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_called_with('comment!')
        self.mocks['set_assignee'].assert_called_with(
            'userD', 'repo-owner', 'repo-name', '7', 'integrationUser',
            'credential', 'userA', None
        )

class TestChooseReviewer(TestNewPR):
    @classmethod
    def setUpClass(cls):
        cls.diff = {
            'normal': cls._load_fake('normal.diff'),
        }
        cls.config = {
            'individuals_no_dirs' :{
                "groups": { "all": ["@pnkfelix", "@nrc"] },
                "dirs": {},
            },
            'individuals_dirs' :{
                "groups": { "all": ["@pnkfelix", "@nrc"] },
                "dirs": { "librustc": ["@aturon"] },
            },
            'individuals_dirs_2' :{
                "groups": { "all": ["@pnkfelix", "@nrc"] },
                "dirs": { "foobazdir": ["@aturon"] },
            },
            'circular_groups': {
                "groups": {
                    "all": ["some"],
                    "some": ["all"],
                },
            },
            'empty' :{
                "groups": { "all": [] },
                "dirs": {},
            },
        }
        cls.global_ = {
            'base': {
                "groups": {
                    "core": ["@alexcrichton"],
                }
            },
            'has_all': {
                "groups": { "all": ["@alexcrichton"] }
            },
        }

    def choose_reviewer(
        self, repo, owner, diff, exclude, config, global_ = None
    ):
        return self.choose_reviewer_inner(
            repo, owner, diff, exclude, config, global_
        )

    @mock.patch('highfive.newpr._load_json_file')
    def choose_reviewer_inner(
        self, repo, owner, diff, exclude, config, global_, mock_load_json
    ):
        mock_load_json.return_value = deepcopy(global_ or { "groups": {} })
        return newpr.choose_reviewer(
            repo, owner, diff, exclude, deepcopy(config)
        )

    def test_unsupported_repo(self):
        """The choose_reviewer function has an escape hatch for calls that
        are not in specific GitHub organizations or owners. This tests
        that logic.
        """
        diff = self.diff['normal']
        config = self.config['individuals_no_dirs']
        test_return = ('test_user_selection_ignore_this', None)

        self.assertNotEqual(
            test_return,
            self.choose_reviewer(
                'whatever', 'rust-lang', diff, 'foo', deepcopy(config)
            )
        )
        self.assertNotEqual(
            test_return,
            self.choose_reviewer(
                'whatever', 'rust-lang-nursery', diff, 'foo', deepcopy(config)
            )
        )
        self.assertNotEqual(
            test_return,
            self.choose_reviewer(
                'whatever', 'rust-lang-deprecated', diff, 'foo',
                deepcopy(config)
            )
        )
        self.assertNotEqual(
            test_return,
            self.choose_reviewer(
                'highfive', 'nrc', diff, 'foo', deepcopy(config)
            )
        )
        self.assertEqual(
            test_return,
            self.choose_reviewer(
                'anything', 'else', diff, 'foo', deepcopy(config)
            )
        )

    def choose_reviewers(self, diff, config, author, global_ = None):
        """Helper function that repeatedly calls choose_reviewer to build sets
        of reviewers and mentions for a given diff, configuration, and
        author.
        """
        chosen_reviewers = set()
        mention_list = set()
        for _ in xrange(40):
            (reviewer, mentions) = self.choose_reviewer(
                'rust', 'rust-lang', diff, author, deepcopy(config), global_
            )
            chosen_reviewers.add(reviewer)
            mention_list.add(None if mentions is None else tuple(mentions))
        return chosen_reviewers, mention_list

    def test_individuals_no_dirs_1(self):
        """Test choosing a reviewer from a list of individual reviewers, no
        directories, and an author who is not a potential reviewer.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['individuals_no_dirs'],
            "nikomatsakis"
        )
        self.assertEqual(set(["pnkfelix", "nrc"]), chosen_reviewers)
        self.assertEqual(set([()]), mentions)

    def test_individuals_no_dirs_2(self):
        """Test choosing a reviewer from a list of individual reviewers, no
        directories, and an author who is a potential reviewer.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['individuals_no_dirs'], "nrc"
        )
        self.assertEqual(set(["pnkfelix"]), chosen_reviewers)
        self.assertEqual(set([()]), mentions)

    def test_circular_groups(self):
        """Test choosing a reviewer from groups that have circular references.
        """
        self.assertRaises(
            AssertionError, newpr.choose_reviewer, 'rust', 'rust-lang',
            self.diff['normal'], 'fooauthor',
            self.config['circular_groups']
        )

    def test_global_core(self):
        """Test choosing a reviewer from the core group in the global
        configuration.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['empty'], 'fooauthor',
            self.global_['base']
        )
        self.assertEqual(set(['alexcrichton']), chosen_reviewers)
        self.assertEqual(set([()]), mentions)

    @mock.patch('highfive.newpr._load_json_file')
    def test_global_group_overlap(self, mock_load_json):
        """Test for an AssertionError when the global config contains a group
        already defined in the config.
        """
        mock_load_json.return_value = self.global_['has_all']
        self.assertRaises(
            AssertionError, newpr.choose_reviewer, 'rust', 'rust-lang',
            self.diff['normal'], 'fooauthor',
            self.config['individuals_no_dirs']
        )

    def test_no_potential_reviewers(self):
        """Test choosing a reviewer when nobody qualifies.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['empty'], 'alexcrichton',
            self.global_['base']
        )
        self.assertEqual(set([None]), chosen_reviewers)
        self.assertEqual(set([None]), mentions)

    def test_with_dirs(self):
        """Test choosing a reviewer when directory reviewers are defined that
        intersect with the diff.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['individuals_dirs'],
            "nikomatsakis"
        )
        self.assertEqual(set(["pnkfelix", "nrc", "aturon"]), chosen_reviewers)
        self.assertEqual(set([()]), mentions)

    def test_with_dirs_no_intersection(self):
        """Test choosing a reviewer when directory reviewers are defined that
        do not intersect with the diff.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['individuals_dirs_2'],
            "nikomatsakis"
        )
        self.assertEqual(set(["pnkfelix", "nrc"]), chosen_reviewers)
        self.assertEqual(set([()]), mentions)
