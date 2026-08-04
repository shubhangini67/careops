from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class RestaurantProfileCreate(BaseModel):
    name:       str = Field(..., min_length=1, max_length=100)
    cuisine:    str = Field(default="pizza", max_length=100)
    capacity:   int = Field(default=70, ge=1, le=10000)
    peak_hours: str = Field(default="18:00-22:00", max_length=50)
    timezone:   str = Field(default="Asia/Kolkata", max_length=50)


class RestaurantProfileUpdate(BaseModel):
    name:       Optional[str] = Field(default=None, min_length=1, max_length=100)
    cuisine:    Optional[str] = Field(default=None, max_length=100)
    capacity:   Optional[int] = Field(default=None, ge=1, le=10000)
    peak_hours: Optional[str] = Field(default=None, max_length=50)
    timezone:   Optional[str] = Field(default=None, max_length=50)


class RestaurantProfileResponse(BaseModel):
    id:         int
    org_id:     int
    name:       str
    cuisine:    str
    capacity:   int
    peak_hours: str
    timezone:   str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RestaurantProfileListResponse(BaseModel):
    profiles: list[RestaurantProfileResponse]
