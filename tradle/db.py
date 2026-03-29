import asyncpg
import logging
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from .state import TradleRound, PlayerSession, GuessEntry

logger = logging.getLogger(__name__)

class TradleLookup:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
            logger.info("TradleLookup connected to Postgres.")

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logger.info("TradleLookup disconnected.")

    async def get_active_round(self) -> Optional[TradleRound]:
        """Fetch the currently active 12h round."""
        if not self.pool: await self.connect()
        row = await self.pool.fetchrow(
            "SELECT * FROM tradle_rounds WHERE is_active = TRUE ORDER BY started_at DESC LIMIT 1"
        )
        if row:
            return TradleRound(
                id=row["id"],
                target_country_iso=row["target_country_iso"],
                started_at=row["started_at"],
                total_export_value_str=row["total_export_value_str"],
                ended_at=row["ended_at"],
                is_active=row["is_active"]
            )
        return None

    async def start_new_round(self, target_iso: str, total_val_str: str) -> TradleRound:
        """Deactivate old rounds and start a new one."""
        if not self.pool: await self.connect()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Deactivate all current rounds
                await conn.execute("UPDATE tradle_rounds SET is_active = FALSE, ended_at = NOW() WHERE is_active = TRUE")
                
                # Start new round
                row = await conn.fetchrow("""
                    INSERT INTO tradle_rounds (target_country_iso, total_export_value_str)
                    VALUES ($1, $2)
                    RETURNING *
                """, target_iso, total_val_str)
                
                return TradleRound(
                    id=row["id"],
                    target_country_iso=row["target_country_iso"],
                    started_at=row["started_at"],
                    total_export_value_str=row["total_export_value_str"]
                )

    async def get_player_session(self, user_id: int, round_id: int) -> PlayerSession:
        """Get or create a player session for a round."""
        if not self.pool: await self.connect()
        row = await self.pool.fetchrow(
            "SELECT * FROM tradle_guesses WHERE user_id = $1 AND round_id = $2",
            user_id, round_id
        )
        if row:
            guesses_data = json.loads(row["guesses_json"])
            guesses = [GuessEntry(**g) for g in guesses_data]
            return PlayerSession(
                user_id=user_id,
                round_id=round_id,
                guesses=guesses,
                won=row["won"],
                game_over=True if (row["won"] or len(guesses) >= 6) else False,
                completed_at=row["completed_at"]
            )
        return PlayerSession(user_id=user_id, round_id=round_id)

    async def save_player_session(self, session: PlayerSession):
        """Persist player session to DB."""
        if not self.pool: await self.connect()
        guesses_json = json.dumps([g.__dict__ for g in session.guesses])
        score = len(session.guesses) if session.won else 0
        
        await self.pool.execute("""
            INSERT INTO tradle_guesses (user_id, round_id, guesses_json, won, score, completed_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, round_id)
            DO UPDATE SET 
                guesses_json = EXCLUDED.guesses_json,
                won = EXCLUDED.won,
                score = EXCLUDED.score,
                completed_at = EXCLUDED.completed_at
        """, session.user_id, session.round_id, guesses_json, session.won, score, session.completed_at or datetime.now())

        if session.game_over:
            await self.update_stats(session.user_id, session.won, score)

    async def update_stats(self, user_id: int, won: bool, score: int):
        """Update long-term stats for a user."""
        if not self.pool: await self.connect()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Get current stats
                stats = await conn.fetchrow("SELECT * FROM tradle_stats WHERE user_id = $1", user_id)
                if not stats:
                    await conn.execute("""
                        INSERT INTO tradle_stats (user_id, total_played, total_won, current_streak, best_streak, total_score)
                        VALUES ($1, 1, $2, $3, $3, $4)
                    """, user_id, 1 if won else 0, 1 if won else 0, score)
                else:
                    new_played = stats["total_played"] + 1
                    new_won = stats["total_won"] + (1 if won else 0)
                    new_streak = (stats["current_streak"] + 1) if won else 0
                    best_streak = max(stats["best_streak"], new_streak)
                    new_total_score = stats["total_score"] + score
                    
                    await conn.execute("""
                        UPDATE tradle_stats SET
                            total_played = $2, total_won = $3,
                            current_streak = $4, best_streak = $5,
                            total_score = $6
                        WHERE user_id = $1
                    """, user_id, new_played, new_won, new_streak, best_streak, new_total_score)

    async def is_guild_active(self, guild_id: int) -> bool:
        """Check if a guild has opted-in to Tradle."""
        if not self.pool: await self.connect()
        row = await self.pool.fetchrow("SELECT is_active FROM tradle_config WHERE guild_id = $1", guild_id)
        return row["is_active"] if row else False

    async def set_guild_config(self, guild_id: int, channel_id: int, is_active: bool = True):
        """Set guild configuration."""
        if not self.pool: await self.connect()
        await self.pool.execute("""
            INSERT INTO tradle_config (guild_id, channel_id, is_active)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE SET
                channel_id = EXCLUDED.channel_id,
                is_active = EXCLUDED.is_active
        """, guild_id, channel_id, is_active)

    async def get_active_guilds(self) -> List[Dict[str, Any]]:
        """Get all guilds with active auto-posting."""
        if not self.pool: await self.connect()
        return await self.pool.fetch("SELECT * FROM tradle_config WHERE is_active = TRUE")

    async def get_round_results(self, round_id: int) -> List[Dict[str, Any]]:
        """Get results for a specific round to generate the summary."""
        if not self.pool: await self.connect()
        return await self.pool.fetch("""
            SELECT user_id, won, score, guesses_json, completed_at
            FROM tradle_guesses 
            WHERE round_id = $1 
            ORDER BY won DESC, score ASC, completed_at ASC
        """, round_id)

    async def get_live_post(self, round_id: int, user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        """Fetch stored public live-post message mapping for a player/round/guild."""
        if not self.pool: await self.connect()
        row = await self.pool.fetchrow("""
            SELECT round_id, user_id, guild_id, channel_id, message_id, created_at, updated_at
            FROM tradle_live_posts
            WHERE round_id = $1 AND user_id = $2 AND guild_id = $3
        """, round_id, user_id, guild_id)
        return dict(row) if row else None

    async def upsert_live_post(
        self,
        round_id: int,
        user_id: int,
        guild_id: int,
        channel_id: int,
        message_id: int,
    ) -> None:
        """Insert or update the public live-post mapping."""
        if not self.pool: await self.connect()
        await self.pool.execute("""
            INSERT INTO tradle_live_posts (round_id, user_id, guild_id, channel_id, message_id, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (round_id, user_id, guild_id)
            DO UPDATE SET
                channel_id = EXCLUDED.channel_id,
                message_id = EXCLUDED.message_id,
                updated_at = NOW()
        """, round_id, user_id, guild_id, channel_id, message_id)
