import psycopg2
import sys
import os
from pathlib import Path

# Add parent dir to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from config import config

def verify():
    test_states = ["California", "Texas", "New York", "Alabama"]
    conn = psycopg2.connect(config.DATABASE_URL)
    with conn.cursor() as cur:
        for state in test_states:
            cur.execute("SELECT name_display, country_code FROM geography WHERE name_display = %s", (state,))
            result = cur.fetchone()
            if result:
                print(f"✅ Found: {result[0]} ({result[1]})")
            else:
                print(f"❌ Not found: {state}")
    conn.close()

if __name__ == "__main__":
    verify()
