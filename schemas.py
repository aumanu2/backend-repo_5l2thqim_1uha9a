"""
Database Schemas for WeathAware

Each Pydantic model represents a MongoDB collection. The collection name is the lowercase
of the class name (e.g., User -> "user").
"""
from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="Hashed password")
    created_at: Optional[datetime] = None
    is_active: bool = True

class FlightPlan(BaseModel):
    user_id: str = Field(..., description="Owner user id")
    callsign: Optional[str] = Field(None, description="Callsign")
    origin: str = Field(..., min_length=3, max_length=4, description="ICAO origin")
    destination: str = Field(..., min_length=3, max_length=4, description="ICAO destination")
    alternates: List[str] = Field(default_factory=list, description="Alternate ICAOs")
    route: Optional[str] = Field(None, description="Route string or airway list")
    departure_time: datetime = Field(..., description="Planned departure time (UTC)")
    cruise_altitude: Optional[str] = None
    aircraft_type: Optional[str] = None

class Briefing(BaseModel):
    user_id: str = Field(...)
    flight_plan_id: str = Field(...)
    summary: str = Field(..., description="AI 5-line summary")
    hazards: List[dict] = Field(default_factory=list)
    risk_level: str = Field("LOW", description="LOW/MEDIUM/HIGH")
    metar: dict = Field(default_factory=dict)
    taf: dict = Field(default_factory=dict)
    notams: List[dict] = Field(default_factory=list)
    pireps: List[dict] = Field(default_factory=list)
    alternates: List[dict] = Field(default_factory=list)
    overlays: dict = Field(default_factory=dict, description="GeoJSON overlays for map")
    created_at: Optional[datetime] = None
