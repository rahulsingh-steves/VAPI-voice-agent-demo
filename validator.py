from pydantic import BaseModel, Field, validator
from typing import Optional
from dateutil import parser
from datetime import datetime



class CreateRequest(BaseModel):
    user_phone: str = Field(..., min_length=6)
    user_name: Optional[str] = ""
    purpose: Optional[str] = ""
    start_time: str

    @validator("start_time")
    def validate_time(cls, v):
        try:
            dt = parser.parse(v)
            if dt < datetime.utcnow():
                raise ValueError("Time must be in the future")
            return dt.isoformat()
        except Exception:
            raise ValueError("Invalid datetime format")



class CancelRequest(BaseModel):
    user_phone: str = Field(..., min_length=6)
    
    
class RescheduleRequest(BaseModel):
    user_phone: str = Field(..., min_length=6)
    new_time: str

    @validator("new_time")
    def validate_time(cls, v):
        try:
            dt = parser.parse(v)
            if dt < datetime.utcnow():
                raise ValueError("Time must be in the future")
            return dt.isoformat()
        except Exception:
            raise ValueError("Invalid datetime format")




