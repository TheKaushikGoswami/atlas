import sys
import os
from pathlib import Path
import psycopg2
from psycopg2.extras import DictCursor

# Add parent dir to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from config import config
from db.geo_lookup import normalise_name

def search_places(query):
    """Search for places matching the query (normalised)."""
    norm_query = normalise_name(query)
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor(cursor_factory=DictCursor) as cur:
            # Use LIKE for fuzzy-ish matching on the normalised name
            cur.execute(
                "SELECT id, name_display, name_normalised, country_code, source FROM geography WHERE name_normalised LIKE %s LIMIT 10",
                (f"%{norm_query}%",)
            )
            return cur.fetchall()
    except Exception as e:
        print(f"❌ Error searching DB: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()

def delete_place(place_id):
    """Delete a place by its ID."""
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM geography WHERE id = %s", (place_id,))
            conn.commit()
        return True
    except Exception as e:
        print(f"❌ Error deleting from DB: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    print("--- 🌍 Atlas Place Remover ---")
    while True:
        query = input("\nEnter a place name to search (or 'q' to quit): ").strip()
        if not query or query.lower() == 'q':
            break

        results = search_places(query)
        if not results:
            print(f"❌ No matches found for '{query}'.")
            continue

        print(f"\nMatches for '{query}':")
        for i, row in enumerate(results):
            print(f"[{i}] ID: {row['id']} | {row['name_display']} ({row['country_code']}) | Source: {row['source']}")

        choice = input("\nEnter index to DELETE, or press Enter to search again: ").strip()
        if not choice:
            continue

        try:
            idx = int(choice)
            if 0 <= idx < len(results):
                place = results[idx]
                confirm = input(f"⚠️ Are you sure you want to delete '{place['name_display']}' (ID: {place['id']})? [y/N]: ").strip().lower()
                if confirm == 'y':
                    if delete_place(place['id']):
                        print(f"✅ Deleted '{place['name_display']}'.")
                    else:
                        print(f"❌ Failed to delete.")
                else:
                    print("Skipped.")
            else:
                print("❌ Invalid index.")
        except ValueError:
            print("❌ Please enter a valid number.")

if __name__ == "__main__":
    main()
