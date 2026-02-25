import discord
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class AtlasBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        """Initialise cogs and sync slash commands."""
        logger.info("Setting up cogs...")
        await self.load_extension("bot.cogs.atlas")
        
        # Syncing globally for now. Can be guild-specific for speed in dev.
        # await self.tree.sync()
        # logger.info("Slash commands synced.")

    async def on_ready(self):
        logger.info(f"Bot is online as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guilds.")
        
        # Syncing slash commands on ready is also common
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} application commands.")
        except Exception as e:
            logger.error(f"Error syncing commands: {e}")

def create_bot():
    intents = discord.Intents.default()
    intents.message_content = True  # Required to listen for answers
    intents.members = True          # Helpful to get names/display info
    intents.guilds = True

    bot = AtlasBot(
        command_prefix="!", # Still need a prefix for legacy, though we use slash
        intents=intents,
        help_command=None
    )
    return bot
