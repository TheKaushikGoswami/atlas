import asyncpg
import logging
from unidecode import unidecode

logger = logging.getLogger(__name__)

def normalise_name(name: str) -> str:
    if not name:
        return ""
    # Consistent normalisation with the setup_db script
    return unidecode(name).lower().strip()

class GeoLookup:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        """Initialise the connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                self.dsn,
                min_size=2,
                max_size=10,
                command_timeout=10
            )
            logger.info("Connected to Postgres database.")
        except Exception as e:
            logger.error(f"Failed to connect to Postgres: {e}")
            raise

    async def disconnect(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Disconnected from Postgres database.")

    async def is_valid(self, name: str) -> bool:
        """
        Check if a geographical name is valid.
        Case-insensitive and handles normalisation.
        """
        if not self.pool:
            await self.connect()

        normalised = normalise_name(name)
        if not normalised:
            return False

        try:
            # We use the unique index on name_normalised for sub-millisecond lookup
            row = await self.pool.fetchrow(
                "SELECT 1 FROM geography WHERE name_normalised = $1 LIMIT 1",
                normalised
            )
            return row is not None
        except Exception as e:
            logger.error(f"Error looking up name '{name}': {e}")
            return False

    async def record_win(self, guild_id: int, user_id: int):
        """Increment win count for a user in a specific guild."""
        if not self.pool:
            await self.connect()
        try:
            await self.pool.execute("""
                INSERT INTO leaderboard (guild_id, user_id, wins)
                VALUES ($1, $2, 1)
                ON CONFLICT (guild_id, user_id)
                DO UPDATE SET wins = leaderboard.wins + 1
            """, guild_id, user_id)
            logger.info(f"Recorded win for user {user_id} in guild {guild_id}")
        except Exception as e:
            logger.error(f"Failed to record win: {e}")

    async def get_leaderboard(self, guild_id: int, limit: int = 10):
        """Get top players for a guild."""
        if not self.pool:
            await self.connect()
        try:
            return await self.pool.fetch("""
                SELECT user_id, wins
                FROM leaderboard
                WHERE guild_id = $1
                ORDER BY wins DESC
                LIMIT $2
            """, guild_id, limit)
        except Exception as e:
            logger.error(f"Failed to fetch leaderboard: {e}")
            return []

    async def reset_leaderboard(self, guild_id: int):
        """Reset the leaderboard for a specific guild."""
        if not self.pool:
            await self.connect()
        try:
            await self.pool.execute("DELETE FROM leaderboard WHERE guild_id = $1", guild_id)
            logger.info(f"Reset leaderboard for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to reset leaderboard: {e}")
            return False

    async def add_place(self, name: str, country_code: str = "--", source: str = "Discord") -> tuple[bool, str]:
        """
        Add a geographical place to the database.
        Returns (success, message).
        """
        if not self.pool:
            await self.connect()

        normalised = normalise_name(name)
        if not normalised:
            return False, "Invalid place name."

        try:
            result = await self.pool.execute("""
                INSERT INTO geography (name_normalised, name_display, country_code, source)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (name_normalised) DO NOTHING
            """, normalised, name.strip(), country_code, source)
            # asyncpg returns 'INSERT 0 1' on insert, 'INSERT 0 0' on conflict
            if result == "INSERT 0 1":
                logger.info(f"Added place '{name}' to database.")
                return True, f"**{name.strip()}** has been added to the database!"
            else:
                return False, f"**{name.strip()}** already exists in the database."
        except Exception as e:
            logger.error(f"Failed to add place '{name}': {e}")
            return False, f"Database error: {e}"

if __name__ == "__main__":
    # For quick testing
    import asyncio
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    dsn = os.getenv("DATABASE_URL")
    
    async def test():
        lookup = GeoLookup(dsn)
        await lookup.connect()
        try:
            print(f"Is 'Mumbai' valid? {await lookup.is_valid('Mumbai')}")
            print(f"Is 'Gibberish123' valid? {await lookup.is_valid('Gibberish123')}")
        finally:
            await lookup.disconnect()
            
    if dsn:
        asyncio.run(test())
    else:
        print("DATABASE_URL not found in .env")
