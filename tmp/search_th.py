import asyncio
import asyncpg

async def check():
    try:
        conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/atlas_bot")
        
        # Search for Thailand round
        th_round = await conn.fetchrow("SELECT * FROM tradle_rounds WHERE target_country_iso = 'TH' ORDER BY id DESC")
        if th_round:
            print(f"Thailand (TH) was Round #{th_round['id']} (Started at: {th_round['started_at']})")
        else:
            print("No Thailand (TH) round found.")
        
        # Current round for 23
        r23 = await conn.fetchrow("SELECT * FROM tradle_rounds WHERE id = 23")
        if r23:
            print(f"Round 23 is: {r23['target_country_iso']}")
        else:
            print("Round 23 not found.")

        # Neighbors
        neighbors = await conn.fetch("SELECT id, target_country_iso FROM tradle_rounds WHERE id BETWEEN 20 AND 25 ORDER BY id")
        for n in neighbors:
            print(f"Round {n['id']}: {n['target_country_iso']}")
            
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(check())
