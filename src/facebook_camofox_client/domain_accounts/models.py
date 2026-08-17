"""Account models."""
from pydantic import BaseModel

class Account(BaseModel):
    account_id: str
    profile_name: str = ""
    cookies_file: str | None = None
    proxy_config: dict | None = None