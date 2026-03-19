import aiohttp
import asyncio
import json

async def count_members():
    url = "https://api-v2.oec.world/tesseract/members?cube=trade_i_baci_a_17&level=HS4+Official"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                members = data.get("members", [])
                print(f"Total HS4 Official members: {len(members)}")
                
                # Check for common sectors
                sections = {}
                for m in members:
                    key = str(m['key'])
                    chapter = key[:-2] if len(key) >= 2 else "0"
                    sections[chapter] = sections.get(chapter, 0) + 1
                
                print("\nDistribution by Chapter (approx):")
                sorted_chapters = sorted(sections.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)
                for chap, count in sorted_chapters[:10]:
                    print(f"  Chapter {chap}: {count} products")
                
                # Check for high chapters
                last_chapters = sorted_chapters[-5:]
                for chap, count in last_chapters:
                    print(f"  Chapter {chap}: {count} products")
            else:
                print(f"Failed: {response.status}")

if __name__ == "__main__":
    asyncio.run(count_members())
