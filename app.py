from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from datetime import datetime, timedelta
import uuid

app = Flask(__name__)
CORS(app)

# -------------------------
# Mock in-memory data stores
# -------------------------
students = {
    "S1001": {"name": "Alice", "phone": "+111111", "email": "alice@example.edu", "holds": [], "program": "BScCS"},
    "S1002": {"name": "Bob", "phone": "+222222", "email": "bob@example.edu", "holds": ["finance"], "program": "BA"},
}

fees = {
    "S1001": {"dueAmount": 150.00, "lastPaymentDate": "2025-02-01", "receipts": ["https://example.edu/receipt/1001/1"]},
    # S1002 intentionally missing to test 'no record' path
}

courses = {
    "CS101": {"seats_total": 2, "seats_filled": 1, "prereqs": []},
    "CS201": {"seats_total": 1, "seats_filled": 1, "prereqs": ["CS101"]},
}

enrollments = {}   # key: studentId -> [courseCodes]
waitlists = {}     # key: courseCode -> [studentId]

exams = {
    "S1001": [
        {"course": "CS101", "date": "2025-06-01", "time": "10:00", "venue": "Hall A"},
        {"course": "MATH101", "date": "2025-06-03", "time": "14:00", "venue": "Hall B"},
    ]
}

hostel_rooms = [
    {"block": "A", "room": "A101", "available": True},
    {"block": "A", "room": "A102", "available": False},
    {"block": "B", "room": "B201", "available": True},
]

tickets = []   # generic ticket store
events = {
    "EVT100": {"name": "Tech Fest", "capacity": 2, "participants": [] , "waitlist": []},
    "EVT101": {"name": "Art Expo", "capacity": 1, "participants": [] , "waitlist": []},
}

leaves = []
audit_logs = []

# Path to uploaded flow image (from session)
FLOW_IMAGE_PATH = "/mnt/data/fe233be5-ad0b-4a79-8498-22629ef3317f.png"

# -------------------------
# Utility helpers
# -------------------------
def log_audit(action, payload):
    entry = {"id": str(uuid.uuid4()), "action": action, "payload": payload, "ts": datetime.utcnow().isoformat()}
    audit_logs.append(entry)

def make_ticket(studentId, category, subcategory, details, priority="normal"):
    ticket = {
        "ticket_id": str(uuid.uuid4()),
        "studentId": studentId,
        "category": category,
        "subcategory": subcategory,
        "details": details,
        "priority": priority,
        "createdAt": datetime.utcnow().isoformat(),
        "status": "open"
    }
    tickets.append(ticket)
    log_audit("create_ticket", ticket)
    return ticket

# -------------------------
# Endpoints
# -------------------------

@app.route("/")
def index():
    return jsonify({"message": "University Helpdesk API - running", "version": "1.0"})

# ---------- Fees ----------
@app.route("/fees/<studentId>", methods=["GET"])
def get_fees(studentId):
    log_audit("get_fees", {"studentId": studentId})
    rec = fees.get(studentId)
    if rec:
        return jsonify({"found": True, "studentId": studentId, **rec})
    else:
        return jsonify({"found": False, "studentId": studentId}), 404

@app.route("/payments/request", methods=["POST"])
def request_payment():
    data = request.json or {}
    studentId = data.get("studentId")
    amount = data.get("amount")
    if not studentId or amount is None:
        return jsonify({"error": "studentId and amount required"}), 400

    # Mock payment URL
    paymentId = str(uuid.uuid4())
    payment_url = f"https://payments.example.edu/pay/{paymentId}"
    log_audit("request_payment", {"studentId": studentId, "amount": amount, "paymentId": paymentId})
    return jsonify({"paymentUrl": payment_url, "paymentId": paymentId})

# If fee record not found -> create ticket
@app.route("/tickets/finance", methods=["POST"])
def create_finance_ticket():
    data = request.json or {}
    studentId = data.get("studentId")
    details = data.get("details", "")
    ticket = make_ticket(studentId, "finance", "fee_query", details)
    return jsonify({"ticket": ticket, "message": "Ticket created for finance team."}), 201

# ---------- Enrollment ----------
@app.route("/courses/<courseCode>/availability", methods=["GET"])
def course_availability(courseCode):
    c = courses.get(courseCode)
    if not c:
        return jsonify({"exists": False}), 404
    seats_available = max(0, c["seats_total"] - c["seats_filled"])
    return jsonify({"exists": True, "courseCode": courseCode, "seatsAvailable": seats_available})

@app.route("/enrollment", methods=["POST"])
def enroll_student():
    data = request.json or {}
    studentId = data.get("studentId")
    courseCode = data.get("courseCode")
    if not studentId or not courseCode:
        return jsonify({"error": "studentId and courseCode required"}), 400

    student = students.get(studentId)
    course = courses.get(courseCode)
    log_audit("enroll_request", {"studentId": studentId, "courseCode": courseCode})

    # Basic validations
    if not student:
        return jsonify({"error": "student not found"}), 404
    # check holds/prereqs
    if student.get("holds"):
        return jsonify({"eligible": False, "reason": "student has holds: " + ",".join(student.get("holds"))}), 403

    prereqs = course.get("prereqs", []) if course else []
    # NOTE: in this mock we won't enforce prereq completion; assume passed earlier
    seats = course["seats_total"] - course["seats_filled"]
    if seats <= 0:
        # add to waitlist
        waitlists.setdefault(courseCode, []).append(studentId)
        pos = len(waitlists[courseCode])
        log_audit("waitlist_add", {"studentId": studentId, "courseCode": courseCode, "position": pos})
        return jsonify({"enrolled": False, "waitlist": True, "position": pos, "message": "Added to waitlist"}), 200

    # Enroll
    course["seats_filled"] += 1
    enrollments.setdefault(studentId, []).append(courseCode)
    log_audit("enrolled", {"studentId": studentId, "courseCode": courseCode})
    # Notify (mock)
    return jsonify({"enrolled": True, "courseCode": courseCode, "message": "Enrollment successful"}), 200

@app.route("/enrollment/override", methods=["POST"])
def override_request():
    data = request.json or {}
    studentId = data.get("studentId")
    courseCode = data.get("courseCode")
    reason = data.get("reason", "")
    ticket = make_ticket(studentId, "academics", "override_request", {"courseCode": courseCode, "reason": reason})
    return jsonify({"message": "Override request submitted", "ticket": ticket}), 201

# ---------- Exams ----------
@app.route("/exams/timetable", methods=["GET"])
def get_timetable():
    studentId = request.args.get("studentId")
    sem = request.args.get("semester")
    log_audit("get_timetable", {"studentId": studentId, "semester": sem})
    if not studentId:
        return jsonify({"error": "studentId required"}), 400
    t = exams.get(studentId, [])
    return jsonify({"studentId": studentId, "timetable": t})

@app.route("/exams/special", methods=["POST"])
def exams_special_request():
    data = request.json or {}
    studentId = data.get("studentId")
    reason = data.get("reason")
    attachments = data.get("attachments", [])
    ticket = make_ticket(studentId, "exams", "special_arrangement", {"reason": reason, "attachments": attachments})
    return jsonify({"message": "Special arrangement request submitted", "ticket": ticket}), 201

# ---------- Hostel ----------
@app.route("/hostel/availability", methods=["GET"])
def hostel_availability():
    block = request.args.get("block")
    log_audit("hostel_availability", {"block": block})
    if block:
        avail = [r for r in hostel_rooms if r["block"] == block and r["available"]]
    else:
        avail = [r for r in hostel_rooms if r["available"]]
    return jsonify({"availableRooms": avail})

@app.route("/hostel/book", methods=["POST"])
def hostel_book():
    data = request.json or {}
    studentId = data.get("studentId")
    room = data.get("room")
    # find room
    for r in hostel_rooms:
        if r["room"] == room:
            if not r["available"]:
                return jsonify({"error": "room not available"}), 400
            r["available"] = False
            booking = {"bookingId": str(uuid.uuid4()), "studentId": studentId, "room": room, "bookedAt": datetime.utcnow().isoformat()}
            log_audit("hostel_book", booking)
            return jsonify({"message": "Room booked", "booking": booking})
    return jsonify({"error": "room not found"}), 404

@app.route("/hostel/maintenance", methods=["POST"])
def hostel_maintenance():
    data = request.json or {}
    studentId = data.get("studentId")
    room = data.get("room")
    issue = data.get("issue")
    attachments = data.get("attachments", [])
    ticket = make_ticket(studentId, "hostel", "maintenance", {"room": room, "issue": issue, "attachments": attachments})
    return jsonify({"message": "Maintenance ticket created", "ticket": ticket}), 201

@app.route("/hostel/mess-complaint", methods=["POST"])
def mess_complaint():
    data = request.json or {}
    studentId = data.get("studentId")
    date = data.get("date")
    description = data.get("description")
    ticket = make_ticket(studentId, "hostel", "mess_complaint", {"date": date, "description": description})
    return jsonify({"message": "Mess complaint logged", "ticket": ticket}), 201

# ---------- Leave ----------
@app.route("/leave", methods=["POST"])
def submit_leave():
    data = request.json or {}
    studentId = data.get("studentId")
    from_date = data.get("fromDate")
    to_date = data.get("toDate")
    leave_type = data.get("leaveType")
    reason = data.get("reason", "")
    supporting = data.get("supporting", [])

    # Basic policy: auto-approve if <=2 days and not special type
    try:
        dfrom = datetime.fromisoformat(from_date)
        dto = datetime.fromisoformat(to_date)
        days = (dto - dfrom).days + 1
    except Exception:
        days = 0

    record = {"leaveId": str(uuid.uuid4()), "studentId": studentId, "from": from_date, "to": to_date, "type": leave_type, "reason": reason, "status": "pending", "submittedAt": datetime.utcnow().isoformat()}
    if days <= 2 and leave_type.lower() not in ("maternity", "medical"):
        record["status"] = "approved"
        message = "Auto-approved"
    else:
        # create ticket for approver
        make_ticket(studentId, "academics", "leave_approval", {"leave": record})
        message = "Submitted for approval"

    leaves.append(record)
    log_audit("leave_submitted", record)
    return jsonify({"leave": record, "message": message}), 201

# ---------- Events ----------
@app.route("/events/<eventId>/register", methods=["POST"])
def register_event(eventId):
    data = request.json or {}
    studentId = data.get("studentId")
    role = data.get("role", "participant")
    event = events.get(eventId)
    if not event:
        return jsonify({"error": "event not found"}), 404

    # check capacity
    cap = event["capacity"]
    if len(event["participants"]) < cap:
        event["participants"].append({"studentId": studentId, "role": role, "registeredAt": datetime.utcnow().isoformat()})
        log_audit("event_register", {"eventId": eventId, "studentId": studentId})
        # generate simple ticket/qr placeholder
        confirmation = {"eventId": eventId, "studentId": studentId, "ticketQRCode": f"QR-{str(uuid.uuid4())[:8]}"}
        return jsonify({"registered": True, "confirmation": confirmation}), 200
    else:
        event["waitlist"].append(studentId)
        pos = len(event["waitlist"])
        log_audit("event_waitlist_add", {"eventId": eventId, "studentId": studentId, "position": pos})
        return jsonify({"registered": False, "waitlistPosition": pos, "message": "Event full, added to waitlist"}), 200

# ---------- Identity verification (OTP simulation) ----------
otp_store = {}
@app.route("/verify_identity", methods=["POST"])
def verify_identity():
    data = request.json or {}
    studentId = data.get("studentId")
    method = data.get("method", "otp")  # otp or sso
    if method == "sso":
        # Simulate SSO success
        log_audit("verify_sso", {"studentId": studentId})
        return jsonify({"verified": True, "method": "sso"}), 200

    # OTP flow - generate
    code = str(uuid.uuid4())[:6].upper()
    otp_store[studentId] = {"code": code, "expires": (datetime.utcnow() + timedelta(minutes=5)).isoformat()}
    # In real life: send SMS or email. Here we return the code so you can test in Postman.
    log_audit("otp_generated", {"studentId": studentId, "otp": code})
    return jsonify({"sent": True, "otp": code, "note": "OTP returned in response for testing only"}), 200

@app.route("/verify_identity/confirm", methods=["POST"])
def verify_identity_confirm():
    data = request.json or {}
    studentId = data.get("studentId")
    code = data.get("code")
    rec = otp_store.get(studentId)
    if not rec:
        return jsonify({"verified": False, "reason": "no otp generated"}), 400
    if rec["code"] == code:
        log_audit("otp_verified", {"studentId": studentId})
        return jsonify({"verified": True}), 200
    return jsonify({"verified": False, "reason": "invalid code"}), 400

# ---------- Tickets & audit ----------
@app.route("/tickets", methods=["GET"])
def list_tickets():
    return jsonify({"tickets": tickets})

@app.route("/audit/logs", methods=["GET"])
def get_audit_logs():
    return jsonify({"logs": audit_logs})

# ---------- Serve uploaded flow image ----------
@app.route("/assets/flow_image", methods=["GET"])
def serve_flow_image():
    try:
        return send_file(FLOW_IMAGE_PATH, mimetype='image/png')
    except Exception as e:
        return jsonify({"error": "could not find image", "path": FLOW_IMAGE_PATH, "exception": str(e)}), 404

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
