@echo off
echo 🚀 Starting Atlas Bot Windows Setup...

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python not found! Please install Python from python.org
    exit /b 1
)

:: 2. Setup Venv
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

echo 📥 Installing dependencies...
call .\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

:: 3. Setup .env
if not exist ".env" (
    echo ⚠️ .env file missing! Copying from .env.example...
    copy .env.example .env
    echo Please edit .env with your DISCORD_TOKEN and DATABASE_URL before running.
)

:: 4. Seed Database
echo 🗄️ Seeding geography database...
python scripts/setup_db.py

echo ✅ Setup finished!
echo To start the bot, run: python main.py
pause
