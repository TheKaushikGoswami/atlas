import aiohttp
import asyncio
import json
import random
import os

async def fetch_json(session, url):
    async with session.get(url) as response:
        if response.status == 200:
            return await response.json()
        return None

async def fetch_random_10():
    """Fetch top exports for 10 random countries from OEC."""
    # 1. Load OEC members
    if not os.path.exists("oec_countries.json"):
        print("oec_countries.json not found. Run fetch_oec_members.py first.")
        return

    with open("oec_countries.json", "r") as f:
        oec_data = json.load(f)
    members = oec_data["members"]
    
    # 2. Pick 10 random
    selected = random.sample(members, 10)
    print(f"Selected 10 random countries: {[m['caption'] for m in selected]}")

    results = {}
    async with aiohttp.ClientSession() as session:
        for m in selected:
            oec_key = m["key"]
            country_name = m["caption"]
            print(f"Fetching top exports for {country_name} ({oec_key})...")
            
            # Fetching more records and sorting manually to avoid sectoral bias in API response
            iso3 = m["key"].lower()[-3:]
            url = f"https://api-v2.oec.world/tesseract/data.jsonrecords?cube=trade_i_baci_a_17&drilldowns=HS4+Official&measures=Trade+Value&include=Exporter+Country+Official:{iso3},Year:2022&limit=100"
            
            data = await fetch_json(session, url)
            if data and "data" in data:
                records = data["data"]
                # Manual sort to ensure we get the absolute top products regardless of HS Section
                top_records = sorted(records, key=lambda x: x["Trade Value"], reverse=True)[:10]
                exports = [{"product": r["HS4 Official"], "value": r["Trade Value"]} for r in top_records]
                results[country_name] = exports
            else:
                print(f"Failed to fetch data for {country_name}")
            
            await asyncio.sleep(1) # Be nice to the API

    # 3. Print results nicely
    print("\n" + "="*40)
    print("TOP EXPORTS FOR 10 RANDOM COUNTRIES")
    print("="*40)
    for country, exports in results.items():
        print(f"\n🌍 {country}:")
        for i, exp in enumerate(exports, 1):
            print(f"  {i}. {exp['product']} (${exp['value']:,.0f})")
    print("="*40)

    # 4. Save to file
    with open("random_10_exports.json", "w") as f:
        json.dump(results, f, indent=4)
    print("\nResults saved to random_10_exports.json")

if __name__ == "__main__":
    asyncio.run(fetch_random_10())
