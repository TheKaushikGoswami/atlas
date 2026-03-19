import aiohttp
import asyncio
import json

async def check_cube():
    url = "https://api-v2.oec.world/tesseract/cubes/trade_i_baci_a_17"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                print("Dimensions in trade_i_baci_a_17:")
                for dim in data.get("dimensions", []):
                    print(f"- {dim['name']}: {', '.join([h['name'] for h in dim.get('hierarchies', [])])}")
                    for hier in dim.get("hierarchies", []):
                        for level in hier.get("levels", []):
                            print(f"  * Level: {level['name']}")
                
                print("\nMeasures:")
                for measure in data.get("measures", []):
                    print(f"- {measure['name']}")
            else:
                print(f"Failed to fetch cube info: {response.status}")

if __name__ == "__main__":
    asyncio.run(check_cube())
