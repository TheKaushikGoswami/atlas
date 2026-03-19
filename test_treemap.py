import json
from pathlib import Path
from tradle.treemap import TradleTreemap

def test_gen_treemap():
    with open("data/trade_data.json", "r") as f:
        data = json.load(f)
    
    # Generate for France
    fr_data = data.get("FR")
    if fr_data:
        img_buf = TradleTreemap.generate(fr_data["exports"], fr_data["total"])
        with open("test_treemap_fr.png", "wb") as f:
            f.write(img_buf.read())
        print("Generated test_treemap_fr.png")
    else:
        print("France data not found.")

if __name__ == "__main__":
    test_gen_treemap()
