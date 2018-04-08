class Payload(object):
    """This class manages access to the GitHub payloads provided via the
    webhook. "Deep indexing" is provided by indexing a comma-separated
    list of keys, rather than the [k1][k2]...[kn] syntax.

    The advantage of this wrapper around the payload dict is that
    special behavior can be centralized in this class, as opposed to
    in the code accessing the payload.
    """
    def __init__(self, payload):
        self._payload = payload

    def __getitem__(self, keys):
        if isinstance(keys, str):
            keys = (keys,)

        inc = self._payload
        for k in keys:
            inc = inc[k]

        return inc
