import asyncio
import random
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from config import config
from tradle.db import TradleLookup
from tradle.engine import TradleEngine


async def main():
    db = TradleLookup(config.DATABASE_URL)
    engine = TradleEngine()

    valid_isos = list(engine.trade_data.keys())
    if not valid_isos:
        raise RuntimeError("No trade data loaded; cannot create a new Tradle round.")

    target_iso = random.choice(valid_isos)
    trade_info = engine.trade_data[target_iso]

    await db.connect()
    new_round = await db.start_new_round(target_iso, trade_info["total"])
    await db.disconnect()

    print(
        f"Created Tradle round #{new_round.id} "
        f"(target={new_round.target_country_iso}, total={new_round.total_export_value_str})"
    )


if __name__ == "__main__":
    asyncio.run(main())
