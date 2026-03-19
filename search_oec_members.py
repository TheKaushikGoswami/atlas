import aiohttp
import asyncio
import json

async def search_members():
    url = "https://api-v2.oec.world/tesseract/members?cube=trade_i_baci_a_17&level=HS4+Official"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                members = data.get("members", [])
                keywords = ["Cars", "Petroleum", "Gold", "Medicaments", "Machinery"]
                found = []
                for m in members:
                    caption = m.get("caption", "").lower()
                    for k in keywords:
                        if k.lower() in caption:
                            found.append(m)
                
                print(f"Found {len(found)} matching members:")
                for f in found[:20]:
                    print(f"- {f['caption']} (ID: {f['key']})")
                
                # Check IDs
                print("\nSample IDs:")
                for f in found[:5]:
                    print(f"  {f['caption']}: {f['key']}")
            else:
                print(f"Failed: {response.status}")

if __name__ == "__main__":
    asyncio.run(search_members())
