#!/usr/bin/env python3

"""
MagiClaw Flask Web Dashboard

This script sets up a Flask web dashboard with SocketIO to monitor the MagiClaw.
It allows starting and stopping the MagiClaw process, and it uses ZeroMQ to receive real-time updates from the MagiClaw.
It also serves a static HTML page for the user interface.

Usage:

Run this script with:

```
python app.py
```

It will start a web dashboard on port 8000.
"""

import eventlet
eventlet.monkey_patch()

import os
import signal
import subprocess
import threading
import base64
import zmq
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from modules import magiclaw_msg_pb2

# Flask app setup
app = Flask(__name__, static_folder='static', static_url_path='')

# SocketIO setup
socketio = SocketIO(app, cors_allowed_origins="*")

# Authentication token
AUTH_TOKEN = "magiclaw"

# Global variables for process management
magiclaw_process = {}
zmq_thread = {}
stop_zmq_flag = {}

# Function to read and process output from the subprocess
def read_process_output(proc, claw_id):
    """
    Reads the output from the subprocess and emits it via SocketIO, 
    namespaced or tagged by claw_id.

    Args:
        proc (subprocess.Popen): The subprocess to read output from.
        claw_id (int): The ID of the claw associated with this subprocess.
    """
    try:
        for line in iter(proc.stdout.readline, ''):
            if line:
                line = line.rstrip()
                log_line = f"[id {claw_id}] {line}"
                print("[run-magiclaw]", log_line)
                socketio.emit('log', {"id": claw_id, "line": line})
        proc.stdout.close()
    except Exception as e:
        print(f"[read error][id {claw_id}]", e)


# ZMQ subscriber function to listen for messages from the MagiClaw
def zmq_subscriber(claw_id=0):
    """
    Subscribes to the ZMQ socket and emits messages via SocketIO.
    
    This function runs in a separate thread to avoid blocking the main thread.
    It listens for messages from the MagiClaw and emits them to connected clients.
    """
    
    context = zmq.Context()
    sub = context.socket(zmq.SUB)
    sub.setsockopt(zmq.CONFLATE, 1)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")
    if claw_id == 0:
        sub.connect("tcp://localhost:6300")
    else:
        sub.connect("tcp://localhost:6400")

    while not stop_zmq_flag[claw_id].is_set():
        try:
            # Receive a message
            data = sub.recv(flags=zmq.NOBLOCK)
            
            # Parse the message
            msg = magiclaw_msg_pb2.MagiClaw()
            msg.ParseFromString(data)

            # Create data to emit
            data_to_emit = {
                "id": claw_id,
                "motor_angle": msg.claw.motor.angle,
                "motor_speed": msg.claw.motor.speed,
                "motor_iq": msg.claw.motor.iq,
                "motor_temp": msg.claw.motor.temperature,
                "claw_angle": msg.claw.angle,
                "finger_0_pose": list(msg.finger_0.pose),
                "finger_0_force": list(msg.finger_0.force),
                "finger_1_pose": list(msg.finger_1.pose),
                "finger_1_force": list(msg.finger_1.force),
                "magiclaw_pose": list(msg.pose),
                "finger_0_img": "data:image/jpeg;base64," + base64.b64encode(msg.finger_0.img).decode("utf-8"),
                "finger_1_img": "data:image/jpeg;base64," + base64.b64encode(msg.finger_1.img).decode("utf-8"),
            }

            socketio.emit("status_update", data_to_emit)

        except zmq.Again:
            eventlet.sleep(0.05)  # non-blocking
        except Exception as e:
            print("ZMQ error:", e)
            eventlet.sleep(0.5)

# Flask route to serve the main page
@app.route('/')
def index():
    """
    Serve the main HTML page.
    
    This route serves the index.html file from the static folder.
    """
    
    return app.send_static_file('index.html')

# Flask route to serve the static files
@app.route('/exec', methods=['POST'])
def exec_cmd():
    """
    Execute commands to control the MagiClaw process.
    
    This route handles commands to start or stop the MagiClaw process.
    It requires an Authorization header with a Bearer token.
    
    Returns:
        JSON response indicating the status of the command execution.
    """
    
    global magiclaw_process, zmq_thread

    auth_header = request.headers.get('Authorization', '')
    if not (auth_header.startswith('Bearer ') and auth_header[7:] == AUTH_TOKEN):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    cmd = data.get("cmd", "")
    claw_id = int(data.get("id", 0))
    mode = data.get("mode", "standalone")
    phone_host = data.get("phone_host", "")
    bilateral_host = data.get("bilateral_host", "")

    magiclaw_path = "/home/pi/miniconda3/envs/magiclaw/bin/run-magiclaw"

    if cmd == "run-magiclaw":
        if claw_id in magiclaw_process and magiclaw_process[claw_id].poll() is None:
            return jsonify({"id": claw_id, "status": "already running"})

        magiclaw_cmd = [magiclaw_path, "--id", str(claw_id), "--mode", mode]
        if phone_host != "":
            magiclaw_cmd += ["--phone_host", phone_host]
        if bilateral_host != "":
            magiclaw_cmd += ["--bilateral_host", bilateral_host]
        print("[run-magiclaw] cmd:", " ".join(magiclaw_cmd))

        env = os.environ.copy()
        proc = subprocess.Popen(
            magiclaw_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env,
            preexec_fn=os.setsid
        )
        magiclaw_process[claw_id] = proc
        stop_zmq_flag[claw_id] = threading.Event()
        stop_zmq_flag[claw_id].clear()
        threading.Thread(target=zmq_subscriber, args=(claw_id,), daemon=True).start()
        threading.Thread(target=read_process_output, args=(proc, claw_id), daemon=True).start()
        return jsonify({
            "id": claw_id, 
            "status": "started",
            "cmd": " ".join(magiclaw_cmd),
        })

    elif cmd == "stop-magiclaw":
        if claw_id in magiclaw_process and magiclaw_process[claw_id].poll() is None:
            os.killpg(os.getpgid(magiclaw_process[claw_id].pid), signal.SIGINT)
            magiclaw_process.pop(claw_id)
            stop_zmq_flag[claw_id].set()
            return jsonify({"id": claw_id, "status": "stopped"})
        else:
            return jsonify({"id": claw_id, "status": "not running"})

    return jsonify({"error": "Unknown cmd"}), 400

# Flask route to serve the favicon
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8000)
