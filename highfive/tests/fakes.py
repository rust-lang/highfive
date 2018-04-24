from highfive import payload
import json
import os

def get_fake_filename(name):
    return os.path.join(os.path.dirname(__file__), 'fakes', name)

class Payload(object):
    @staticmethod
    def new_pr(overrides):
        with open(get_fake_filename('open-pr.payload'), 'r') as fin:
            p = json.load(fin)
        p.update(overrides)

        return payload.Payload(p)
