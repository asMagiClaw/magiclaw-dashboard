#!/bin/bash
# -*- coding: utf-8 -*-

set -e
set -x

DASHBOARD_DIR="$HOME/Documents/magiclaw-dashboard"
SERVICE_FILE="/etc/systemd/system/magiclaw-dashboard.service"

### Activate magiclaw environment
echo "Activating conda environment 'magiclaw'..."
source ~/.bashrc
conda activate magiclaw

### Install dependencies
echo "Installing dashboard requirements..."
cd "$DASHBOARD_DIR"
pip install -r requirements.txt

# 获取当前环境 Python 路径
PYTHON_PATH=$(which python)

### Create systemd service
echo "Creating systemd service file at $SERVICE_FILE..."
sudo bash -c "cat > $SERVICE_FILE" <<EOL
[Unit]
Description=MagiClaw Dashboard Web Server
After=network.target

[Service]
ExecStart=$PYTHON_PATH app.py
WorkingDirectory=$DASHBOARD_DIR
Restart=always
User=pi
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOL

echo "Reloading systemd daemon and enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable magiclaw-dashboard.service
sudo systemctl start magiclaw-dashboard.service

echo "✅ MagiClaw Dashboard service installed and started!"
echo "You can check logs with: journalctl -u magiclaw-dashboard -f"
