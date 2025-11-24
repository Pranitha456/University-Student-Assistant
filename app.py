"""
University Student Helpdesk - Single-file Flask Mock API

Features implemented (mock/in-memory with optional JSON persistence):
- Fees lookup and payment link generation
- Course enrollment and waitlist
- Exam timetable and special arrangements
- Hostel availability, booking and maintenance tickets
- Leave applications with auto-approve rules
- Event registration and waitlist
- Identity verification (OTP simulation)
- Simple audit logging & ticketing

Run:
    pip install flask flask_cors
    python university_helpdesk_api.py

The app stores runtime state in `data_store.json` for convenience (ignored by git by default).
"""

from flask import Flask, jsonify, request, abort
from flask_cors import CORS
import uuid
import datetime
import json
import threading
import os

APP = Flask(__name__)
CORS(APP)

DATA_FILE = "data_store.json"
LOCK = threading.Lock()

# ---------------- Utilities ----------------
def now_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    # defaults
    return {
        "students": {},
        "courses": {},
        "enrollments": {},
        "waitlists": {},
        "fees": {},
        "payments": {},
        "exam_timetables": {},
        "exam_special_requests": {},
        "hostels": {},
        "hostel_bookings": {},
        "maintenance_tickets": {},
        "leave_requests": {},
        "events": {},
        "event_registrations": {},
        "event_waitlists": {},
        "otps": {},
        "audit_logs": []
    }

def save_data(data):
    with LOCK:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)

def audit(user, action, details=None):
    entry = {
        "id": str(uuid.uuid4()),
        "time": now_iso(),
        "user": user,
        "action": action,
        "details": details or {}
    }
    DATA["audit_logs"].append(entry)
    save_data(DATA)

# ---------------- Initialize data ----------------
DATA = load_data()

# seed some data if empty
if not DATA["students"]:
    DATA["students"] = {
        "s001": {"id": "s001", "name": "Alice Example", "email": "alice@example.edu"},
        "s002": {"id": "s002", "name": "Bob Example", "email": "bob@example.edu"}
    }

if not DATA["courses"]:
    DATA["courses"] = {
        "CSE101": {"code": "CSE101", "title": "Intro to Computer Science", "capacity": 2},
        "MTH101": {"code": "MTH101", "title": "Calculus I", "capacity": 1}
    }

if not DATA["fees"]:
    DATA["fees"] = {
        "s001": {"balance": 1500.0, "items": [{"desc": "Tuition", "amount": 1500.0}]},
        "s002": {"balance": 0.0, "items": []}
    }

if not DATA["exam_timetables"]:
    DATA["exam_timetables"] = {
        "CSE101": [{"date": "2026-01-15", "time": "09:00", "venue": "Hall A"}],
        "MTH101": [{"date": "2026-01-17", "time": "13:00", "venue": "Hall B"}]
    }

if not DATA["hostels"]:
    DATA["hostels"] = {
        "H1": {"name": "Maple Hostel", "rooms_total": 4, "rooms_available": 2},
        "H2": {"name": "Pine Hostel", "rooms_total": 3, "rooms_available": 3}
    }

if not DATA["events"]:
    DATA["events"] = {
        "EVT100": {"id": "EVT100", "title": "Freshers Meet", "capacity": 2}
    }

save_data(DATA)

# ---------------- Fees endpoints ----------------
@APP.route("/fees/<student_id>", methods=["GET"])
def get_fees(student_id):
    fees = DATA["fees"].get(student_id, {"balance": 0.0, "items": []})
    audit(student_id, "check_fees")
    return jsonify({"student_id": student_id, **fees})

@APP.route("/fees/pay/<student_id>", methods=["POST"])
def create_payment(student_id):
    body = request.json or {}
    amount = body.get("amount")
    if amount is None:
        abort(400, "amount required")
    token = str(uuid.uuid4())
    payment = {
        "id": token,
        "student_id": student_id,
        "amount": float(amount),
        "created": now_iso(),
        "status": "pending",
        "expires_at": (datetime.datetime.utcnow() + datetime.timedelta(hours=1)).replace(microsecond=0).isoformat() + "Z"
    }
    DATA["payments"][token] = payment
    save_data(DATA)
    audit(student_id, "generate_payment", {"payment_id": token, "amount": amount})
    # mock payment link
    link = f"https://payments.example/university/pay/{token}"
    return jsonify({"payment_id": token, "payment_link": link, "expires_at": payment["expires_at"]})

@APP.route("/fees/pay/callback/<payment_id>", methods=["POST"])
def payment_callback(payment_id):
    payment = DATA["payments"].get(payment_id)
    if not payment:
        abort(404)
    payment["status"] = "completed"
    payment["completed_at"] = now_iso()
    sid = payment["student_id"]
    if sid in DATA["fees"]:
        DATA["fees"][sid]["balance"] = max(0.0, DATA["fees"][sid]["balance"] - payment["amount"])
        DATA["fees"][sid]["items"].append({"desc": "Online payment", "amount": -payment["amount"]})
    save_data(DATA)
    audit(sid, "payment_completed", {"payment_id": payment_id})
    return jsonify({"ok": True, "payment_id": payment_id})

# ---------------- Enrollment & waitlist ----------------
@APP.route("/enroll", methods=["POST"])
def enroll():
    body = request.json or {}
    student_id = body.get("student_id")
    course_code = body.get("course_code")
    if not student_id or not course_code:
        abort(400, "student_id and course_code required")
    course = DATA["courses"].get(course_code)
    if not course:
        abort(404, "course not found")

    enrollments = DATA.setdefault("enrollments", {}).setdefault(course_code, [])
    waitlist = DATA.setdefault("waitlists", {}).setdefault(course_code, [])

    if student_id in enrollments:
        return jsonify({"status": "already_enrolled", "course": course_code})
    if len(enrollments) < course.get("capacity", 0):
        enrollments.append(student_id)
        save_data(DATA)
        audit(student_id, "enrolled", {"course": course_code})
        return jsonify({"status": "enrolled", "course": course_code})
    else:
        if any(w.get("student_id") == student_id for w in waitlist):
            return jsonify({"status": "already_waitlisted", "course": course_code})
        waitlist.append({"student_id": student_id, "requested_at": now_iso()})
        save_data(DATA)
        audit(student_id, "waitlisted", {"course": course_code})
        return jsonify({"status": "waitlisted", "course": course_code})

@APP.route("/enroll/status/<course_code>", methods=["GET"])
def enroll_status(course_code):
    enrollments = DATA.get("enrollments", {}).get(course_code, [])
    waitlist = DATA.get("waitlists", {}).get(course_code, [])
    return jsonify({"course": course_code, "enrolled": enrollments, "waitlist": waitlist})

# ---------------- Exam timetable & special arrangements ----------------
@APP.route("/exam/timetable/<student_id>", methods=["GET"])
def exam_timetable(student_id):
    # return timetable for courses the student is enrolled in
    student_courses = [c for c, studs in DATA.get("enrollments", {}).items() if student_id in studs]
    timetable = {c: DATA.get("exam_timetables", {}).get(c, []) for c in student_courses}
    audit(student_id, "view_exam_timetable")
    return jsonify({"student_id": student_id, "timetable": timetable})

@APP.route("/exam/special", methods=["POST"])
def request_special_exam():
    body = request.json or {}
    sid = body.get("student_id")
    course = body.get("course_code")
    reason = body.get("reason", "")
    if not sid or not course:
        abort(400, "student_id and course_code required")
    ticket_id = str(uuid.uuid4())
    ticket = {
        "id": ticket_id,
        "student_id": sid,
        "course": course,
        "reason": reason,
        "status": "submitted",
        "created": now_iso()
    }
    DATA.setdefault("exam_special_requests", {})[ticket_id] = ticket
    save_data(DATA)
    audit(sid, "special_exam_request", {"ticket_id": ticket_id})
    return jsonify({"ticket_id": ticket_id, "status": "submitted"})

# ---------------- Hostel booking & maintenance ----------------
@APP.route("/hostel/availability", methods=["GET"])
def hostel_availability():
    return jsonify(DATA.get("hostels", {}))

@APP.route("/hostel/book", methods=["POST"])
def hostel_book():
    body = request.json or {}
    sid = body.get("student_id")
    hostel_id = body.get("hostel_id")
    if not sid or not hostel_id:
        abort(400, "student_id and hostel_id required")
    hostel = DATA.get("hostels", {}).get(hostel_id)
    if not hostel:
        abort(404, "hostel not found")
    if hostel.get("rooms_available", 0) <= 0:
        return jsonify({"status": "full"})
    booking_id = str(uuid.uuid4())
    DATA.setdefault("hostel_bookings", {})[booking_id] = {
        "id": booking_id, "student_id": sid, "hostel_id": hostel_id, "created": now_iso()
    }
    hostel["rooms_available"] = max(0, hostel.get("rooms_available", 1) - 1)
    save_data(DATA)
    audit(sid, "hostel_booked", {"booking_id": booking_id, "hostel_id": hostel_id})
    return jsonify({"status": "booked", "booking_id": booking_id})

@APP.route("/hostel/maintenance", methods=["POST"])
def hostel_maintenance():
    body = request.json or {}
    sid = body.get("student_id")
    hostel_id = body.get("hostel_id")
    desc = body.get("description", "")
    if not sid or not hostel_id:
        abort(400, "student_id and hostel_id required")
    ticket_id = str(uuid.uuid4())
    DATA.setdefault("maintenance_tickets", {})[ticket_id] = {
        "id": ticket_id, "student_id": sid, "hostel_id": hostel_id, "description": desc,
        "status": "open", "created": now_iso()
    }
    save_data(DATA)
    audit(sid, "maintenance_ticket", {"ticket_id": ticket_id})
    return jsonify({"ticket_id": ticket_id, "status": "open"})

# ---------------- Leave applications with auto-approve ----------------
@APP.route("/leave/apply", methods=["POST"])
def leave_apply():
    body = request.json or {}
    sid = body.get("student_id")
    start = body.get("start_date")
    end = body.get("end_date")
    reason = body.get("reason", "")
    if not sid or not start or not end:
        abort(400, "student_id, start_date and end_date required")
    try:
        sdate = datetime.datetime.fromisoformat(start)
        edate = datetime.datetime.fromisoformat(end)
    except Exception:
        abort(400, "dates must be ISO format YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
    duration_days = (edate - sdate).days + 1
    # simple auto-approve rule: <=3 days and reason provided
    status = "approved" if (duration_days <= 3 and reason) else "pending"
    lr_id = str(uuid.uuid4())
    DATA.setdefault("leave_requests", {})[lr_id] = {
        "id": lr_id, "student_id": sid, "start": start, "end": end,
        "reason": reason, "status": status, "created": now_iso()
    }
    save_data(DATA)
    audit(sid, "leave_applied", {"leave_id": lr_id, "status": status})
    return jsonify({"leave_id": lr_id, "status": status, "duration_days": duration_days})

# ---------------- Events registration & waitlist ----------------
@APP.route("/events/register", methods=["POST"])
def event_register():
    body = request.json or {}
    sid = body.get("student_id")
    event_id = body.get("event_id")
    if not sid or not event_id:
        abort(400, "student_id and event_id required")
    event = DATA.get("events", {}).get(event_id)
    if not event:
        abort(404, "event not found")
    regs = DATA.setdefault("event_registrations", {}).setdefault(event_id, [])
    if sid in regs:
        return jsonify({"status": "already_registered"})
    if len(regs) < event.get("capacity", 0):
        regs.append(sid)
        save_data(DATA)
        audit(sid, "event_registered", {"event_id": event_id})
        return jsonify({"status": "registered"})
    else:
        wl = DATA.setdefault("event_waitlists", {}).setdefault(event_id, [])
        wl.append({"student_id": sid, "requested_at": now_iso()})
        save_data(DATA)
        audit(sid, "event_waitlisted", {"event_id": event_id})
        return jsonify({"status": "waitlisted"})

# ---------------- OTP identity verification ----------------
@APP.route("/verify/otp/request", methods=["POST"])
def request_otp():
    body = request.json or {}
    sid = body.get("student_id")
    if not sid:
        abort(400, "student_id required")
    code = str(uuid.uuid4())[:6]
    exp = (datetime.datetime.utcnow() + datetime.timedelta(minutes=5)).replace(microsecond=0).isoformat() + "Z"
    DATA.setdefault("otps", {})[sid] = {"code": code, "expires_at": exp}
    save_data(DATA)
    audit(sid, "otp_requested")
    # for testing we return the code (in production you'd send via SMS/email)
    return jsonify({"student_id": sid, "otp": code, "expires_at": exp})

@APP.route("/verify/otp/confirm", methods=["POST"])
def confirm_otp():
    body = request.json or {}
    sid = body.get("student_id")
    code = body.get("otp")
    if not sid or not code:
        abort(400, "student_id and otp required")
    rec = DATA.get("otps", {}).get(sid)
    if not rec:
        return jsonify({"verified": False, "reason": "no_otp_requested"}), 400
    # compare code and expiration
    if rec.get("code") != code:
        return jsonify({"verified": False, "reason": "invalid_code"}), 400
    if datetime.datetime.fromisoformat(rec["expires_at"].replace("Z", "")) < datetime.datetime.utcnow():
        return jsonify({"verified": False, "reason": "expired"}), 400
    DATA["otps"].pop(sid, None)
    save_data(DATA)
    audit(sid, "otp_verified")
    return jsonify({"verified": True})

# ---------------- Audit logs & helpers ----------------
@APP.route("/audit/logs", methods=["GET"])
def get_audit_logs():
    since = request.args.get("since")
    logs = DATA.get("audit_logs", [])
    if since:
        try:
            sdt = datetime.datetime.fromisoformat(since.replace("Z", ""))
            logs = [l for l in logs if datetime.datetime.fromisoformat(l["time"].replace("Z", "")) >= sdt]
        except Exception:
            pass
    return jsonify({"count": len(logs), "logs": logs})

@APP.route("/students/<student_id>", methods=["GET"])
def get_student(student_id):
    s = DATA.get("students", {}).get(student_id)
    if not s:
        abort(404)
    return jsonify(s)

@APP.route("/courses", methods=["GET"])
def list_courses():
    return jsonify(list(DATA.get("courses", {}).values()))

@APP.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": now_iso()})

# admin testing - reload from disk (dev only)
@APP.route("/admin/reset", methods=["POST"])
def admin_reset():
    global DATA
    DATA = load_data()
    audit("admin", "reset")
    return jsonify({"ok": True})

if __name__ == "__main__":
    # Allow port override via env var
    port = int(os.environ.get("PORT", 5000))
    APP.run(host="0.0.0.0", port=port, debug=True)
