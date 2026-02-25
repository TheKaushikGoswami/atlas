import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Config:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL")
    TURN_TIMEOUT = int(os.getenv("TURN_TIMEOUT", 30))
    
    # Project root
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / "data"

config = Config()

if __name__ == "__main__":
    print(f"Project ROOT: {config.BASE_DIR}")
    print(f"DB URL: {config.DATABASE_URL}")
    print(f"Timeout: {config.TURN_TIMEOUT}")
