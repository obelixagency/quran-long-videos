"""Credential-bearing HTTP calls: never expose response bodies or request URLs."""
import requests

RequestException = requests.RequestException


class Response:
    def __init__(self, response):
        self._response = response

    def __getattr__(self, name):
        return getattr(self._response, name)

    def json(self):
        try:
            return self._response.json()
        except ValueError:
            raise RuntimeError("API returned invalid JSON") from None


def _call(method, *args, **kwargs):
    try:
        return Response(getattr(requests, method)(*args, **kwargs))
    except requests.RequestException:
        # Resumable-upload URLs are bearer credentials too. Do not chain the
        # original exception: its traceback may contain that URL or a token.
        raise RequestException("API transport failed (details withheld)") from None


def get(*args, **kwargs):
    return _call("get", *args, **kwargs)


def post(*args, **kwargs):
    return _call("post", *args, **kwargs)


def put(*args, **kwargs):
    return _call("put", *args, **kwargs)
