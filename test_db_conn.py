import psycopg2
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("DATABASE_URL")

async def test_asyncpg():
    print(f"Testing asyncpg with {url}...")
    try:
        conn = await asyncpg.connect(url)
        print("asyncpg: Success!")
        await conn.close()
    except Exception as e:
        print(f"asyncpg: Failed! {e}")

def test_psycopg2():
    print(f"Testing psycopg2 with {url}...")
    try:
        conn = psycopg2.connect(url)
        print("psycopg2: Success!")
        conn.close()
    except Exception as e:
        print(f"psycopg2: Failed! {e}")

if __name__ == "__main__":
    test_psycopg2()
    asyncio.run(test_asyncpg())
