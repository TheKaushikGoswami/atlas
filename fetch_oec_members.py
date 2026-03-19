import aiohttp
import asyncio
import json

async def fetch_members():
    url = "https://api-v2.oec.world/tesseract/members?cube=trade_i_baci_a_17&level=Exporter+Country"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                with open("oec_countries.json", "w") as f:
                    json.dump(data, f, indent=4)
                print("Successfully fetched OEC country members mapping.")
            else:
                print(f"Failed to fetch OEC members: Status {response.status}")

if __name__ == "__main__":
    asyncio.run(fetch_members())
