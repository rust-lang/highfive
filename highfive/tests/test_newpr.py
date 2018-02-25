from copy import deepcopy
from highfive import newpr
from highfive.tests import base
import json
import mock

class TestNewPR(base.BaseTest):
    pass

class TestNewPRGeneral(TestNewPR):
    @mock.patch('os.path.dirname')
    def test_load_json_file(self, mock_dirname):
        mock_dirname.return_value = '/the/path'
        contents = ['some json']
        with mock.patch(
            '__builtin__.open', mock.mock_open(read_data=json.dumps(contents))
        ) as mock_file:
            self.assertEqual(newpr._load_json_file('a-config.json'), contents)
            mock_file.assert_called_with('/the/path/configs/a-config.json')

    def test_submodule(self):
        submodule_diff = self._load_fake('submodule.diff')
        self.assertTrue(newpr.modifies_submodule(submodule_diff))

        normal_diff = self._load_fake('normal.diff')
        self.assertFalse(newpr.modifies_submodule(normal_diff))

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

        for (msg, reviewer) in found_cases:
            self.assertEqual(
                newpr.find_reviewer(msg), reviewer,
                "expected '%s' from '%s'" % (reviewer, msg)
            )

        for msg in not_found_cases:
            self.assertIsNone(
                newpr.find_reviewer(msg),
                "expected '%s' to have no reviewer extracted" % msg
            )

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
            'individuals_dirs' :{
                "groups": { "all": ["@pnkfelix", "@nrc"] },
                "dirs": { "librustc": ["@aturon"] },
            },
            'individuals_dirs_2' :{
                "groups": { "all": ["@pnkfelix", "@nrc"] },
                "dirs": { "foobazdir": ["@aturon"] },
            },
            'circular_groups': {
                "groups": {
                    "all": ["some"],
                    "some": ["all"],
                },
            },
            'empty' :{
                "groups": { "all": [] },
                "dirs": {},
            },
        }
        cls.global_ = {
            'base': {
                "groups": {
                    "core": ["@alexcrichton"],
                }
            },
            'has_all': {
                "groups": { "all": ["@alexcrichton"] }
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

    def test_unsupported_repo(self):
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
        mention_list = set()
        for _ in xrange(40):
            (reviewer, mentions) = self.choose_reviewer(
                'rust', 'rust-lang', diff, author, deepcopy(config), global_
            )
            chosen_reviewers.add(reviewer)
            mention_list.add(None if mentions is None else tuple(mentions))
        return chosen_reviewers, mention_list

    def test_individuals_no_dirs_1(self):
        """Test choosing a reviewer from a list of individual reviewers, no
        directories, and an author who is not a potential reviewer.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['individuals_no_dirs'],
            "nikomatsakis"
        )
        self.assertEqual(set(["pnkfelix", "nrc"]), chosen_reviewers)
        self.assertEqual(set([()]), mentions)

    def test_individuals_no_dirs_2(self):
        """Test choosing a reviewer from a list of individual reviewers, no
        directories, and an author who is a potential reviewer.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['individuals_no_dirs'], "nrc"
        )
        self.assertEqual(set(["pnkfelix"]), chosen_reviewers)
        self.assertEqual(set([()]), mentions)

    def test_circular_groups(self):
        """Test choosing a reviewer from groups that have circular references.
        """
        self.assertRaises(
            AssertionError, newpr.choose_reviewer, 'rust', 'rust-lang',
            self.diff['normal'], 'fooauthor',
            self.config['circular_groups']
        )

    def test_global_core(self):
        """Test choosing a reviewer from the core group in the global
        configuration.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['empty'], 'fooauthor',
            self.global_['base']
        )
        self.assertEqual(set(['alexcrichton']), chosen_reviewers)
        self.assertEqual(set([()]), mentions)

    @mock.patch('highfive.newpr._load_json_file')
    def test_global_group_overlap(self, mock_load_json):
        """Test for an AssertionError when the global config contains a group
        already defined in the config.
        """
        mock_load_json.return_value = self.global_['has_all']
        self.assertRaises(
            AssertionError, newpr.choose_reviewer, 'rust', 'rust-lang',
            self.diff['normal'], 'fooauthor',
            self.config['individuals_no_dirs']
        )

    def test_no_potential_reviewers(self):
        """Test choosing a reviewer when nobody qualifies.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['empty'], 'alexcrichton',
            self.global_['base']
        )
        self.assertEqual(set([None]), chosen_reviewers)
        self.assertEqual(set([None]), mentions)

    def test_with_dirs(self):
        """Test choosing a reviewer when directory reviewers are defined that
        intersect with the diff.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['individuals_dirs'],
            "nikomatsakis"
        )
        self.assertEqual(set(["pnkfelix", "nrc", "aturon"]), chosen_reviewers)
        self.assertEqual(set([()]), mentions)

    def test_with_dirs_no_intersection(self):
        """Test choosing a reviewer when directory reviewers are defined that
        do not intersect with the diff.
        """
        (chosen_reviewers, mentions) = self.choose_reviewers(
            self.diff['normal'], self.config['individuals_dirs_2'],
            "nikomatsakis"
        )
        self.assertEqual(set(["pnkfelix", "nrc"]), chosen_reviewers)
        self.assertEqual(set([()]), mentions)
