from copy import deepcopy
from highfive.payload import Payload
from highfive.tests import base
import json
import mock
from nose.plugins.attrib import attr
import unittest

@attr(type='unit')
class TestPayload(base.BaseTest):
    @classmethod
    def setUpClass(cls):
        cls.payload = Payload(json.loads(cls._load_fake('open-pr.payload')))

    def test_get_attr(self):
        self.assertEqual(self.payload['pull_request', 'state'], 'open')
        self.assertEqual(self.payload['number'], 1)

    def test_get_attr_not_found(self):
        self.assertRaises(KeyError, self.payload.__getitem__, 'foo')
        self.assertRaises(KeyError, self.payload.__getitem__, ['foo', 'bar'])
        self.assertRaises(
            KeyError, self.payload.__getitem__, ['pull_request', 'baz']
        )
