from copy import deepcopy
from highfive import newpr
from highfive.payload import Payload
from highfive.tests import fakes
from highfive.tests.patcherize import patcherize
from highfive.tests.fakes import load_fake
import json
import mock
import os
import pytest
from urllib2 import HTTPError

@pytest.mark.unit
@pytest.mark.hermetic
class TestNewPR(object):
    pass

class HighfiveHandlerMock(object):
    def __init__(
        self, payload, integration_user='integrationUser',
        integration_token='integrationToken', repo_config={}
    ):
        assert(type(payload) == Payload)
        self.integration_user = integration_user
        self.integration_token = integration_token

        def config_handler(section, key):
            if section == 'github':
                if key == 'user':
                    return integration_user
                if key == 'token':
                    return integration_token

        self.patchers_stopped = False
        self.config_patcher = mock.patch('highfive.newpr.ConfigParser')
        self.mock_config_parser = self.config_patcher.start()
        self.mock_config = mock.Mock()
        self.mock_config.get.side_effect = config_handler
        self.mock_config_parser.RawConfigParser.return_value = self.mock_config

        self.load_repo_config_patcher = mock.patch(
            'highfive.newpr.HighfiveHandler.load_repo_config'
        )
        self.mock_load_repo_config = self.load_repo_config_patcher.start()
        self.mock_load_repo_config.return_value = repo_config

        self.handler = newpr.HighfiveHandler(payload)

    def __enter__(self):
        return self

    def __exit__(self, _, __, ___):
        self.stop_patchers()

    def __del__(self):
        self.stop_patchers()

    def stop_patchers(self):
        if not self.patchers_stopped:
            self.patchers_stopped = True
            self.config_patcher.stop()
            self.load_repo_config_patcher.stop()

class TestHighfiveHandler(TestNewPR):
    @mock.patch('highfive.newpr.HighfiveHandler.load_repo_config')
    def test_init(self, mock_load_repo_config):
        payload = Payload({'the': 'payload'})
        with HighfiveHandlerMock(payload, repo_config={'a': 'config!'}) as m:
            assert m.handler.payload == payload
            assert m.handler.config == m.mock_config
            assert m.handler.integration_user == 'integrationUser'
            assert m.handler.integration_token == 'integrationToken'
            assert m.handler.repo_config == {'a': 'config!'}
            m.mock_config.read.assert_called_once_with('./config')

    @mock.patch('highfive.newpr.HighfiveHandler._load_json_file')
    def test_load_repo_config_supported(self, mock_load_json_file):
        mock_load_json_file.return_value = {'a': 'config!'}
        payload = Payload({
            'action': 'opened',
            'repository': {'full_name': 'foo/blah'}
        })
        m = HighfiveHandlerMock(payload)
        m.stop_patchers()
        assert m.handler.load_repo_config() == {'a': 'config!'}
        mock_load_json_file.assert_called_once_with(
            os.path.join('foo', 'blah.json')
        )

    @mock.patch('highfive.newpr.HighfiveHandler._load_json_file')
    def test_load_repo_config_unsupported(self, mock_load_json_file):
        mock_load_json_file.side_effect = IOError
        payload = Payload({
            'action': 'created',
            'repository': {'full_name': 'foo/blah'}
        })
        m = HighfiveHandlerMock(payload)
        m.stop_patchers()
        with pytest.raises(newpr.UnsupportedRepoError):
            m.handler.load_repo_config()
        mock_load_json_file.assert_called_once_with(
            os.path.join('foo', 'blah.json')
        )

class TestNewPRGeneral(TestNewPR):
    def test_welcome_msg(self):
        base_msg = """Thanks for the pull request, and welcome! The Rust team is excited to review your changes, and you should hear from %s soon.

If any changes to this PR are deemed necessary, please add them as extra commits. This ensures that the reviewer can see what has changed since they last reviewed the code. Due to the way GitHub handles out-of-date commits, this should also make it reasonably obvious what issues have or haven't been addressed. Large or tricky changes may require several passes of review and changes.

Please see [the contribution instructions](%s) for more information.
"""

        # No reviewer, no config contributing link.
        handler = HighfiveHandlerMock(Payload({})).handler
        assert handler.welcome_msg(None) == base_msg % (
            '@nrc (NB. this repo may be misconfigured)',
            'https://github.com/rust-lang/rust/blob/master/CONTRIBUTING.md'
        )

        # Has reviewer, no config contributing link.
        handler = HighfiveHandlerMock(Payload({})).handler
        assert handler.welcome_msg('userA') == base_msg % (
            '@userA (or someone else)',
            'https://github.com/rust-lang/rust/blob/master/CONTRIBUTING.md'
        )

        # No reviewer, has config contributing link.
        handler = HighfiveHandlerMock(
            Payload({}), repo_config={'contributing': 'https://something'}
        ).handler
        assert handler.welcome_msg(None) == base_msg % (
            '@nrc (NB. this repo may be misconfigured)',
            'https://something'
        )

        # Has reviewer, has config contributing link.
        handler = HighfiveHandlerMock(
            Payload({}), repo_config={'contributing': 'https://something'}
        ).handler
        assert handler.welcome_msg('userA') == base_msg % (
            '@userA (or someone else)',
            'https://something'
        )

    def test_review_msg(self):
        # No reviewer.
        handler = HighfiveHandlerMock(Payload({})).handler
        assert handler.review_msg(None, 'userB') == \
            '@userB: no appropriate reviewer found, use r? to override'

        # Has reviewer.
        assert handler.review_msg('userA', 'userB') == \
            'r? @userA\n\n(rust_highfive has picked a reviewer for you, use r? to override)'

    @mock.patch('os.path.dirname')
    def test_load_json_file(self, mock_dirname):
        handler = HighfiveHandlerMock(Payload({})).handler
        mock_dirname.return_value = '/the/path'
        contents = ['some json']
        with mock.patch(
            '__builtin__.open', mock.mock_open(read_data=json.dumps(contents))
        ) as mock_file:
            assert handler._load_json_file('a-config.json') == contents
            mock_file.assert_called_with('/the/path/configs/a-config.json')

    @mock.patch('highfive.newpr.HighfiveHandler.api_req')
    def test_post_comment_success(self, mock_api_req):
        handler = HighfiveHandlerMock(Payload({})).handler
        mock_api_req.return_value = {'body': 'response body!'}
        assert handler.post_comment(
            'Request body!', 'repo-owner', 'repo-name', 7
        ) is None
        mock_api_req.assert_called_with(
            'POST', 'https://api.github.com/repos/repo-owner/repo-name/issues/7/comments',
            {'body': 'Request body!'}
        )

    @mock.patch('highfive.newpr.HighfiveHandler.api_req')
    def test_post_comment_error_201(self, mock_api_req):
        handler = HighfiveHandlerMock(Payload({})).handler
        mock_api_req.return_value = {}
        mock_api_req.side_effect = HTTPError(None, 201, None, None, None)
        assert handler.post_comment(
            'Request body!', 'repo-owner', 'repo-name', 7
        ) is None
        mock_api_req.assert_called_with(
            'POST', 'https://api.github.com/repos/repo-owner/repo-name/issues/7/comments',
            {'body': 'Request body!'}
        )

    @mock.patch('highfive.newpr.HighfiveHandler.api_req')
    def test_post_comment_error(self, mock_api_req):
        handler = HighfiveHandlerMock(Payload({})).handler
        mock_api_req.return_value = {}
        mock_api_req.side_effect = HTTPError(None, 422, None, None, None)
        with pytest.raises(HTTPError):
            handler.post_comment(
                'Request body!', 'repo-owner', 'repo-name', 7
            )
        mock_api_req.assert_called_with(
            'POST', 'https://api.github.com/repos/repo-owner/repo-name/issues/7/comments',
            {'body': 'Request body!'}
        )

    @mock.patch('highfive.newpr.HighfiveHandler.api_req')
    def test_is_collaborator_true(self, mock_api_req):
        handler = HighfiveHandlerMock(Payload({})).handler
        assert handler.is_collaborator(
            'commentUser', 'repo-owner', 'repo-name'
        )
        mock_api_req.assert_called_with(
            'GET',
            'https://api.github.com/repos/repo-owner/repo-name/collaborators/commentUser',
            None
        )

    @mock.patch('highfive.newpr.HighfiveHandler.api_req')
    def test_is_collaborator_false(self, mock_api_req):
        handler = HighfiveHandlerMock(Payload({})).handler
        mock_api_req.side_effect = HTTPError(None, 404, None, None, None)
        assert not handler.is_collaborator(
            'commentUser', 'repo-owner', 'repo-name'
        )
        mock_api_req.assert_called_with(
            'GET',
            'https://api.github.com/repos/repo-owner/repo-name/collaborators/commentUser',
            None
        )

    @mock.patch('highfive.newpr.HighfiveHandler.api_req')
    def test_is_collaborator_error(self, mock_api_req):
        handler = HighfiveHandlerMock(Payload({})).handler
        mock_api_req.side_effect = HTTPError(None, 500, None, None, None)
        with pytest.raises(HTTPError):
            handler.is_collaborator(
                'commentUser', 'repo-owner', 'repo-name'
            )
        mock_api_req.assert_called_with(
            'GET',
            'https://api.github.com/repos/repo-owner/repo-name/collaborators/commentUser',
            None
        )

    @mock.patch('highfive.newpr.HighfiveHandler.api_req')
    def test_add_labels_success(self, mock_api_req):
        mock_api_req.return_value = {'body': 'response body!'}
        labels = ['label1', 'label2']
        handler = HighfiveHandlerMock(
            Payload({}), repo_config={'new_pr_labels': labels}
        ).handler
        assert handler.add_labels('repo-owner', 'repo-name', 7) is None
        mock_api_req.assert_called_with(
            'POST', 'https://api.github.com/repos/repo-owner/repo-name/issues/7/labels',
            labels
        )

    @mock.patch('highfive.newpr.HighfiveHandler.api_req')
    def test_add_labels_error(self, mock_api_req):
        mock_api_req.return_value = {}
        mock_api_req.side_effect = HTTPError(None, 422, None, None, None)
        labels = ['label1', 'label2']
        handler = HighfiveHandlerMock(
            Payload({}), repo_config={'new_pr_labels': labels}
        ).handler
        with pytest.raises(HTTPError):
            handler.add_labels('repo-owner', 'repo-name', 7)
        mock_api_req.assert_called_with(
            'POST', 'https://api.github.com/repos/repo-owner/repo-name/issues/7/labels',
            labels
        )

    def test_submodule(self):
        handler = HighfiveHandlerMock(Payload({})).handler
        submodule_diff = load_fake('submodule.diff')
        assert handler.modifies_submodule(submodule_diff)

        normal_diff = load_fake('normal.diff')
        assert not handler.modifies_submodule(normal_diff)

    def test_expected_branch_default_expected_no_match(self):
        payload = Payload(
            {'pull_request': {'base': {'label': 'repo-owner:dev'}}}
        )
        with HighfiveHandlerMock(payload, repo_config={}) as m:
            assert m.handler.unexpected_branch() == ('master', 'dev')

    def test_expected_branch_default_expected_match(self):
        payload = Payload(
            {'pull_request': {'base': {'label': 'repo-owner:master'}}}
        )
        with HighfiveHandlerMock(payload, repo_config={}) as m:
            assert not m.handler.unexpected_branch()

    def test_expected_branch_custom_expected_no_match(self):
        payload = Payload(
            {'pull_request': {'base': {'label': 'repo-owner:master'}}}
        )
        config = {'expected_branch': 'dev' }
        with HighfiveHandlerMock(payload, repo_config=config) as m:
            assert m.handler.unexpected_branch() == ('dev', 'master')

    def test_expected_branch_custom_expected_match(self):
        payload = Payload(
            {'pull_request': {'base': {'label':'repo-owner:dev'}}}
        )
        config = {'expected_branch': 'dev' }
        with HighfiveHandlerMock(payload, repo_config=config) as m:
            assert not m.handler.unexpected_branch()

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
        handler = HighfiveHandlerMock(Payload({})).handler

        for (msg, reviewer) in found_cases:
            assert handler.find_reviewer(msg) == reviewer, \
                "expected '%s' from '%s'" % (reviewer, msg)

        for msg in not_found_cases:
            assert handler.find_reviewer(msg) is None, \
                "expected '%s' to have no reviewer extracted" % msg

    def setup_get_irc_nick_mocks(self, mock_urllib2, status_code, data=None):
        if status_code != 200:
            mock_urllib2.side_effect = HTTPError(
                None, status_code, None, None, None
            )
            return

        mock_data = mock.Mock()
        mock_data.getcode.return_value = status_code
        mock_data.read.return_value = data
        mock_urllib2.urlopen.return_value = mock_data
        return mock_data

    @mock.patch('highfive.newpr.urllib2')
    def test_get_irc_nick_non_200(self, mock_urllib2):
        handler = HighfiveHandlerMock(Payload({})).handler
        self.setup_get_irc_nick_mocks(mock_urllib2, 503)
        assert handler.get_irc_nick('foo') is None

        mock_urllib2.urlopen.assert_called_with(
            'http://www.ncameron.org/rustaceans/user?username=foo'
        )

    @mock.patch('highfive.newpr.urllib2')
    def test_get_irc_nick_no_data(self, mock_urllib2):
        handler = HighfiveHandlerMock(Payload({})).handler
        mock_data = self.setup_get_irc_nick_mocks(mock_urllib2, 200, '[]')
        assert handler.get_irc_nick('foo') is None

        mock_urllib2.urlopen.assert_called_with(
            'http://www.ncameron.org/rustaceans/user?username=foo'
        )
        mock_data.getcode.assert_called()
        mock_data.read.assert_called()

    @mock.patch('highfive.newpr.urllib2')
    def test_get_irc_nick_has_data(self, mock_urllib2):
        handler = HighfiveHandlerMock(Payload({})).handler
        mock_data = self.setup_get_irc_nick_mocks(
            mock_urllib2, 200,
            '[{"username":"nrc","name":"Nick Cameron","irc":"nrc","email":"nrc@ncameron.org","discourse":"nrc","reddit":"nick29581","twitter":"@nick_r_cameron","blog":"https://www.ncameron.org/blog","website":"https://www.ncameron.org","notes":"<p>I work on the Rust compiler, language design, and tooling. I lead the dev tools team and am part of the core team. I&#39;m part of the research team at Mozilla.</p>\\n","avatar":"https://avatars.githubusercontent.com/nrc","irc_channels":["rust-dev-tools","rust","rust-internals","rust-lang","rustc","servo"]}]'
        )
        assert handler.get_irc_nick('nrc') == 'nrc'

        mock_urllib2.urlopen.assert_called_with(
            'http://www.ncameron.org/rustaceans/user?username=nrc'
        )
        mock_data.getcode.assert_called()
        mock_data.read.assert_called()

class TestApiReq(TestNewPR):
    @pytest.fixture(autouse=True)
    def make_defaults(cls, patcherize):
        cls.mocks = patcherize((
            ('urlopen', 'urllib2.urlopen'),
            ('Request', 'urllib2.Request'),
            ('StringIO', 'highfive.newpr.StringIO'),
            ('GzipFile', 'gzip.GzipFile'),
        ))

        cls.req = cls.mocks['Request'].return_value

        cls.res = cls.mocks['urlopen'].return_value
        cls.res.info.return_value = {'Content-Encoding': 'gzip'}

        cls.body = cls.res.read.return_value = 'body1'

        cls.gzipped_body = cls.mocks['GzipFile'].return_value.read
        cls.gzipped_body.return_value = 'body2'

        cls.handler = HighfiveHandlerMock(Payload({})).handler

        cls.method = 'METHOD'
        cls.url = 'https://foo.bar'

    def verify_mock_calls(self, header_calls, gzipped):
        self.mocks['Request'].assert_called_with(
            self.url, json.dumps(self.data) if self.data else self.data,
            {'Content-Type': 'application/json'} if self.data else {}
        )
        assert self.req.get_method() == 'METHOD'

        assert len(self.req.add_header.mock_calls) == len(header_calls)
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
        self.handler.integration_token = self.token
        return self.handler.api_req(
            self.method, self.url, self.data, media_type=self.media_type
        )

    def test1(self):
        """No data, no token, no media_type, header (gzip/no gzip)"""
        (self.data, self.token, self.media_type) = (None, None, None)

        assert self.call_api_req() == {
            'header': {'Content-Encoding': 'gzip'}, 'body': 'body2'
        }
        self.verify_mock_calls([], True)

    def test2(self):
        """Has data, no token, no media_type, response gzipped"""
        (self.data, self.token, self.media_type) = (
            {'some': 'data'}, None, None
        )

        assert self.call_api_req() == {
            'header': {'Content-Encoding': 'gzip'}, 'body': 'body2'
        }
        self.verify_mock_calls([], True)

    def test3(self):
        """Has data, has token, no media_type, response gzipped"""
        (self.data, self.token, self.media_type) = (
            {'some': 'data'}, 'credential', None
        )

        assert self.call_api_req() == {
            'header': {'Content-Encoding': 'gzip'}, 'body': 'body2'
        }
        calls = [
            mock.call('Authorization', 'token %s' % self.token),
        ]
        self.verify_mock_calls(calls, True)

    def test4(self):
        """Has data, no token, has media_type, response gzipped"""
        (self.data, self.token, self.media_type) = (
            {'some': 'data'}, None, 'this.media.type'
        )

        assert self.call_api_req() == {
            'header': {'Content-Encoding': 'gzip'}, 'body': 'body2'
        }
        calls = [
            mock.call('Accept', self.media_type),
        ]
        self.verify_mock_calls(calls, True)

    def test5(self):
        """Has data, has token, has media_type, response gzipped"""
        (self.data, self.token, self.media_type) = (
            {'some': 'data'}, 'credential', 'the.media.type'
        )

        assert self.call_api_req() == {
            'header': {'Content-Encoding': 'gzip'}, 'body': 'body2'
        }
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

        assert self.call_api_req() == {'header': {}, 'body': 'body1'}
        calls = [
            mock.call('Authorization', 'token %s' % self.token),
            mock.call('Accept', self.media_type),
        ]
        self.verify_mock_calls(calls, False)

class TestSetAssignee(TestNewPR):
    @pytest.fixture(autouse=True)
    def make_defaults(cls, patcherize):
        cls.mocks = patcherize((
            ('api_req', 'highfive.newpr.HighfiveHandler.api_req'),
            ('get_irc_nick', 'highfive.newpr.HighfiveHandler.get_irc_nick'),
            ('post_comment', 'highfive.newpr.HighfiveHandler.post_comment'),
            ('IrcClient', 'highfive.irc.IrcClient'),
        ))

        cls.mocks['client'] = cls.mocks['IrcClient'].return_value

        cls.handler = HighfiveHandlerMock(Payload({})).handler
        cls.assignee = 'assigneeUser'
        cls.author = 'authorUser'
        cls.owner = 'repo-owner'
        cls.repo = 'repo-name'
        cls.issue = 7
        cls.user = 'integrationUser'
        cls.token = 'integrationToken'

    def set_assignee(self, assignee='', to_mention=None):
        assignee = self.assignee if assignee == '' else assignee
        return self.handler.set_assignee(
            assignee, self.owner, self.repo, self.issue, self.user,
            self.author, to_mention or []
        )

    def assert_api_req_call(self, assignee=''):
        assignee = self.assignee if assignee == '' else assignee
        self.mocks['api_req'].assert_called_once_with(
            'PATCH',
            'https://api.github.com/repos/%s/%s/issues/%s' % (
                self.owner, self.repo, self.issue
            ), {"assignee": assignee}
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
        with pytest.raises(HTTPError):
            self.set_assignee()

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
            self.owner, self.repo, self.issue
        )

    def test_no_assignee(self):
        self.set_assignee(None)

        self.assert_api_req_call(None)
        self.mocks['get_irc_nick'].assert_not_called()
        self.mocks['IrcClient'].assert_not_called()
        self.mocks['client'].send_then_quit.assert_not_called()
        self.mocks['post_comment'].assert_not_called()

class TestIsNewContributor(TestNewPR):
    @pytest.fixture(autouse=True)
    def make_defaults(cls, patcherize):
        cls.mocks = patcherize((
            ('api_req', 'highfive.newpr.HighfiveHandler.api_req'),
        ))
        cls.payload = Payload({'repository': {'fork': False}})

        cls.username = 'commitUser'
        cls.owner = 'repo-owner'
        cls.repo = 'repo-name'
        cls.token = 'integrationToken'

    def is_new_contributor(self):
        handler = HighfiveHandlerMock(Payload(self.payload)).handler
        return handler.is_new_contributor(self.username, self.owner, self.repo)

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
            ), None, 'application/vnd.github.cloak-preview'
        )

    def test_is_new_contributor_fork(self):
        self.payload._payload['repository']['fork'] = True
        assert not self.is_new_contributor()
        self.mocks['api_req'].assert_not_called()

    def test_is_new_contributor_has_commits(self):
        self.mocks['api_req'].return_value = self.api_return(5)
        assert not self.is_new_contributor()
        self.assert_api_req_call()

    def test_is_new_contributor_no_commits(self):
        self.mocks['api_req'].return_value = self.api_return(0)
        assert self.is_new_contributor()
        self.assert_api_req_call()

    def test_is_new_contributor_nonexistent_user(self):
        self.mocks['api_req'].side_effect = HTTPError(None, 422, None, None, None)
        assert self.is_new_contributor()
        self.assert_api_req_call()

    def test_is_new_contributor_error(self):
        self.mocks['api_req'].side_effect = HTTPError(None, 403, None, None, None)
        with pytest.raises(HTTPError):
            self.is_new_contributor()
        self.assert_api_req_call()

class TestPostWarnings(TestNewPR):
    @pytest.fixture(autouse=True)
    def tpw_defaults(cls, patcherize):
        cls.mocks = patcherize((
            ('unexpected_branch', 'highfive.newpr.HighfiveHandler.unexpected_branch'),
            ('modifies_submodule', 'highfive.newpr.HighfiveHandler.modifies_submodule'),
            ('post_comment', 'highfive.newpr.HighfiveHandler.post_comment'),
        ))

        cls.payload = Payload({'the': 'payload'})
        cls.config = {'the': 'config'}
        cls.diff = 'the diff'
        cls.owner = 'repo-owner'
        cls.repo = 'repo-name'
        cls.issue = 7
        cls.token = 'integrationToken'

        cls.handler = HighfiveHandlerMock(
            cls.payload, repo_config=cls.config
        ).handler

    def post_warnings(self):
        self.handler.post_warnings(
            self.diff, self.owner, self.repo, self.issue
        )

    def test_no_warnings(self):
        self.mocks['unexpected_branch'].return_value = False
        self.mocks['modifies_submodule'].return_value = False

        self.post_warnings()

        self.mocks['unexpected_branch'].assert_called_once_with()
        self.mocks['modifies_submodule'].assert_called_with(self.diff)
        self.mocks['post_comment'].assert_not_called()

    def test_unexpected_branch(self):
        self.mocks['unexpected_branch'].return_value = (
            'master', 'something-else'
        )
        self.mocks['modifies_submodule'].return_value = False

        self.post_warnings()

        self.mocks['unexpected_branch'].assert_called_once_with()
        self.mocks['modifies_submodule'].assert_called_with(self.diff)

        expected_warning = """:warning: **Warning** :warning:

* Pull requests are usually filed against the master branch for this repo, but this one is against something-else. Please double check that you specified the right target!"""
        self.mocks['post_comment'].assert_called_with(
            expected_warning, self.owner, self.repo, self.issue
        )

    def test_modifies_submodule(self):
        self.mocks['unexpected_branch'].return_value = False
        self.mocks['modifies_submodule'].return_value = True

        self.post_warnings()

        self.mocks['unexpected_branch'].assert_called_once_with()
        self.mocks['modifies_submodule'].assert_called_with(self.diff)

        expected_warning = """:warning: **Warning** :warning:

* These commits modify **submodules**."""
        self.mocks['post_comment'].assert_called_with(
            expected_warning, self.owner, self.repo, self.issue
        )

    def test_unexpected_branch_modifies_submodule(self):
        self.mocks['unexpected_branch'].return_value = (
            'master', 'something-else'
        )
        self.mocks['modifies_submodule'].return_value = True

        self.post_warnings()

        self.mocks['unexpected_branch'].assert_called_once_with()
        self.mocks['modifies_submodule'].assert_called_with(self.diff)

        expected_warning = """:warning: **Warning** :warning:

* Pull requests are usually filed against the master branch for this repo, but this one is against something-else. Please double check that you specified the right target!
* These commits modify **submodules**."""
        self.mocks['post_comment'].assert_called_with(
            expected_warning, self.owner, self.repo, self.issue
        )

class TestNewPrFunction(TestNewPR):
    @pytest.fixture(autouse=True)
    def make_defaults(cls, patcherize):
        cls.mocks = patcherize((
            ('api_req', 'highfive.newpr.HighfiveHandler.api_req'),
            ('find_reviewer', 'highfive.newpr.HighfiveHandler.find_reviewer'),
            ('choose_reviewer', 'highfive.newpr.HighfiveHandler.choose_reviewer'),
            ('set_assignee', 'highfive.newpr.HighfiveHandler.set_assignee'),
            ('is_new_contributor', 'highfive.newpr.HighfiveHandler.is_new_contributor'),
            ('post_comment', 'highfive.newpr.HighfiveHandler.post_comment'),
            ('welcome_msg', 'highfive.newpr.HighfiveHandler.welcome_msg'),
            ('review_msg', 'highfive.newpr.HighfiveHandler.review_msg'),
            ('post_warnings', 'highfive.newpr.HighfiveHandler.post_warnings'),
            ('add_labels', 'highfive.newpr.HighfiveHandler.add_labels'),
        ))

        cls.mocks['api_req'].return_value = {'body': 'diff'}

        cls.payload = fakes.Payload.new_pr()
        cls.config = {'the': 'config', 'new_pr_labels': ['foo-label']}
        cls.user = 'integrationUser'
        cls.token = 'integrationToken'

    def call_new_pr(self):
        handler = HighfiveHandlerMock(
            self.payload, repo_config=self.config
        ).handler
        return handler.new_pr()

    def assert_set_assignee_branch_calls(self, reviewer, to_mention):
        self.mocks['api_req'].assert_called_once_with(
            'GET', 'https://the.url/', None, 'application/vnd.github.v3.diff'
        )
        self.mocks['find_reviewer'].assert_called_once_with('The PR comment.')
        self.mocks['set_assignee'].assert_called_once_with(
            reviewer, 'repo-owner', 'repo-name', '7', self.user, 'prAuthor',
            to_mention
        )
        self.mocks['is_new_contributor'].assert_called_once_with(
            'prAuthor', 'repo-owner', 'repo-name'
        )
        self.mocks['post_warnings'].assert_called_once_with(
            'diff', 'repo-owner', 'repo-name', '7'
        )

    def test_no_msg_reviewer_new_contributor(self):
        self.mocks['find_reviewer'].return_value = None
        self.mocks['choose_reviewer'].return_value = (
            'reviewUser', ['to', 'mention']
        )
        self.mocks['is_new_contributor'].return_value = True
        self.mocks['welcome_msg'].return_value = 'Welcome!'

        self.call_new_pr()

        self.assert_set_assignee_branch_calls('reviewUser', ['to', 'mention'])
        self.mocks['choose_reviewer'].assert_called_once_with(
            'repo-name', 'repo-owner', 'diff', 'prAuthor'
        )
        self.mocks['welcome_msg'].assert_called_once_with('reviewUser')
        self.mocks['review_msg'].assert_not_called()
        self.mocks['post_comment'].assert_called_once_with(
            'Welcome!', 'repo-owner', 'repo-name', '7'
        )
        self.mocks['add_labels'].assert_called_once_with(
            'repo-owner', 'repo-name', '7'
        )

    def test_no_msg_reviewer_repeat_contributor(self):
        self.mocks['find_reviewer'].return_value = None
        self.mocks['choose_reviewer'].return_value = (
            'reviewUser', ['to', 'mention']
        )
        self.mocks['is_new_contributor'].return_value = False
        self.mocks['review_msg'].return_value = 'Review message!'

        self.call_new_pr()

        self.assert_set_assignee_branch_calls('reviewUser', ['to', 'mention'])
        self.mocks['choose_reviewer'].assert_called_once_with(
            'repo-name', 'repo-owner', 'diff', 'prAuthor'
        )
        self.mocks['welcome_msg'].assert_not_called()
        self.mocks['review_msg'].assert_called_once_with(
            'reviewUser', 'prAuthor'
        )
        self.mocks['post_comment'].assert_called_once_with(
            'Review message!', 'repo-owner', 'repo-name', '7'
        )
        self.mocks['add_labels'].assert_called_once_with(
            'repo-owner', 'repo-name', '7'
        )

    def test_msg_reviewer_repeat_contributor(self):
        self.mocks['find_reviewer'].return_value = 'foundReviewer'
        self.mocks['is_new_contributor'].return_value = False
        self.mocks['welcome_msg'].return_value = 'Welcome!'

        self.call_new_pr()

        self.assert_set_assignee_branch_calls('foundReviewer', None)
        self.mocks['choose_reviewer'].assert_not_called()
        self.mocks['welcome_msg'].assert_not_called()
        self.mocks['review_msg'].assert_not_called()
        self.mocks['post_comment'].assert_not_called()
        self.mocks['add_labels'].assert_called_once_with(
            'repo-owner', 'repo-name', '7'
        )

    def test_assignee_already_set(self):
        self.payload._payload['pull_request']['assignees'] = [
            {'login': 'assignedUser'},
        ]

        self.call_new_pr()

        self.mocks['api_req'].assert_called_once_with(
            'GET', 'https://the.url/', None, 'application/vnd.github.v3.diff'
        )
        self.mocks['find_reviewer'].assert_not_called()
        self.mocks['choose_reviewer'].assert_not_called()
        self.mocks['set_assignee'].assert_not_called()
        self.mocks['is_new_contributor'].assert_not_called()
        self.mocks['welcome_msg'].assert_not_called()
        self.mocks['review_msg'].assert_not_called()
        self.mocks['post_comment'].assert_not_called()
        self.mocks['post_warnings'].assert_called_once_with(
            'diff', 'repo-owner', 'repo-name', '7'
        )

        self.mocks['add_labels'].assert_called_once_with(
            'repo-owner', 'repo-name', '7'
        )

    def test_no_pr_labels_specified(self):
        self.config = {'the': 'config'}
        self.mocks['find_reviewer'].return_value = 'foundReviewer'
        self.mocks['is_new_contributor'].return_value = True
        self.mocks['welcome_msg'].return_value = 'Welcome!'

        self.call_new_pr()

        self.assert_set_assignee_branch_calls('foundReviewer', None)
        self.mocks['choose_reviewer'].assert_not_called()
        self.mocks['welcome_msg'].assert_called_once_with('foundReviewer')
        self.mocks['review_msg'].assert_not_called()
        self.mocks['post_comment'].assert_called_once_with(
            'Welcome!', 'repo-owner', 'repo-name', '7'
        )
        self.mocks['add_labels'].assert_not_called()

    def test_empty_pr_labels(self):
        self.config = {
            'the': 'config', 'new_pr_labels': []
        }
        self.mocks['find_reviewer'].return_value = 'foundReviewer'
        self.mocks['is_new_contributor'].return_value = True
        self.mocks['welcome_msg'].return_value = 'Welcome!'

        self.call_new_pr()

        self.assert_set_assignee_branch_calls('foundReviewer', None)
        self.mocks['choose_reviewer'].assert_not_called()
        self.mocks['welcome_msg'].assert_called_once_with('foundReviewer')
        self.mocks['review_msg'].assert_not_called()
        self.mocks['post_comment'].assert_called_once_with(
            'Welcome!', 'repo-owner', 'repo-name', '7'
        )
        self.mocks['add_labels'].assert_not_called()

class TestNewComment(TestNewPR):
    @pytest.fixture(autouse=True)
    def make_mocks(cls, patcherize):
        cls.mocks = patcherize((
            ('is_collaborator', 'highfive.newpr.HighfiveHandler.is_collaborator'),
            ('find_reviewer', 'highfive.newpr.HighfiveHandler.find_reviewer'),
            ('set_assignee', 'highfive.newpr.HighfiveHandler.set_assignee'),
        ))

    @staticmethod
    def make_handler(
        state='open', is_pull_request=True, commenter='userA',
        repo='repo-name', owner='repo-owner', author='userB',
        comment='comment!', issue_number=7, assignee=None
    ):
        payload = Payload({
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
        })

        if is_pull_request:
            payload._payload['issue']['pull_request'] = {}
        if assignee is not None:
            payload._payload['issue']['assignee'] = {'login': assignee}

        return HighfiveHandlerMock(payload).handler

    def test_not_open(self):
        handler = self.make_handler(state='closed')

        assert handler.new_comment() is None
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_not_called()
        self.mocks['set_assignee'].assert_not_called()

    def test_not_pr(self):
        handler = self.make_handler(is_pull_request=False)

        handler.new_comment() is None
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_not_called()
        self.mocks['set_assignee'].assert_not_called()

    def test_commenter_is_integration_user(self):
        handler = self.make_handler(commenter='integrationUser')

        assert handler.new_comment() is None
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_not_called()
        self.mocks['set_assignee'].assert_not_called()

    def test_unauthorized_assigner(self):
        handler = self.make_handler(
            author='userA', commenter='userB', assignee='userC'
        )

        self.mocks['is_collaborator'].return_value = False
        assert handler.new_comment() is None
        self.mocks['is_collaborator'].assert_called_with(
            'userB', 'repo-owner', 'repo-name'
        )
        self.mocks['find_reviewer'].assert_not_called()
        self.mocks['set_assignee'].assert_not_called()

    # There are three ways to make it past the authorized assigner
    # check. The next three methods excercise those paths.
    def test_authorized_assigner_author_is_commenter(self):
        handler = self.make_handler(
            author='userA', commenter='userA', assignee='userC'
        )

        handler.new_comment()
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_called()

    def test_authorized_assigner_commenter_is_assignee(self):
        handler = self.make_handler(
            author='userA', commenter='userB', assignee='userB'
        )

        handler.new_comment()
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_called()

    def test_authorized_assigner_commenter_is_collaborator(self):
        handler = self.make_handler(
            author='userA', commenter='userB', assignee='userC'
        )

        self.mocks['is_collaborator'].return_value = True
        handler.new_comment()
        self.mocks['is_collaborator'].assert_called_with(
            'userB', 'repo-owner', 'repo-name'
        )
        self.mocks['find_reviewer'].assert_called()

    def test_no_reviewer(self):
        handler = self.make_handler(author='userA', commenter='userA')

        self.mocks['find_reviewer'].return_value = None
        handler.new_comment()
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_called_with('comment!')
        self.mocks['set_assignee'].assert_not_called()

    def test_has_reviewer(self):
        handler = self.make_handler(author='userA', commenter='userA')

        self.mocks['find_reviewer'].return_value = 'userD'
        handler.new_comment()
        self.mocks['is_collaborator'].assert_not_called()
        self.mocks['find_reviewer'].assert_called_with('comment!')
        self.mocks['set_assignee'].assert_called_with(
            'userD', 'repo-owner', 'repo-name', '7', 'integrationUser',
            'userA', None
        )

class TestChooseReviewer(TestNewPR):
    @pytest.fixture(autouse=True)
    def make_fakes(cls):
        cls.fakes = {
            'diff': {
                'normal': load_fake('normal.diff'),
            },
            'config': fakes.get_repo_configs(),
            'global_': fakes.get_global_configs(),
        }

    def choose_reviewer(
        self, repo, owner, diff, exclude, global_=None
    ):
        return self.choose_reviewer_inner(
            repo, owner, diff, exclude, global_
        )

    @mock.patch('highfive.newpr.HighfiveHandler._load_json_file')
    def choose_reviewer_inner(
        self, repo, owner, diff, exclude, global_, mock_load_json
    ):
        mock_load_json.return_value = deepcopy(global_ or { "groups": {} })
        return self.handler.choose_reviewer(
            repo, owner, diff, exclude
        )

    def choose_reviewers(self, diff, author, global_ = None):
        """Helper function that repeatedly calls choose_reviewer to build sets
        of reviewers and mentions for a given diff and author.
        """
        chosen_reviewers = set()
        mention_list = set()
        for _ in xrange(40):
            (reviewer, mentions) = self.choose_reviewer(
                'rust', 'rust-lang', diff, author, global_
            )
            chosen_reviewers.add(reviewer)
            mention_list.add(None if mentions is None else tuple(mentions))
        return chosen_reviewers, mention_list

    def test_individuals_no_dirs_1(self):
        """Test choosing a reviewer from a list of individual reviewers, no
        directories, and an author who is not a potential reviewer.
        """
        self.handler = HighfiveHandlerMock(
            Payload({}), repo_config=self.fakes['config']['individuals_no_dirs']
        ).handler
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.fakes['diff']['normal'], "nikomatsakis"
        )
        assert set(["pnkfelix", "nrc"]) == chosen_reviewers
        assert set([()]) == mentions

    def test_individuals_no_dirs_2(self):
        """Test choosing a reviewer from a list of individual reviewers, no
        directories, and an author who is a potential reviewer.
        """
        self.handler = HighfiveHandlerMock(
            Payload({}), repo_config=self.fakes['config']['individuals_no_dirs']
        ).handler
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.fakes['diff']['normal'], "nrc"
        )
        assert set(["pnkfelix"]) == chosen_reviewers
        assert set([()]) == mentions

    def test_circular_groups(self):
        """Test choosing a reviewer from groups that have circular references.
        """
        handler = HighfiveHandlerMock(
            Payload({}), repo_config=self.fakes['config']['circular_groups']
        ).handler
        with pytest.raises(AssertionError):
            handler.choose_reviewer(
                'rust', 'rust-lang', self.fakes['diff']['normal'], 'fooauthor'
            )

    def test_global_core(self):
        """Test choosing a reviewer from the core group in the global
        configuration.
        """
        self.handler = HighfiveHandlerMock(
            Payload({}), repo_config=self.fakes['config']['empty']
        ).handler
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.fakes['diff']['normal'], 'fooauthor',
            self.fakes['global_']['base']
        )
        assert set(['alexcrichton']) == chosen_reviewers
        assert set([()]) == mentions

    @mock.patch('highfive.newpr.HighfiveHandler._load_json_file')
    def test_global_group_overlap(self, mock_load_json):
        """Test for an AssertionError when the global config contains a group
        already defined in the config.
        """
        handler = HighfiveHandlerMock(
            Payload({}), repo_config=self.fakes['config']['individuals_no_dirs']
        ).handler
        mock_load_json.return_value = self.fakes['global_']['has_all']
        with pytest.raises(AssertionError):
            handler.choose_reviewer(
                'rust', 'rust-lang', self.fakes['diff']['normal'], 'fooauthor'
            )

    def test_no_potential_reviewers(self):
        """Test choosing a reviewer when nobody qualifies.
        """
        self.handler = HighfiveHandlerMock(
            Payload({}), repo_config=self.fakes['config']['empty']
        ).handler
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.fakes['diff']['normal'], 'alexcrichton',
            self.fakes['global_']['base']
        )
        assert set([None]) == chosen_reviewers
        assert set([None]) == mentions

    def test_with_dirs(self):
        """Test choosing a reviewer when directory reviewers are defined that
        intersect with the diff.
        """
        self.handler = HighfiveHandlerMock(
            Payload({}), repo_config=self.fakes['config']['individuals_dirs']
        ).handler
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.fakes['diff']['normal'], "nikomatsakis"
        )
        assert set(["pnkfelix", "nrc", "aturon"]) == chosen_reviewers
        assert set([()]) == mentions

    def test_with_dirs_no_intersection(self):
        """Test choosing a reviewer when directory reviewers are defined that
        do not intersect with the diff.
        """
        self.handler = HighfiveHandlerMock(
            Payload({}), repo_config=self.fakes['config']['individuals_dirs_2']
        ).handler
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.fakes['diff']['normal'], "nikomatsakis"
        )
        assert set(["pnkfelix", "nrc"]) == chosen_reviewers
        assert set([()]) == mentions

class TestRun(TestNewPR):
    @pytest.fixture(autouse=True)
    def make_mocks(cls, patcherize):
        cls.mocks = patcherize((
            ('new_pr', 'highfive.newpr.HighfiveHandler.new_pr'),
            ('new_comment', 'highfive.newpr.HighfiveHandler.new_comment'),
            ('sys', 'highfive.newpr.sys'),
        ))

    def handler_mock(self, payload):
        return HighfiveHandlerMock(
            payload, 'integration-user', 'integration-token'
        )

    def test_newpr(self):
        payload = Payload({'action': 'opened'})
        m = self.handler_mock(payload)
        m.handler.run()
        assert m.mock_config.get.call_count == 2
        self.mocks['new_pr'].assert_called_once_with()
        self.mocks['new_comment'].assert_not_called()
        self.mocks['sys'].exit.assert_not_called()

    def test_new_comment(self):
        payload = Payload({'action': 'created'})
        m = self.handler_mock(payload)
        m.handler.run()
        assert m.mock_config.get.call_count == 2
        self.mocks['new_pr'].assert_not_called()
        self.mocks['new_comment'].assert_called_once_with()
        self.mocks['sys'].exit.assert_not_called()

    def test_unsupported_payload(self):
        payload = Payload({'action': 'something-not-supported'})
        m = self.handler_mock(payload)
        m.handler.run()
        assert m.mock_config.get.call_count == 2
        self.mocks['new_pr'].assert_not_called()
        self.mocks['new_comment'].assert_not_called()
        self.mocks['sys'].exit.assert_called_once_with(0)
