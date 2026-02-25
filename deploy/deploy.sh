#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting Atlas Bot Deployment..."

# 1. Update system
sudo apt update && sudo apt install -y python3-venv python3-dev libpq-dev postgresql postgresql-contrib

# 2. Setup Venv
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

echo "📥 Installing dependencies..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 3. Setup .env if missing
if [ ! -f ".env" ]; then
    echo "⚠️ .env file missing! Copying from .env.example..."
    cp .env.example .env
    echo "Please edit .env with your DISCORD_TOKEN and DATABASE_URL before running."
fi

# 4. Seed Database
echo "🗄️ Seeding geography database (this may take a few minutes)..."
./venv/bin/python scripts/setup_db.py

# 5. systemd setup
echo "🛠️ Configuring systemd service..."
sudo cp deploy/atlas.service /etc/systemd/system/atlas.service
sudo systemctl daemon-reload
sudo systemctl enable atlas

echo "✅ Deployment finished!"
echo "Run 'sudo systemctl start atlas' to start the bot."
echo "Monitor logs with 'journalctl -u atlas -f'"
