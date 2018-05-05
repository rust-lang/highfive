import mock
import os
import testtools


class BaseTest(testtools.TestCase):
    def setUp(self, patchers=None):
        super(BaseTest, self).setUp()

        patchers = patchers or ()
        self.patchers = {n: mock.patch(p) for n,p in patchers}
        self.mocks = {n: p.start() for n,p in self.patchers.iteritems()}

    def tearDown(self):
        super(BaseTest, self).tearDown()

        for patcher in self.patchers.itervalues():
            patcher.stop()

    @classmethod
    def _load_fake(cls, fake):
        fakes_dir = os.path.join(os.path.dirname(__file__), 'fakes')

        with open(os.path.join(fakes_dir, fake)) as fake:
            return fake.read()

