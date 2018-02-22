from copy import deepcopy
from highfive import newpr
from highfive.tests import base
import mock

class TestNewPR(base.BaseTest):
    pass

class TestSubmodule(TestNewPR):
    def test_submodule(self):
        submodule_diff = self._load_fake('submodule.diff')
        self.assertTrue(newpr.modifies_submodule(submodule_diff))

        normal_diff = self._load_fake('normal.diff')
        self.assertFalse(newpr.modifies_submodule(normal_diff))

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
            'empty' :{
                "groups": { "all": [] },
                "dirs": {},
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

    def test_choose_reviewer_unsupported_repo(self):
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
        mentions = set()
        for _ in xrange(40):
            reviewer = self.choose_reviewer(
                'rust', 'rust-lang', diff, author, deepcopy(config), global_
            )
            chosen_reviewers.add(reviewer[0])
            mentions.add(tuple(reviewer[1]))
        return chosen_reviewers, mentions

    def test_choose_reviewer_individuals_no_dirs_1(self):
        """Test choosing a reviewer from a list of individual reviewers, no
        directories, and an author who is not a potential reviewer.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['individuals_no_dirs'],
            "nikomatsakis"
        )
        self.assertEqual(set(["pnkfelix", "nrc"]), chosen_reviewers)
        self.assertEqual(set([()]), mentions)

    def test_choose_reviewer_individuals_no_dirs_2(self):
        """Test choosing a reviewer from a list of individual reviewers, no
        directories, and an author who is a potential reviewer.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['individuals_no_dirs'], "nrc"
        )
        self.assertEqual(set(["pnkfelix"]), chosen_reviewers)
        self.assertEqual(set([()]), mentions)

    def test_choose_reviewer_global_core(self):
        """Test choosing a reviewer from the core group in the global
        configuration.
        """
        global_ = {
            "groups": {
                "core": ["@alexcrichton"],
            }
        }

        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['empty'], 'fooauthor', global_
        )
        self.assertEqual(set(['alexcrichton']), chosen_reviewers)
        self.assertEqual(set([()]), mentions)
