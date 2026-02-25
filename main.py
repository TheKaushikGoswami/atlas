import logging
import asyncio
from config import config
from bot.bot import create_bot
from db.geo_lookup import GeoLookup

# Setup logging
log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log")
    ]
)
logger = logging.getLogger("main")

async def run():
    # 1. Initialise GeoLookup
    if not config.DATABASE_URL:
        logger.error("DATABASE_URL not set in .env")
        return

    geo_lookup = GeoLookup(config.DATABASE_URL)
    await geo_lookup.connect()

    # 2. Create the bot
    bot = create_bot()
    
    # Inject geo_lookup into the bot for cogs to use
    bot.geo_lookup = geo_lookup

    #3. Start the bot
    async with bot:
        try:
            await bot.start(config.DISCORD_TOKEN)
        except KeyboardInterrupt:
            logger.info("Bot shutting down...")
        finally:
            await geo_lookup.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
