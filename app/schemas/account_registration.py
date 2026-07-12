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


class RegisterAccountLoginRequest(BaseModel):
    username: str
    password: str
    user_agent: str = _DEFAULT_UA
    locale: str = "en_US"
    timezone: str = "UTC"
