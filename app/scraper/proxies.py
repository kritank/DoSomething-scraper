from __future__ import annotations
"""
Proxy-URL parsing for the two HTTP stacks that talk to Instagram: curl_cffi
(app.scraper.client, all read scraping) and Playwright (app.scraper.
login_automator, the one browser-driven login path).

An account is pinned to a single proxy at registration time and uses that
SAME egress IP for login, checkpoint resolution, and every scrape request.
A residential/mobile proxy per account is the thing that stops Instagram
flagging the session -- a cookie minted from one IP and then replayed from a
datacenter IP (e.g. EC2) looks like a hijacked session and trips the
"suspicious login"/checkpoint_required path. Keeping egress identical across
the account's whole lifetime is the point, mirroring how user_agent/locale/
timezone are pinned per account (see app.scraper.user_agents).

A proxy URL is the standard scheme://[user:pass@]host:port form, e.g.
    http://user:pass@residential.example.com:8000
    socks5://10.0.0.1:1080
"""

from urllib.parse import urlparse


def curl_proxies(proxy_url: str | None) -> dict[str, str] | None:
    """curl_cffi's AsyncSession takes a requests-style {scheme: url} mapping.
    Return None (not an empty dict) when no proxy is set, so the caller can
    pass it straight through to `proxies=` without special-casing."""
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def playwright_proxy(proxy_url: str | None) -> dict[str, str] | None:
    """Playwright wants the credentials split out of the server URL:
    {"server": "scheme://host:port", "username": ..., "password": ...}.
    Passing user:pass inline in `server` is silently ignored by Chromium,
    so they must be lifted into their own keys here."""
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    host = parsed.hostname or ""
    server = f"{parsed.scheme}://{host}"
    if parsed.port is not None:
        server = f"{server}:{parsed.port}"
    proxy: dict[str, str] = {"server": server}
    if parsed.username:
        proxy["username"] = parsed.username
    if parsed.password:
        proxy["password"] = parsed.password
    return proxy
