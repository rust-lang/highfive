from highfive import newpr
from highfive.tests import base
from nose.plugins.attrib import attr

@attr(type='integration')
class TestIsNewContributor(base.BaseTest):
    def setUp(self):
        super(TestIsNewContributor, self).setUp()

        self.payload = {'repository': {'fork': False}}        

    def test_real_contributor_true(self):
        self.assertTrue(
            newpr.is_new_contributor(
                'nrc', 'rust-lang', 'rust', '', None, self.payload
            )
        )

    def test_real_contributor_false(self):
        self.assertFalse(
            newpr.is_new_contributor(
                'octocat', 'rust-lang', 'rust', '', None, self.payload
            )
        )

    def test_fake_user(self):
        self.assertFalse(
            newpr.is_new_contributor(
                'fjkesfgojsrgljsdgla', 'rust-lang', 'rust', '', None, self.payload
            )
        )
