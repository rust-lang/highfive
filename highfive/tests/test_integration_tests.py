import mock
import pytest
import responses

from highfive import newpr, payload
from highfive.config import Config
from highfive.tests import fakes
from highfive.tests.test_newpr import HighfiveHandlerMock
from highfive.tests.patcherize import patcherize


@pytest.mark.integration
class TestIsNewContributor(object):
    @pytest.fixture(autouse=True)
    def mock_handler(cls):
        cls.handler = HighfiveHandlerMock(
            payload.Payload({'repository': {'fork': False}}), integration_token=''
        ).handler

    def test_real_contributor_true(self):
        assert not self.handler.is_new_contributor('nrc', 'rust-lang', 'rust')

    def test_real_contributor_false(self):
        assert self.handler.is_new_contributor('octocat', 'rust-lang', 'rust')

    def test_fake_user(self):
        assert self.handler.is_new_contributor(
            'fjkesfgojsrgljsdgla', 'rust-lang', 'rust'
        )


class ApiReqMocker(object):
    def __init__(self, calls_and_returns):
        self.calls = [(c[0],) for c in calls_and_returns]
        self.patcher = mock.patch('highfive.newpr.HighfiveHandler.api_req')
        self.mock = self.patcher.start()
        self.mock.side_effect = [c[1] for c in calls_and_returns]

    def verify_calls(self):
        self.patcher.stop()

        for (expected, actual) in zip(self.calls, self.mock.call_args_list):
            assert expected == actual, 'Expected call with args %s, got %s' % (
                str(expected), str(actual)
            )

        assert self.mock.call_count == len(self.calls)


def dummy_config():
    with responses.RequestsMock() as resp:
        resp.add(
            responses.GET, 'https://api.github.com/user',
            json={'login': 'integration-user'},
        )
        return Config('integration_token')


@pytest.mark.integration
@pytest.mark.hermetic
class TestNewPr(object):
    @pytest.fixture(autouse=True)
    def make_mocks(cls, patcherize):
        cls.mocks = patcherize((
            ('ConfigParser', 'highfive.newpr.ConfigParser'),
            ('load_json_file', 'highfive.newpr.HighfiveHandler._load_json_file'),
        ))

        cls.mocks['load_json_file'].side_effect = (
            fakes.get_repo_configs()['individuals_no_dirs'],
            fakes.get_global_configs()['base'],
        )

    def test_new_pr_non_contributor(self):
        payload = fakes.Payload.new_pr(
            repo_owner='rust-lang', repo_name='rust', pr_author='pnkfelix'
        )
        handler = newpr.HighfiveHandler(payload, dummy_config())

        api_req_mock = ApiReqMocker([
            (
                (
                    'GET', 'https://the.url/', None,
                    'application/vnd.github.v3.diff'
                ),
                {'body': fakes.load_fake('normal.diff')},
            ),
            (
                (
                    'PATCH', newpr.issue_url % ('rust-lang', 'rust', '7'),
                    {'assignee': 'nrc'}
                ),
                {'body': {}},
            ),
            (
                (
                    'GET', newpr.commit_search_url % ('rust-lang', 'rust', 'pnkfelix'),
                    None, 'application/vnd.github.cloak-preview'
                ),
                {'body': '{"total_count": 0}'},
            ),
            (
                (
                    'POST', newpr.post_comment_url % ('rust-lang', 'rust', '7'),
                    {
                        'body': "Thanks for the pull request, and welcome! The Rust team is excited to review your changes, and you should hear from @nrc (or someone else) soon.\n\nPlease see [the contribution instructions](https://rustc-dev-guide.rust-lang.org/contributing.html) for more information.\n"}
                ),
                {'body': {}},
            ),
        ])
        handler.new_pr()

        api_req_mock.verify_calls()

    def test_new_pr_empty_body(self):
        payload = fakes.Payload.new_pr(
            repo_owner='rust-lang', repo_name='rust', pr_author='pnkfelix',
            pr_body=None,
        )
        handler = newpr.HighfiveHandler(payload, dummy_config())

        api_req_mock = ApiReqMocker([
            (
                (
                    'GET', 'https://the.url/', None,
                    'application/vnd.github.v3.diff'
                ),
                {'body': fakes.load_fake('normal.diff')},
            ),
            (
                (
                    'PATCH', newpr.issue_url % ('rust-lang', 'rust', '7'),
                    {'assignee': 'nrc'}
                ),
                {'body': {}},
            ),
            (
                (
                    'GET', newpr.commit_search_url % ('rust-lang', 'rust', 'pnkfelix'),
                    None, 'application/vnd.github.cloak-preview'
                ),
                {'body': '{"total_count": 0}'},
            ),
            (
                (
                    'POST', newpr.post_comment_url % ('rust-lang', 'rust', '7'),
                    {
                        'body': "Thanks for the pull request, and welcome! The Rust team is excited to review your changes, and you should hear from @nrc (or someone else) soon.\n\nPlease see [the contribution instructions](https://rustc-dev-guide.rust-lang.org/contributing.html) for more information.\n"}
                ),
                {'body': {}},
            ),
        ])
        handler.new_pr()

        api_req_mock.verify_calls()

    def test_new_pr_contributor(self):
        payload = fakes.Payload.new_pr(
            repo_owner='rust-lang', repo_name='rust', pr_author='pnkfelix'
        )
        handler = newpr.HighfiveHandler(payload, dummy_config())

        api_req_mock = ApiReqMocker([
            (
                (
                    'GET', 'https://the.url/', None,
                    'application/vnd.github.v3.diff'
                ),
                {'body': fakes.load_fake('normal.diff')},
            ),
            (
                (
                    'PATCH', newpr.issue_url % ('rust-lang', 'rust', '7'),
                    {'assignee': 'nrc'}
                ),
                {'body': {}},
            ),
            (
                (
                    'GET', newpr.commit_search_url % ('rust-lang', 'rust', 'pnkfelix'),
                    None, 'application/vnd.github.cloak-preview'
                ),
                {'body': '{"total_count": 1}'},
            ),
            (
                (
                    'POST', newpr.post_comment_url % ('rust-lang', 'rust', '7'),
                    {'body': 'r? @nrc\n\n(rust-highfive has picked a reviewer for you, use r? to override)'}
                ),
                {'body': {}},
            ),
        ])
        handler.new_pr()

        api_req_mock.verify_calls()

    def test_new_pr_contributor_with_labels(self):
        self.mocks['load_json_file'].side_effect = (
            fakes.get_repo_configs()['individuals_no_dirs_labels'],
            fakes.get_global_configs()['base'],
        )
        payload = fakes.Payload.new_pr(
            repo_owner='rust-lang', repo_name='rust', pr_author='pnkfelix'
        )
        handler = newpr.HighfiveHandler(payload, dummy_config())

        api_req_mock = ApiReqMocker([
            (
                (
                    'GET', 'https://the.url/', None,
                    'application/vnd.github.v3.diff'
                ),
                {'body': fakes.load_fake('normal.diff')},
            ),
            (
                (
                    'PATCH', newpr.issue_url % ('rust-lang', 'rust', '7'),
                    {'assignee': 'nrc'}
                ),
                {'body': {}},
            ),
            (
                (
                    'GET', newpr.commit_search_url % ('rust-lang', 'rust', 'pnkfelix'),
                    None, 'application/vnd.github.cloak-preview'
                ),
                {'body': '{"total_count": 1}'},
            ),
            (
                (
                    'POST', newpr.post_comment_url % ('rust-lang', 'rust', '7'),
                    {'body': 'r? @nrc\n\n(rust-highfive has picked a reviewer for you, use r? to override)'}
                ),
                {'body': {}},
            ),
            (
                (
                    'POST', newpr.issue_labels_url % ('rust-lang', 'rust', '7'),
                    ['a', 'b']
                ),
                {'body': {}},
            ),
        ])
        handler.new_pr()

        api_req_mock.verify_calls()


@pytest.mark.integration
@pytest.mark.hermetic
class TestNewComment(object):
    @pytest.fixture(autouse=True)
    def make_mocks(cls, patcherize):
        cls.mocks = patcherize((
            ('ConfigParser', 'highfive.newpr.ConfigParser'),
            ('load_json_file', 'highfive.newpr.HighfiveHandler._load_json_file'),
        ))

        config_mock = mock.Mock()
        config_mock.get.side_effect = ('integration-user', 'integration-token')
        cls.mocks['ConfigParser'].RawConfigParser.return_value = config_mock
        cls.mocks['load_json_file'].side_effect = (
            fakes.get_repo_configs()['individuals_no_dirs'],
            fakes.get_global_configs()['base'],
        )

    def test_author_is_commenter(self):
        payload = fakes.Payload.new_comment()
        handler = newpr.HighfiveHandler(payload, dummy_config())
        api_req_mock = ApiReqMocker([
            (
                (
                    'PATCH', newpr.issue_url % ('rust-lang', 'rust', '1'),
                    {'assignee': 'davidalber'}
                ),
                {'body': {}},
            ),
        ])
        handler.new_comment()
        api_req_mock.verify_calls()

    def test_author_not_commenter_is_collaborator(self):
        payload = fakes.Payload.new_comment()
        payload._payload['issue']['user']['login'] = 'foouser'

        handler = newpr.HighfiveHandler(payload, dummy_config())
        api_req_mock = ApiReqMocker([
            (
                (
                    "GET",
                    newpr.user_collabo_url % (
                        'rust-lang', 'rust', 'davidalber'
                    ),
                    None
                ),
                {'body': {}},
            ),
            (
                (
                    'PATCH', newpr.issue_url % ('rust-lang', 'rust', '1'),
                    {'assignee': 'davidalber'}
                ),
                {'body': {}},
            ),
        ])
        handler.new_comment()
        api_req_mock.verify_calls()
