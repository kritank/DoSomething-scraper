from pydantic import BaseModel

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class RegisterAccountCookiesRequest(BaseModel):
    username: str
    sessionid: str
    csrftoken: str
    ds_user_id: str
    ig_did: str | None = None
    user_agent: str = _DEFAULT_UA
    locale: str = "en_US"
    timezone: str = "UTC"
    # Pin egress to a proxy (scheme://[user:pass@]host:port). None on a
    # re-register keeps any existing proxy; see InstagramAccountRepo.create.
    proxy: str | None = None


class RegisterAccountLoginRequest(BaseModel):
    username: str
    password: str
    user_agent: str = _DEFAULT_UA
    locale: str = "en_US"
    timezone: str = "UTC"
    proxy: str | None = None


class AccountProxyUpdate(BaseModel):
    # Empty/None clears the proxy (direct connection); a value sets it.
    proxy: str | None = None
