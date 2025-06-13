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
magiclaw_process = None
zmq_thread = None
stop_zmq_flag = threading.Event()

# Function to read and process output from the subprocess
def read_process_output(proc):
    """
    Reads the output from the subprocess and emits it via SocketIO.
    
    Args:
        proc (subprocess.Popen): The subprocess to read output from.
    """
    
    try:
        for line in iter(proc.stdout.readline, ''):
            if line:
                line = line.rstrip()
                print("[run-magiclaw]", line)
                socketio.emit('log', line)
        proc.stdout.close()
    except Exception as e:
        print("[read error]", e)

# ZMQ subscriber function to listen for messages from the MagiClaw
def zmq_subscriber():
    """
    Subscribes to the ZMQ socket and emits messages via SocketIO.
    
    This function runs in a separate thread to avoid blocking the main thread.
    It listens for messages from the MagiClaw and emits them to connected clients.
    """
    
    context = zmq.Context()
    sub = context.socket(zmq.SUB)
    sub.setsockopt(zmq.CONFLATE, 1)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")
    sub.connect("tcp://localhost:6300")

    msg = magiclaw_msg_pb2.MagiClaw()

    while not stop_zmq_flag.is_set():
        try:
            data = sub.recv(flags=zmq.NOBLOCK)
            msg.ParseFromString(data)

            # parse data
            data_to_emit = {
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

    magiclaw_path = "/home/pi/miniconda3/bin/run-magiclaw"

    if cmd == "run-magiclaw":
        if magiclaw_process and magiclaw_process.poll() is None:
            return jsonify({"status": "already running"})

        env = os.environ.copy()
        magiclaw_process = subprocess.Popen(
            [magiclaw_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env,
            preexec_fn=os.setsid
        )
        stop_zmq_flag.clear()
        zmq_thread = threading.Thread(target=zmq_subscriber, daemon=True)
        zmq_thread.start()
        threading.Thread(target=read_process_output, args=(magiclaw_process,), daemon=True).start()
        return jsonify({"status": "started"})

    elif cmd == "stop-magiclaw":
        if magiclaw_process and magiclaw_process.poll() is None:
            os.killpg(os.getpgid(magiclaw_process.pid), signal.SIGINT)
            magiclaw_process = None
            stop_zmq_flag.set()
            return jsonify({"status": "stopped"})
        else:
            return jsonify({"status": "not running"})

    return jsonify({"error": "Unknown cmd"}), 400

# Flask route to serve the favicon
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8000)
