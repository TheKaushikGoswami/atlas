import json
import sys
import os
from pathlib import Path

# Add parent dir to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from config import config
import psycopg2
from scripts.setup_db import normalise_name

def load_suggestions():
    if not config.SUGGESTIONS_FILE.exists():
        return []
    with open(config.SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_suggestions(suggestions):
    with open(config.SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(suggestions, f, indent=4)

def add_to_db(location):
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor() as cur:
            norm = normalise_name(location)
            cur.execute(
                "INSERT INTO geography (name_normalised, name_display, country_code, source) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (norm, location, "--", "Manual")
            )
            conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error adding to DB: {e}")
        return False

def main():
    while True:
        suggestions = load_suggestions()
        if not suggestions:
            print("\n✅ No pending suggestions.")
            break
        
        print(f"\n--- Pending Suggestions ({len(suggestions)}) ---")
        for i, s in enumerate(suggestions):
            print(f"[{i}] {s['location']} (by {s['suggested_by']})")
        
        try:
            cmd = input("\nEnter index to approve, 'r<index>' to reject, or 'q' to quit: ").strip().lower()
            if cmd == 'q':
                break
            
            if cmd.startswith('r'):
                idx = int(cmd[1:])
                removed = suggestions.pop(idx)
                save_suggestions(suggestions)
                print(f"🗑️ Rejected: {removed['location']}")
            else:
                idx = int(cmd)
                location = suggestions[idx]['location']
                if add_to_db(location):
                    suggestions.pop(idx)
                    save_suggestions(suggestions)
                    print(f"✅ Approved and added to DB: {location}")
        except (ValueError, IndexError):
            print("❌ Invalid input.")

if __name__ == "__main__":
    main()
