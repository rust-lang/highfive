import os

import testtools


class BaseTest(testtools.TestCase):
    @classmethod
    def _load_fake(cls, fake):
        fakes_dir = os.path.join(os.path.dirname(__file__), 'fakes')

        with open(os.path.join(fakes_dir, fake)) as fake:
            return fake.read()

