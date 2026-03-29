import asyncio
import asyncpg
import logging
import sys
from pathlib import Path

# Add parent dir to path for config import
sys.path.append(str(Path(__file__).parent.parent))
from config import config

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def setup_tradle_db():
    """Setup Tradle-specific database schema using asyncpg."""
    url = config.DATABASE_URL
    if not url:
        logger.error("DATABASE_URL not set in .env")
        return

    try:
        logger.info(f"Connecting to {url}...")
        conn = await asyncpg.connect(url)
        
        logger.info("Creating Tradle-specific tables...")
        
        # 1. tradle_rounds: stores history of 12h rounds
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tradle_rounds (
                id SERIAL PRIMARY KEY,
                target_country_iso CHAR(2) NOT NULL,
                started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP WITH TIME ZONE,
                total_export_value_str TEXT, -- e.g. "$18.9B"
                is_active BOOLEAN DEFAULT TRUE
            );
        """)

        # 2. tradle_guesses: individual player guesses per round
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tradle_guesses (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                round_id INT REFERENCES tradle_rounds(id),
                guesses_json JSONB NOT NULL, -- list of guess objects
                won BOOLEAN DEFAULT FALSE,
                score INT, -- number of guesses (1-6)
                completed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, round_id)
            );
        """)

        # 3. tradle_stats: long-term player stats
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tradle_stats (
                user_id BIGINT PRIMARY KEY,
                total_played INT DEFAULT 0,
                total_won INT DEFAULT 0,
                current_streak INT DEFAULT 0,
                best_streak INT DEFAULT 0,
                total_score INT DEFAULT 0 -- sum of scores for avg calculation
            );
        """)

        # 4. tradle_config: server-level configuration
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tradle_config (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT, -- where auto-posts go (default #general or similar)
                is_active BOOLEAN DEFAULT FALSE -- Opt-in ONLY after first usage
            );
        """)

        # 5. tradle_live_posts: persistent mapping for public live progress messages
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tradle_live_posts (
                round_id INT NOT NULL REFERENCES tradle_rounds(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (round_id, user_id, guild_id)
            );
        """)
        
        # Create indexes for performance
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tradle_guesses_round ON tradle_guesses(round_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tradle_guesses_user ON tradle_guesses(user_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tradle_live_posts_message ON tradle_live_posts(message_id);")
        
        logger.info("Tradle database setup complete!")
        await conn.close()
        
    except Exception as e:
        logger.error(f"Error setting up Tradle database: {e}")

if __name__ == "__main__":
    asyncio.run(setup_tradle_db())
