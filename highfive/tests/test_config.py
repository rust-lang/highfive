import pytest
import responses

from ..config import Config, InvalidTokenException


@pytest.mark.unit
@pytest.mark.hermetic
class TestConfig(object):
    def test_empty_token(self):
        for token in ['', None]:
            with pytest.raises(InvalidTokenException):
                Config(token)

    @responses.activate
    def test_valid_token(self):
        responses.add(
            responses.GET, 'https://api.github.com/user',
            json={'login': 'baz'},
        )

        config = Config('foobar')
        assert config.github_token == 'foobar'
        assert config.github_username == 'baz'

    @responses.activate
    def test_invalid_token(self):
        responses.add(responses.GET, 'https://api.github.com/user', status=403)

        with pytest.raises(InvalidTokenException):
            Config('foobar')
