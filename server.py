# server.py
import eventlet
eventlet.monkey_patch()

from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__, static_folder='static')
socketio = SocketIO(app, cors_allowed_origins="*")

# Ephemeral state for exactly one sender/receiver session
STATE = {
    "sender_id": None,
    "receiver_id": None,
    "offer": None,
    "offer_candidates": [],
    "answer": None,
    "answer_candidates": []
}

ROOM_ID = "my_room"

@app.route("/")
def index():
    return send_from_directory('static', 'index.html')

@socketio.on("join")
def on_join(data):
    """
    role = "sender" or "receiver"
    If a sender joins (even re-joins), we reset ephemeral state.
    """
    global STATE
    role = data.get("role")
    join_room(ROOM_ID)
    print(f"Client {request.sid} joined as {role}.")

    if role == "sender":
        # Reset ephemeral state for a fresh session
        # but keep the receiver_id if a receiver is already in the room
        old_receiver = STATE["receiver_id"]
        STATE = {
            "sender_id": request.sid,
            "receiver_id": old_receiver,
            "offer": None,
            "offer_candidates": [],
            "answer": None,
            "answer_candidates": []
        }
        print(">>> Reset ephemeral state because a new/returning Sender joined.")

    elif role == "receiver":
        STATE["receiver_id"] = request.sid
        # If there's an existing offer from the current sender, send it immediately
        if STATE["offer"]:
            print("Sending stored offer to newly joined receiver.")
            emit("offer", {"sdp": STATE["offer"]}, room=request.sid)
        # Send any stored ICE candidates from the sender
        for c in STATE["offer_candidates"]:
            emit("candidate", {"candidate": c}, room=request.sid)

    emit("joined_room", {"room": ROOM_ID, "role": role}, room=request.sid)

@socketio.on("offer")
def on_offer(data):
    global STATE
    STATE["offer"] = data["sdp"]
    print("Storing new offer from Sender.")
    if STATE["receiver_id"]:
        print("Forwarding offer to receiver...")
        emit("offer", data, room=STATE["receiver_id"])

@socketio.on("answer")
def on_answer(data):
    global STATE
    STATE["answer"] = data["sdp"]
    print("Storing new answer from Receiver.")
    if STATE["sender_id"]:
        emit("answer", data, room=STATE["sender_id"])

@socketio.on("candidate")
def on_candidate(data):
    global STATE
    candidate = data["candidate"]
    print(f"Got ICE candidate from {request.sid}.")

    if request.sid == STATE.get("sender_id"):
        # It's from the sender
        STATE["offer_candidates"].append(candidate)
        if STATE["receiver_id"]:
            emit("candidate", data, room=STATE["receiver_id"])
    else:
        # It's from the receiver
        STATE["answer_candidates"].append(candidate)
        if STATE["sender_id"]:
            emit("candidate", data, room=STATE["sender_id"])

@socketio.on("disconnect")
def on_disconnect():
    global STATE
    sid = request.sid
    print(f"Client {sid} disconnected.")

    if sid == STATE.get("sender_id"):
        # Clear ephemeral state except for the receiver_id
        print(">>> Sender disconnected. Clearing ephemeral offer/answer/candidates.")
        STATE["sender_id"] = None
        STATE["offer"] = None
        STATE["offer_candidates"] = []
        STATE["answer"] = None
        STATE["answer_candidates"] = []
    elif sid == STATE.get("receiver_id"):
        print(">>> Receiver disconnected. Removing receiver_id.")
        STATE["receiver_id"] = None

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
