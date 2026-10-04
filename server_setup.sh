#!/bin/bash
# One-time setup of the attendance bot on an Ubuntu 22.04 server.
# Clone the repo to ~/bot, create ~/bot/config.txt, then run:  bash ~/bot/server_setup.sh
set -e
cd ~/bot

if [ ! -f config.txt ]; then
  echo "!! ~/bot/config.txt is missing. Copy config.example.txt to config.txt and fill it in first."
  exit 1
fi

echo "== 1/5 Checking the portal and Telegram can be reached from this server =="
portal=$(curl -k -s -o /dev/null -w "%{http_code}" --max-time 25 https://sdc-sppap1.svkm.ac.in:50001/irj/portal || true)
tg=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 https://api.telegram.org || true)
echo "portal: $portal   telegram: $tg"
if [ "$portal" = "000" ] || [ -z "$portal" ]; then
  echo "!! The SVKM portal blocks this server. Hosting here will not work. Stopping."
  exit 1
fi

echo "== 2/5 Installing Python packages =="
sudo apt-get update -y
sudo apt-get install -y python3-pip
sudo pip3 install --upgrade playwright pdfplumber requests

echo "== 3/5 Installing Chrome for the bot =="
sudo python3 -m playwright install-deps chromium
python3 -m playwright install chromium

echo "== 4/5 Securing config and setting the clock to India time =="
chmod 600 config.txt
sudo timedatectl set-timezone Asia/Kolkata   # the 06:00 PM - 07:00 AM window uses the server clock

echo "== 5/5 Creating the always-on service =="
sudo tee /etc/systemd/system/attendance-bot.service > /dev/null <<UNIT
[Unit]
Description=Attendance Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$HOME/bot
ExecStart=/usr/bin/python3 $HOME/bot/attendance_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now attendance-bot
sleep 5
sudo systemctl --no-pager status attendance-bot | head -5
echo
echo "DONE. Send /attendance to your bot on Telegram."
