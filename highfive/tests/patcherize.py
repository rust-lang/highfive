import mock
import pytest


@pytest.fixture
def patcherize():
    patchers = {}

    def _patcherize(patcher_names=None):
        for n, p in (patcher_names or ()):
            patchers[n] = mock.patch(p)
        return {n: p.start() for n, p in patchers.items()}

    yield _patcherize

    for patcher in patchers.values():
        patcher.stop()
