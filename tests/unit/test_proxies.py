from __future__ import annotations

from unittest.mock import MagicMock

from app.scraper.client import InstagramClient
from app.scraper.proxies import curl_proxies, playwright_proxy


class TestCurlProxies:
    def test_none_when_no_proxy(self):
        assert curl_proxies(None) is None
        assert curl_proxies("") is None

    def test_maps_scheme_to_url(self):
        assert curl_proxies("http://u:p@host:8000") == {
            "http": "http://u:p@host:8000",
            "https": "http://u:p@host:8000",
        }


class TestPlaywrightProxy:
    def test_none_when_no_proxy(self):
        assert playwright_proxy(None) is None
        assert playwright_proxy("") is None

    def test_splits_credentials_out_of_server(self):
        # Chromium ignores inline user:pass in `server`, so they must be lifted
        # into their own keys.
        assert playwright_proxy("http://user:pass@host.example:8000") == {
            "server": "http://host.example:8000",
            "username": "user",
            "password": "pass",
        }

    def test_no_credentials(self):
        assert playwright_proxy("socks5://10.0.0.1:1080") == {
            "server": "socks5://10.0.0.1:1080",
        }

    def test_no_port(self):
        assert playwright_proxy("http://proxy.example") == {"server": "http://proxy.example"}


class TestClientProxyWiring:
    def test_client_passes_proxy_to_curl_session(self, monkeypatch):
        captured = {}

        def fake_session(*_args, **kwargs):
            captured.update(kwargs)
            return MagicMock()

        monkeypatch.setattr("app.scraper.client.CurlAsyncSession", fake_session)
        InstagramClient(cookies={"sessionid": "s"}, user_agent="ua", proxy="http://h:1")
        assert captured["proxies"] == {"http": "http://h:1", "https": "http://h:1"}

    def test_client_without_proxy_passes_none(self, monkeypatch):
        captured = {}

        def fake_session(*_args, **kwargs):
            captured.update(kwargs)
            return MagicMock()

        monkeypatch.setattr("app.scraper.client.CurlAsyncSession", fake_session)
        InstagramClient(cookies={"sessionid": "s"}, user_agent="ua")
        assert captured["proxies"] is None
