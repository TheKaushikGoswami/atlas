import asyncio
import asyncpg
import json

async def check():
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/atlas_bot")
    
    # Get round info
    round_info = await conn.fetchrow("SELECT * FROM tradle_rounds WHERE id = 23")
    if not round_info:
        print("Round 23 not found.")
        await conn.close()
        return
        
    print(f"--- Round 23 Summary ---")
    print(f"Target ISO: {round_info['target_country_iso']}")
    print(f"Started At: {round_info['started_at']}")
    print(f"Ended At: {round_info['ended_at']}")
    print(f"Total Export: {round_info['total_export_value_str']}")
    print("-" * 30)

    # Get results
    results = await conn.fetch("""
        SELECT user_id, won, score, completed_at
        FROM tradle_guesses 
        WHERE round_id = 23 
        ORDER BY won DESC, score ASC, completed_at ASC
    """)
    
    if not results:
        print("No players found for Round 23.")
    else:
        print(f"Found {len(results)} player(s):")
        for r in results:
            status = "WON" if r['won'] else "LOST"
            print(f"User {r['user_id']}: {status} in {r['score']}/6 at {r['completed_at']}")

    await conn.close()

asyncio.run(check())
