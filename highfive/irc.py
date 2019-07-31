import socket
import time

class IrcClient(object):
    """ A simple IRC client to send a message and then leave.
    the calls to `time.sleep` are so the socket has time to recognize
    responses from the IRC protocol
    """
    def __init__(self, target, nick="rust-highfive", should_join=False):
        self.target = target.encode("utf-8")
        self.nick = nick.encode("utf-8")
        self.should_join = should_join
        self.ircsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ircsock.connect(("irc.mozilla.org", 6667))
        self.ircsock.send(b"USER " + self.nick + b" " + self.nick + b" " + self.nick + b" :alert bot!\r\n")
        self.ircsock.send(b"NICK " + self.nick + b"\r\n")
        time.sleep(2)

    def join(self):
        self.ircsock.send(b"JOIN " + self.targert + b"\r\n")

    def send(self, msg):
        if type(msg) == str:
            msg = msg.encode("utf-8")
        start = time.time()
        while True:
            if time.time() - start > 5:
                print("Timeout! EXITING")
                return
            ircmsg = self.ircsock.recv(2048).strip()
            #if ircmsg: print(ircmsg)

            if ircmsg.find(self.nick + b" +x") != -1:
                self.ircsock.send(b"PRIVMSG " + self.target + b" :" + msg + b"\r\n")
                return

    def quit(self):
        self.ircsock.send(b"QUIT :bot out\r\n")

    def send_then_quit(self, msg):
        if self.should_join:
            self.join()
        time.sleep(2)
        self.send(msg)
        time.sleep(3)
        self.quit()
