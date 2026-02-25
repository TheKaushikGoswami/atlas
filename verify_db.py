import asyncio
from db.geo_lookup import GeoLookup
from config import config

async def test():
    lookup = GeoLookup(config.DATABASE_URL)
    await lookup.connect()
    
    cities = ["Mumbai", "London", "New York City", "Delhi", "Bengaluru"]
    for city in cities:
        is_valid = await lookup.is_valid(city)
        print(f"Checking '{city}': {'✅ Valid' if is_valid else '❌ Not Found'}")
    
    await lookup.disconnect()

if __name__ == "__main__":
    asyncio.run(test())
