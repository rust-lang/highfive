import json

import pytest

from highfive.payload import Payload
from highfive.tests.fakes import load_fake


@pytest.mark.unit
@pytest.mark.hermetic
class TestPayload(object):
    @pytest.fixture(autouse=True)
    def make_payload(cls):
        cls.payload = Payload(json.loads(load_fake('open-pr.payload')))

    def test_get_attr(self):
        assert self.payload['pull_request', 'state'] == 'open'
        assert self.payload['number'] == 1

    def test_get_attr_not_found(self):
        with pytest.raises(KeyError):
            self.payload.__getitem__('foo')

        with pytest.raises(KeyError):
            self.payload.__getitem__(['foo', 'bar'])

        with pytest.raises(KeyError):
            self.payload.__getitem__(['pull_request', 'baz'])
