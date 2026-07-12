from typing import Literal

from pydantic import BaseModel


class AlertOut(BaseModel):
    severity: Literal["critical", "warning", "info"]
    message: str
