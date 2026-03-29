import asyncio
import asyncpg
import json

async def check():
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/atlas_bot")
    
    # Get recent rounds
    rounds = await conn.fetch("SELECT * FROM tradle_rounds ORDER BY id DESC LIMIT 10")
    
    print(f"{'ID':<5} | {'ISO':<5} | {'Started At':<30} | {'Active'}")
    print("-" * 60)
    for r in rounds:
        print(f"{r['id']:<5} | {r['target_country_iso']:<5} | {str(r['started_at']):<30} | {r['is_active']}")

    await conn.close()

asyncio.run(check())
