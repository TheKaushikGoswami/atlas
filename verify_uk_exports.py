import aiohttp
import asyncio
import json

async def fetch_uk_all():
    # Use Year 2022 as it's the most stable widely available
    url = "https://api-v2.oec.world/tesseract/data.jsonrecords?cube=trade_i_baci_a_17&drilldowns=HS4+Official&measures=Trade+Value&include=Exporter+Country+Official:gbr,Year:2022&limit=500"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                records = data.get("data", [])
                print(f"Fetched {len(records)} records for UK 2022.")
                
                # Sort by Trade Value descending
                sorted_records = sorted(records, key=lambda x: x["Trade Value"], reverse=True)
                
                print("\nTop 20 Exports for UK (Manual Sort):")
                for i, r in enumerate(sorted_records[:20], 1):
                    print(f"{i}. {r['HS4 Official']} (ID: {r['HS4 Official ID']}) - ${r['Trade Value']:,.0f}")
            else:
                print(f"Failed: {response.status}")

if __name__ == "__main__":
    asyncio.run(fetch_uk_all())
