import sys
import os
from pathlib import Path
import psycopg2

# Add parent dir to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from config import config
from db.geo_lookup import normalise_name

def add_places(locations_str, country_code="--", source="Manual"):
    """Add one or more places to the database."""
    # Split by comma and strip whitespace
    locations = [loc.strip() for loc in locations_str.split(",") if loc.strip()]
    
    if not locations:
        print("❌ No valid locations provided.")
        return

    added_count = 0
    skipped_count = 0
    
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor() as cur:
            for location in locations:
                norm = normalise_name(location)
                if not norm:
                    print(f"⚠️ Skipping invalid name: '{location}'")
                    continue
                
                cur.execute(
                    "INSERT INTO geography (name_normalised, name_display, country_code, source) VALUES (%s, %s, %s, %s) ON CONFLICT (name_normalised) DO NOTHING",
                    (norm, location, country_code, source)
                )
                
                if cur.rowcount > 0:
                    added_count += 1
                else:
                    skipped_count += 1
            
            conn.commit()
        
        print(f"✅ Successfully added {added_count} places.")
        if skipped_count > 0:
            print(f"ℹ️ {skipped_count} places were already in the database and were skipped.")
            
    except Exception as e:
        print(f"❌ Error adding to DB: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    if len(sys.argv) > 1:
        # Use arguments if provided
        locations_str = " ".join(sys.argv[1:])
        add_places(locations_str)
    else:
        # Interactive mode
        print("--- 🌍 Atlas Place Adder ---")
        print("Enter places separated by commas to add them to the database.")
        while True:
            query = input("\nEnter places (or 'q' to quit): ").strip()
            if not query or query.lower() == 'q':
                break
            add_places(query)

if __name__ == "__main__":
    main()
