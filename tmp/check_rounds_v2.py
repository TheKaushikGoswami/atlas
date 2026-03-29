import asyncio
import asyncpg

async def check():
    for attempt in range(3):
        try:
            conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/atlas_bot")
            rounds = await conn.fetch("SELECT id, target_country_iso, started_at FROM tradle_rounds ORDER BY id DESC LIMIT 5")
            print(f"{'ID':<5} | {'ISO':<5} | {'Started At':<30}")
            print("-" * 50)
            for r in rounds:
                print(f"{r['id']:<5} | {r['target_country_iso']:<5} | {str(r['started_at']):<30}")
            await conn.close()
            return
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(2)

asyncio.run(check())
