from pydantic import BaseModel
from typing import List

class BaseRequest(BaseModel):
    DesiredService: str
    desc: str

class UserRequest(BaseModel):
    requests: List[BaseRequest]