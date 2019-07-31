import mock
import pytest

from highfive import irc


@pytest.mark.unit
@pytest.mark.hermetic
class TestIrc(object):
    def test_send_and_join(self):
        with mock.patch('socket.socket') as mocked_socket:
            with mock.patch('time.sleep') as time:
                msocket = mock.MagicMock()
                mocked_socket.return_value = msocket

                client = irc.IrcClient('#rust-bots')
                msocket.connect.assert_called_once_with(("irc.mozilla.org", 6667))

                client.send_then_quit("test")
                msocket.send.assert_has_calls([
                    mock.call(b"USER rust-highfive rust-highfive rust-highfive :alert bot!\r\n"),
                    mock.call(b"NICK rust-highfive\r\n"),
                    mock.call(b"PRIVMSG #rust-bots :test\r\n"),
                    mock.call(b"QUIT :bot out\r\n"),
                ])
