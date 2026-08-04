from pydantic import BaseModel, Field


class OrgSettings(BaseModel):
    capacity:               int   = Field(default=70,    ge=1,   le=10000, description="Restaurant seating capacity")
    timezone:               str   = Field(default="Asia/Kolkata")
    cuisine_type:           str   = Field(default="pizza")
    peak_hours:             str   = Field(default="18:00-22:00")
    critic_threshold:       float = Field(default=0.7,   ge=0.0, le=1.0,  description="Min critic score to auto-approve")
    low_stock_threshold_pct: float = Field(default=20.0, ge=0.0, le=100.0, description="% below which stock is flagged low")
    overstock_threshold_pct: float = Field(default=150.0, ge=0.0,          description="% of capacity above which stock is flagged excess (e.g. 150 = 1.5x capacity)")


class OrgSettingsResponse(BaseModel):
    org_id:   int
    org_name: str
    settings: OrgSettings
