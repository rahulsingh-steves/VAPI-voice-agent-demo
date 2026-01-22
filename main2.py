import os
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
from dateutil import parser

# --- DATABASE ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True)
    user_phone = Column(String)
    user_name = Column(String)
    purpose = Column(Text)
    start_time = Column(TIMESTAMP)
    status = Column(String, default="scheduled")

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

# --- LOGIC FUNCTIONS ---

# def logic_create(phone, name, purpose, time_str):
#     db = SessionLocal()
#     try:
#         try: dt = parser.parse(time_str)
#         except: return "I couldn't understand that date."
#         conflict = db.query(Appointment).filter(Appointment.start_time == dt, Appointment.status == "scheduled").first()
#         if conflict: return "That time is already taken."
#         db.add(Appointment(user_phone=phone, user_name=name, purpose=purpose, start_time=dt))
#         db.commit()
#         return f"Booked! {name}, your meeting about {purpose} is set for {dt.strftime('%A at %I:%M %p')}."
#     finally: db.close()

def logic_cancel(phone):
    db = SessionLocal()
    appt = db.query(Appointment).filter(Appointment.user_phone == phone, Appointment.status == "scheduled").first()
    if not appt: return "I couldn't find any active meetings."
    appt.status = "cancelled"
    db.commit()
    db.close()
    return "Meeting cancelled successfully."

# --- NEW: RESCHEDULE LOGIC ---
# --- IN MAIN.PY ---

def logic_create(phone, name, purpose, time_str):
    db = SessionLocal()
    try:
        # Debug print to see what Vapi sends to Render logs
        print(f"DEBUG: Creating appointment. Date received: {time_str}")
        
        try:
            dt = parser.parse(time_str)
        except:
            return "I had trouble understanding that date. Could you please say the day and time again clearly?"
        
        conflict = db.query(Appointment).filter(Appointment.start_time == dt, Appointment.status == "scheduled").first()
        if conflict: 
            return "That time slot is already taken. Please choose another time."

        # Check if phone number was actually passed
        if not phone:
            return "I seem to have missed your phone number. Could you please repeat it?"

        new_appt = Appointment(user_phone=phone, user_name=name, purpose=purpose, start_time=dt)
        db.add(new_appt)
        db.commit()
        
        # Readable date format for the voice response
        readable_date = dt.strftime('%A, %B %d at %I:%M %p')
        return f"Done. I have booked your consultation for {readable_date}."
    except Exception as e:
        print(f"ERROR: {e}")
        return "I'm having a system issue saving that appointment."
    finally: 
        db.close()

def logic_reschedule(phone, new_time_str):
    db = SessionLocal()
    try:
        print(f"DEBUG: Rescheduling. New Date received: {new_time_str}")

        appt = db.query(Appointment).filter(Appointment.user_phone == phone, Appointment.status == "scheduled").first()
        if not appt: 
            return "I couldn't find an existing meeting for that phone number."

        try:
            dt = parser.parse(new_time_str)
        except:
            return "I couldn't understand the new time. Please say it again."

        conflict = db.query(Appointment).filter(Appointment.start_time == dt, Appointment.status == "scheduled").first()
        if conflict: 
            return "That new time slot is already taken."

        appt.start_time = dt
        db.commit()
        
        readable_date = dt.strftime('%A, %B %d at %I:%M %p')
        return f"Success. I have moved your meeting to {readable_date}."
    finally:
        db.close()
        
        
def logic_list(phone):
    db = SessionLocal()
    appts = db.query(Appointment).filter(Appointment.user_phone == phone, Appointment.status == "scheduled").all()
    db.close()
    if not appts: return "No upcoming meetings found."
    return "You have: " + ", ".join([f"{a.purpose} at {a.start_time.strftime('%I:%M %p')}" for a in appts])

# --- WEBHOOK HANDLER ---
@app.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    payload = await request.json()
    if payload.get("message", {}).get("type") == "tool-calls":
        tool = payload["message"]["toolCalls"][0]
        name = tool["function"]["name"]
        args = tool["function"]["arguments"]
        
        res = "Error processing request"
        
        if name == "createAppointment":
            res = logic_create(args.get("user_phone"), args.get("user_name"), args.get("purpose"), args.get("start_time"))
        elif name == "cancelAppointment":
            res = logic_cancel(args.get("user_phone"))
        elif name == "listAppointments":
            res = logic_list(args.get("user_phone"))
        # --- NEW: Handle Reschedule ---
        elif name == "rescheduleAppointment":
            res = logic_reschedule(args.get("user_phone"), args.get("new_time"))
            
        return {"results": [{"toolCallId": tool["id"], "result": res}]}
    return {"status": "ok"}