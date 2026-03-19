import asyncio
import json
import os
from tradle.engine import TradleEngine
from tradle.db import TradleLookup
from config import config

async def fix_data():
    print("Starting Tradle Data Fix Script...")
    engine = TradleEngine()
    db = TradleLookup(config.DATABASE_URL)
    
    await db.connect()
    async with db.pool.acquire() as conn:
        # 1. Fetch all guesses that have 0 distance but are NOT correct
        # or have 100% proximity but are NOT correct
        rows = await conn.fetch("SELECT * FROM tradle_guesses WHERE (distance_km = 0 AND is_correct = FALSE) OR (proximity_pct = 100 AND is_correct = FALSE)")
        print(f"Found {len(rows)} potentially buggy guesses.")
        
        for row in rows:
            guess_id = row["id"]
            guess_iso = row["country_iso"]
            round_id = row["round_id"]
            
            # Get target ISO for this round
            round_row = await conn.fetchrow("SELECT target_country_iso FROM tradle_rounds WHERE id = $1", round_id)
            if not round_row: continue
            target_iso = round_row["target_country_iso"]
            
            # Recalculate
            dist = engine.calculate_distance(guess_iso, target_iso)
            prox = engine.proximity_percentage(dist)
            
            if dist is not None:
                print(f"Updating guess {guess_id} ({guess_iso} -> {target_iso}): {dist:.0f}km, {prox}%")
                await conn.execute(
                    "UPDATE tradle_guesses SET distance_km = $1, proximity_pct = $2 WHERE id = $3",
                    dist, prox, guess_id
                )
            else:
                # Still missing coordinates?
                print(f"Still missing coordinates for {guess_iso} or {target_iso}")
                await conn.execute(
                    "UPDATE tradle_guesses SET proximity_pct = 0 WHERE id = $1",
                    guess_id
                )
                
    print("Fix complete!")

if __name__ == "__main__":
    asyncio.run(fix_data())
