import aiohttp
import asyncio
import json
import os
from pathlib import Path

# Data directory
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

async def fetch_json(session, url):
    async with session.get(url) as response:
        if response.status == 200:
            return await response.json()
        return None

async def fetch_trade_data():
    """Fetch top 10 exports for each country from OEC."""
    # 1. Load OEC members for mapping
    with open("oec_countries.json", "r") as f:
        oec_data = json.load(f)
    
    members = oec_data["members"]
    # We want to map ISO2 -> OEC key
    # OEC members have 'key' and 'caption'
    # We'll also fetch ISO2 from REST Countries to be sure
    
    print("Fetching ISO2 mappings from REST Countries...")
    async with aiohttp.ClientSession() as session:
        countries_resp = await fetch_json(session, "https://restcountries.com/v3.1/all?fields=name,cca2,capitalInfo,flags")
        if not countries_resp:
            print("Failed to fetch country data from REST Countries.")
            return

        iso_to_name = {c["cca2"]: c["name"]["common"] for c in countries_resp}
        name_to_iso = {c["name"]["common"].lower(): c["cca2"] for c in countries_resp}
        iso_to_coords = {}
        for c in countries_resp:
            coords = c.get("capitalInfo", {}).get("latlng")
            if coords:
                iso_to_coords[c["cca2"]] = {"lat": coords[0], "lng": coords[1]}

        # Map OEC keys to ISO2
        oec_to_iso = {}
        for m in members:
            name = m["caption"].lower()
            if name in name_to_iso:
                oec_to_iso[m["key"]] = name_to_iso[name]
            elif "south korea" in name:
                oec_to_iso[m["key"]] = "KR"
            elif "north korea" in name:
                oec_to_iso[m["key"]] = "KP"
            elif "united states" in name:
                oec_to_iso[m["key"]] = "US"
            elif "russia" in name:
                oec_to_iso[m["key"]] = "RU"
            # Add more manual mappings as needed
        
        print(f"Mapped {len(oec_to_iso)} OEC countries to ISO2.")

        trade_data = {}
        semaphore = asyncio.Semaphore(5) # Rate limit protection

        async def fetch_country_trade(oec_key, iso2):
            async with semaphore:
                # Fetch more records as Tesseract sort might be biased
                url = f"https://api-v2.oec.world/tesseract/data.jsonrecords?cube=trade_i_baci_a_17&drilldowns=HS4+Official&measures=Trade+Value&include=Exporter+Country+Official:{oec_key.lower()[-3:]},Year:2022&limit=500"
                await asyncio.sleep(0.5)
                data = await fetch_json(session, url)
                if data and "data" in data:
                    records = data["data"]
                    # Manual sort to ensure absolute top products across all sectors
                    records = sorted(records, key=lambda x: x["Trade Value"], reverse=True)[:10]
                    total_val = sum(r["Trade Value"] for r in records)
                    exports = []
                    for r in records:
                        exports.append({
                            "product": r["HS4 Official"],
                            "value": r["Trade Value"],
                            "share": r["Trade Value"] / total_val if total_val > 0 else 0
                        })
                    
                    # Format total value
                    if total_val > 1e12:
                        total_str = f"${total_val/1e12:.1f}T"
                    elif total_val > 1e9:
                        total_str = f"${total_val/1e9:.1f}B"
                    else:
                        total_str = f"${total_val/1e6:.1f}M"

                    trade_data[iso2] = {
                        "total": total_str,
                        "exports": exports
                    }
                    print(f"Fetched trade data for {iso2}")

        tasks = []
        # Fetch for top countries first to avoid hitting limits on 250 countries if unwanted
        # But we want all. Let's try 50 major ones first as a sample if it's too much.
        # For Tradle, we need a good pool.
        for oec_key, iso2 in oec_to_iso.items():
            tasks.append(fetch_country_trade(oec_key, iso2))
        
        print(f"Starting batch fetch for {len(tasks)} countries...")
        await asyncio.gather(*tasks)

        # Save files
        with open(DATA_DIR / "trade_data.json", "w") as f:
            json.dump(trade_data, f, indent=4)
        
        with open(DATA_DIR / "capitals_coords.json", "w") as f:
            json.dump(iso_to_coords, f, indent=4)
        
        print("Data preparation complete!")

if __name__ == "__main__":
    asyncio.run(fetch_trade_data())
