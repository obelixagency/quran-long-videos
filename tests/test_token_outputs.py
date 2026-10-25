"""Offline canary tests; no credentials, network calls, or uploads."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import traceback
import types
import unittest
from unittest.mock import patch

# The suite can run in a minimal offline Python environment.
try:
    import requests
except ImportError:
    requests = types.ModuleType('requests')
    requests.RequestException = type('RequestException', (Exception,), {})
    for method in ('get', 'post', 'put'):
        setattr(requests, method, lambda *a, **k: None)
    sys.modules['requests'] = requests
from long import youtube, safe_http

CANARY = 'synthetic-secret-canary-DO-NOT-LOG'


def response(data=None, status=200, headers=None):
    return types.SimpleNamespace(status_code=status, headers=headers or {}, text=CANARY,
                                 json=lambda: data)


class TokenOutputTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, dict(YT_CLIENT_ID=CANARY, YT_CLIENT_SECRET=CANARY,
                                               YT_REFRESH_TOKEN=CANARY, YT_CHANNEL_ID='channel'))
        self.env.start()
        self.addCleanup(self.env.stop)

    def assert_safe_failure(self, call):
        try:
            call()
        except Exception:
            text = traceback.format_exc()
            self.assertNotIn(CANARY, text)
            return text
        self.fail('Expected a failure')

    def test_transport_traceback_never_exposes_url(self):
        for method in ('get', 'post', 'put'):
            with self.subTest(method=method), patch.object(requests, method,
                    side_effect=requests.RequestException('https://upload.example/?token=' + CANARY)):
                self.assert_safe_failure(lambda: getattr(safe_http, method)('https://example.test'))

    def test_invalid_json_is_generic(self):
        raw = response()
        raw.json = lambda: (_ for _ in ()).throw(ValueError(CANARY))
        with patch.object(requests, 'post', return_value=raw):
            self.assert_safe_failure(youtube._token)

    def test_refresh_error_body_is_not_logged(self):
        with patch.object(requests, 'post', return_value=response({'error':CANARY,'error_description':CANARY},400)):
            self.assertIn('HTTP 400', self.assert_safe_failure(youtube._token))

    def test_refresh_success_unchanged(self):
        with patch.object(requests, 'post', return_value=response({'access_token':CANARY})):
            self.assertEqual(youtube._token(), CANARY)

    def test_playlist_failure_never_persists_exception(self):
        with patch.object(youtube, '_playlist_id', side_effect=RuntimeError(CANARY)):
            self.assertNotIn(CANARY, youtube.add_to_playlist('video', 'playlist', {'Authorization':'Bearer '+CANARY}))

    def test_playlist_creation_body_not_logged(self):
        with patch.object(requests,'get',return_value=response({'items':[]})), patch.object(requests,'post',return_value=response({},400)):
            self.assert_safe_failure(lambda: youtube._playlist_id({},'playlist'))

    def test_upload_init_body_not_logged(self):
        with tempfile.NamedTemporaryFile() as f, patch.object(youtube,'_token',return_value=CANARY), patch.object(youtube,'channel',return_value={'snippet':{'title':'name'}}), patch.object(requests,'post',return_value=response({},400)):
            self.assert_safe_failure(lambda: youtube.upload(f.name, {'title':'title','description':'desc','tags':[],'lang':'en'}))

    def test_upload_success_and_retry_no_secret_output(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(b'video'); f.flush()
            with patch.object(youtube,'_token',return_value=CANARY), patch.object(youtube,'channel',return_value={'snippet':{'title':'name'}}), patch.object(requests,'post',return_value=response({},headers={'Location':'https://upload.example/?token='+CANARY})), patch.object(requests,'put',side_effect=[requests.RequestException(CANARY),response({'id':'video','status':{'privacyStatus':'public'}})]), patch.object(youtube.time,'sleep'), contextlib.redirect_stdout(io.StringIO()) as output:
                result=youtube.upload(f.name,{'title':'title','description':'desc','tags':[],'lang':'en'})
                self.assertEqual(result['url'],'https://youtu.be/video')
                self.assertNotIn(CANARY, output.getvalue())
                self.assertNotIn(CANARY, str(result))

    def test_workflow_no_raw_api_body_output(self):
        for path in Path('.github/workflows').glob('*.yml'):
            self.assertNotIn('r.text',path.read_text(),path)


if __name__ == '__main__':
    unittest.main()
