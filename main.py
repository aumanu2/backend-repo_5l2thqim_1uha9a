import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from passlib.context import CryptContext
from jose import jwt, JWTError

from database import create_document, get_documents, db
from schemas import User, FlightPlan, Briefing

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="WeathAware API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class FlightPlanIn(BaseModel):
    callsign: Optional[str] = None
    origin: str = Field(..., min_length=3, max_length=4)
    destination: str = Field(..., min_length=3, max_length=4)
    alternates: list[str] = Field(default_factory=list)
    route: Optional[str] = None
    departure_time: datetime
    cruise_altitude: Optional[str] = None
    aircraft_type: Optional[str] = None


class BriefingRequest(BaseModel):
    flight_plan_id: str


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow().timestamp() + ACCESS_TOKEN_EXPIRE_MINUTES * 60})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str | None = None):
    # In a real app, use OAuth2PasswordBearer; simplified here
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        users = get_documents("user", {"email": email}, limit=1)
        if not users:
            raise HTTPException(status_code=401, detail="User not found")
        return users[0]
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/")
def root():
    return {"message": "WeathAware API running"}


@app.post("/auth/register", response_model=Token)
def register(req: RegisterRequest):
    existing = get_documents("user", {"email": req.email}, limit=1)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = pwd_context.hash(req.password)
    user = User(name=req.name, email=req.email, password_hash=hashed)
    create_document("user", user)
    token = create_access_token({"sub": req.email})
    return Token(access_token=token)


@app.post("/auth/login", response_model=Token)
def login(req: AuthRequest):
    users = get_documents("user", {"email": req.email}, limit=1)
    if not users:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = users[0]
    if not pwd_context.verify(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": req.email})
    return Token(access_token=token)


@app.post("/flightplan", response_model=dict)
def create_flight_plan(fp: FlightPlanIn, token: str):
    user = get_current_user(token)
    doc = FlightPlan(
        user_id=str(user.get("_id")),
        callsign=fp.callsign,
        origin=fp.origin.upper(),
        destination=fp.destination.upper(),
        alternates=[a.upper() for a in fp.alternates],
        route=fp.route,
        departure_time=fp.departure_time,
        cruise_altitude=fp.cruise_altitude,
        aircraft_type=fp.aircraft_type,
    )
    inserted_id = create_document("flightplan", doc)
    return {"id": inserted_id}


@app.get("/dashboard", response_model=dict)
def dashboard(token: str):
    user = get_current_user(token)
    plans = get_documents("flightplan", {"user_id": str(user.get("_id"))}, limit=20)
    return {"user": {"name": user.get("name"), "email": user.get("email")}, "recent_plans": plans}


@app.post("/brief", response_model=dict)
def generate_briefing(req: BriefingRequest, token: str):
    user = get_current_user(token)
    plans = get_documents("flightplan", {"_id": {"$eq": db["flightplan"]._ensure_objectid(req.flight_plan_id)}})
    plan = plans[0] if plans else None
    if not plan:
        raise HTTPException(status_code=404, detail="Flight plan not found")

    # Placeholder integrations: In production, call weather/NOTAM APIs here
    summary = (
        "Winds aloft moderate, isolated TS enroute, bases 3k ft, "
        "VFR marginal near destination after 21Z; fuel/alt review advised."
    )

    briefing = Briefing(
        user_id=str(user.get("_id")),
        flight_plan_id=req.flight_plan_id,
        summary=summary,
        hazards=[{"type": "TS", "severity": "MOD", "location": "enroute"}],
        risk_level="MEDIUM",
        metar={"origin": "METAR KJFK 121651Z ..."},
        taf={"destination": "TAF KLAX 121720Z ..."},
        notams=[{"id": "A1234", "text": "RWY 12/30 closed"}],
        pireps=[{"loc": "DCT", "wx": "MOD TURB FL180"}],
        alternates=[{"icao": "KBUR", "category": "Nearby"}],
        overlays={"route": {"type": "LineString", "coordinates": []}},
    )

    inserted_id = create_document("briefing", briefing)
    return {"id": inserted_id, "summary": briefing.summary, "risk": briefing.risk_level}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
