import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
from dateutil import parser
from dotenv import load_dotenv

# Import your validators
from validator import CreateRequest, CancelRequest, RescheduleRequest 

load_dotenv()

# --- DATABASE SETUP (SUPABASE) ---
DATABASE_URL = os.getenv("DATABASE_URL")

# Fix for Supabase/Render: SQLAlchemy requires 'postgresql://' not 'postgres://'
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# pool_pre_ping=True is important for Supabase to prevent connection timeouts
engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    pool_recycle=3600
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True)
    user_phone = Column(String)
    user_name = Column(String)
    purpose = Column(Text)
    start_time = Column(TIMESTAMP)
    status = Column(String, default="scheduled")
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

# This creates the table in your Supabase project automatically
Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- LOGIC FUNCTIONS (Return strings for Vapi) ---

def logic_create(user_phone, user_name, purpose, start_time_str):
    db = SessionLocal()
    try:
        time_obj = parser.parse(start_time_str)
        conflict = db.query(Appointment).filter(
            Appointment.start_time == time_obj,
            Appointment.status == "scheduled"
        ).first()

        if conflict:
            return "I'm sorry, that time is already booked. Please choose another time."

        appt = Appointment(user_phone=user_phone, user_name=user_name, purpose=purpose, start_time=time_obj)
        db.add(appt)
        db.commit()
        return f"Meeting booked! {user_name}, I've scheduled your {purpose} for {time_obj.strftime('%A at %I:%M %p')}."
    except Exception as e:
        return f"I had trouble saving that. Could you repeat the date and time?"
    finally:
        db.close()

def logic_cancel(user_phone):
    db = SessionLocal()
    try:
        appt = db.query(Appointment).filter(Appointment.user_phone == user_phone, Appointment.status == "scheduled").first()
        if not appt: return "I couldn't find any active meetings to cancel for this number."
        appt.status = "cancelled"
        db.commit()
        return "Your meeting has been cancelled successfully."
    finally:
        db.close()

def logic_list(user_phone):
    db = SessionLocal()
    try:
        appts = db.query(Appointment).filter(Appointment.user_phone == user_phone, Appointment.status == "scheduled").all()
        if not appts: return "You have no upcoming meetings."
        details = ", ".join([f"{a.purpose} on {a.start_time.strftime('%A at %I:%M %p')}" for a in appts])
        return f"You have the following meetings scheduled: {details}."
    finally:
        db.close()

# --- WEBHOOK FOR VAPI ---

@app.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    payload = await request.json()
    if payload.get("message", {}).get("type") == "tool-calls":
        tool_call = payload["message"]["toolCalls"][0]
        name = tool_call["function"]["name"]
        args = tool_call["function"]["arguments"]
        
        res = "Function error"
        if name == "createAppointment":
            res = logic_create(args.get("user_phone"), args.get("user_name"), args.get("purpose"), args.get("start_time"))
        elif name == "cancelAppointment":
            res = logic_cancel(args.get("user_phone"))
        elif name == "listAppointments":
            res = logic_list(args.get("user_phone"))
            
        return {"results": [{"toolCallId": tool_call["id"], "result": res}]}
    return {"status": "ok"}