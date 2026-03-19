import asyncio
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add parent dir to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from tradle.engine import TradleEngine
from tradle.db import TradleLookup
from config import config

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

async def fix_data():
    logger.info("Starting Tradle JSONB Data Fix Script...")
    engine = TradleEngine()
    db = TradleLookup(config.DATABASE_URL)
    
    await db.connect()
    async with db.pool.acquire() as conn:
        # Fetch all player sessions
        rows = await conn.fetch("SELECT * FROM tradle_guesses")
        logger.info(f"Checking {len(rows)} player sessions...")
        
        updates = 0
        for row in rows:
            user_id = row["user_id"]
            round_id = row["round_id"]
            guesses_json = row["guesses_json"]
            
            try:
                guesses = json.loads(guesses_json)
            except Exception:
                continue
                
            # Get target ISO for this round
            round_row = await conn.fetchrow("SELECT target_country_iso FROM tradle_rounds WHERE id = $1", round_id)
            if not round_row: continue
            target_iso = round_row["target_country_iso"]
            
            changed = False
            new_guesses = []
            for g in guesses:
                guess_iso = g["country_iso"]
                is_correct = g.get("is_correct", False)
                
                # Check for buggy 0km + incorrect OR 100% + incorrect
                dist = g.get("distance_km", 0)
                prox = g.get("proximity_pct", 0)
                
                if not is_correct and (dist == 0 or prox == 100):
                    # Recalculate
                    new_dist = engine.calculate_distance(guess_iso, target_iso)
                    new_prox = engine.proximity_percentage(new_dist)
                    
                    if new_dist is not None:
                        logger.info(f"Fixing {user_id} @ Round {round_id}: {guess_iso} -> {target_iso} ({new_dist:.0f}km, {new_prox}%)")
                        g["distance_km"] = new_dist
                        g["proximity_pct"] = new_prox
                        changed = True
                    else:
                        # Still missing? (e.g. target is still missing in memory if not reloaded, 
                        # but engine() loads from disk so it should have Macao now).
                        g["distance_km"] = 0.0
                        g["proximity_pct"] = 0
                        changed = True
                
                new_guesses.append(g)
            
            if changed:
                await conn.execute(
                    "UPDATE tradle_guesses SET guesses_json = $1 WHERE user_id = $2 AND round_id = $3",
                    json.dumps(new_guesses), user_id, round_id
                )
                updates += 1
                
    logger.info(f"Fix complete! Updated {updates} sessions.")

if __name__ == "__main__":
    asyncio.run(fix_data())
