import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import logging
import random
import json
from typing import Optional, List, Dict, Any

from tradle.engine import TradleEngine
from tradle.db import TradleLookup
from tradle.treemap import TradleTreemap
from tradle.cards import TradleCardRenderer
from tradle.state import PlayerSession, GuessEntry
from config import config

logger = logging.getLogger(__name__)
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# --- UI Components ---

class GuessModal(discord.ui.Modal, title="🌍 Submit your Tradle guess"):
    country_name = discord.ui.TextInput(
        label="Country Name",
        placeholder="e.g. France, United States, Japan...",
        min_length=2,
        max_length=50,
        required=True
    )

    def __init__(self, parent_view: 'TradleSessionView'):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        await self.parent_view.handle_guess(interaction, self.country_name.value)

class TradleSessionView(discord.ui.View):
    """The ephemeral view for a single player's game session."""
    def __init__(
        self,
        cog: 'TradleCog',
        engine: TradleEngine,
        db: TradleLookup,
        session: PlayerSession,
        target_iso: str,
        total_val: str,
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.engine = engine
        self.db = db
        self.session = session
        self.target_iso = target_iso
        self.total_val = total_val

    @discord.ui.button(label="🌍 Guess", style=discord.ButtonStyle.primary)
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.game_over:
            return await interaction.response.send_message("This game is already over!", ephemeral=True)
        await interaction.response.send_modal(GuessModal(self))

    @discord.ui.button(label="🏳️ Give Up", style=discord.ButtonStyle.secondary)
    async def give_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.game_over:
            return await interaction.response.send_message("This game is already over!", ephemeral=True)
        
        self.session.game_over = True
        self.session.won = False
        self.session.completed_at = datetime.datetime.now()
        await self.db.save_player_session(self.session)
        await self.cog.update_live_progress_message(interaction, self.session, final_state="gave up")
        
        target_name = self.engine.get_country_name(self.target_iso)
        await interaction.response.edit_message(
            content=f"You gave up! The answer was **{target_name}**. Better luck next time!",
            view=None
        )

    async def handle_guess(self, interaction: discord.Interaction, country_name: str):
        result = self.engine.process_guess(self.session, self.target_iso, country_name)
        if not result:
            return await interaction.response.send_message(f"Could not find country: **{country_name}**. Please try again.", ephemeral=True)

        # Save session
        await self.db.save_player_session(self.session)
        final_state = None
        if self.session.won:
            final_state = "solved"
        elif self.session.game_over:
            final_state = "game over"
        await self.cog.update_live_progress_message(interaction, self.session, final_state=final_state)

        # Update message
        embed = interaction.message.embeds[0]
        
        # Build guess history text
        history = ""
        for g in self.session.guesses:
            history += f"{self.engine.get_country_name(g.country_iso)} | {int(g.distance_km):,} km | {g.direction} | {g.proximity_pct}%\n"
        
        embed.description = f"```\n{history}\n```"
        
        if self.session.won:
            embed.color = discord.Color.green()
            content = f"🎉 **CONGRATULATIONS!** You guessed it in {len(self.session.guesses)}/6!\n\n**Share Pattern:**\n{result.share_text}"
            self.clear_items()
            await interaction.response.edit_message(content=content, embed=embed, view=None)
        elif self.session.game_over:
            embed.color = discord.Color.red()
            target_name = self.engine.get_country_name(self.target_iso)
            content = f"❌ **Game Over!** You ran out of guesses. The answer was **{target_name}**."
            self.clear_items()
            await interaction.response.edit_message(content=content, embed=embed, view=None)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

class PlayTradleView(discord.ui.View):
    """The public persistent view with the 'Play Tradle!' button."""
    def __init__(self, cog: 'TradleCog'):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="🌍 Play Tradle!", style=discord.ButtonStyle.success, custom_id="play_tradle_btn")
    async def play_tradle(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Get active round
        round_data = await self.cog.db.get_active_round()
        if not round_data:
            return await interaction.response.send_message("No Tradle round is currently active. Please wait for the next trigger!", ephemeral=True)

        # 2. Get player session
        session = await self.cog.db.get_player_session(interaction.user.id, round_data.id)
        if session.game_over:
            target_name = self.cog.engine.get_country_name(round_data.target_country_iso)
            if session.won:
                return await interaction.response.send_message(f"You've already won this Tradle! The answer was **{target_name}**.", ephemeral=True)
            else:
                return await interaction.response.send_message(f"You've already finished this Tradle. The answer was **{target_name}**.", ephemeral=True)

        # 3. Generate treemap
        trade_info = self.cog.engine.trade_data.get(round_data.target_country_iso)
        if not trade_info:
            return await interaction.response.send_message("Error loading trade data for this round.", ephemeral=True)

        img_buf = TradleTreemap.generate(trade_info["exports"], round_data.total_export_value_str)
        file = discord.File(img_buf, filename="tradle_exports.png")

        # 4. Send ephemeral game view
        embed = discord.Embed(title=f"Tradle Round #{round_data.id}", color=discord.Color.blue())
        embed.set_image(url="attachment://tradle_exports.png")
        embed.description = "Guess the country exporting these products!"
        
        # If user already had guesses, show them
        if session.guesses:
            history = ""
            for g in session.guesses:
                history += f"{self.cog.engine.get_country_name(g.country_iso)} | {int(g.distance_km):,} km | {g.direction} | {g.proximity_pct}%\n"
            embed.description = f"```\n{history}\n```"

        view = TradleSessionView(self.cog, self.cog.engine, self.cog.db, session, round_data.target_country_iso, round_data.total_export_value_str)
        await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=True)
        
        # 5. Opt-in guild if not already
        if interaction.guild:
            await self.cog.db.set_guild_config(interaction.guild.id, interaction.channel.id, is_active=True)
            await self.cog.ensure_live_progress_message(interaction, session)

# --- Cog ---

class TradleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = TradleLookup(config.DATABASE_URL)
        self.engine = TradleEngine()
        self.tradle_loop.start()

    def cog_unload(self):
        self.tradle_loop.cancel()

    @tasks.loop(hours=8.0)
    async def tradle_loop(self):
        """Run a new Tradle round every 8 hours at 00:00, 08:00, 16:00 IST."""
        await self.trigger_new_round()

    @staticmethod
    def _parse_guesses_field(raw: Any) -> List[Dict[str, Any]]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                decoded = json.loads(raw)
                if isinstance(decoded, list):
                    return decoded
            except json.JSONDecodeError:
                return []
        return []

    async def _fetch_avatar_bytes(self, user: discord.abc.User) -> Optional[bytes]:
        try:
            return await user.display_avatar.read()
        except Exception:
            return None

    async def _build_round_card_file(
        self,
        channel: discord.abc.Messageable,
        new_round_id: int,
        old_round_id: Optional[int],
        results: List[Dict[str, Any]],
    ) -> Optional[discord.File]:
        try:
            players = []
            guild = getattr(channel, "guild", None)
            for row in results[:5]:
                data = dict(row)
                user_id = int(data["user_id"])
                guesses = self._parse_guesses_field(data.get("guesses_json"))
                score = data.get("score")
                name = f"<@{user_id}>"
                avatar_bytes = None

                member = guild.get_member(user_id) if guild else None
                if member:
                    name = member.display_name
                    avatar_bytes = await self._fetch_avatar_bytes(member)
                else:
                    try:
                        user = await self.bot.fetch_user(user_id)
                        name = user.display_name
                        avatar_bytes = await self._fetch_avatar_bytes(user)
                    except Exception:
                        pass

                players.append({
                    "name": name,
                    "score": score,
                    "guesses": guesses,
                    "avatar_bytes": avatar_bytes,
                })

            card = TradleCardRenderer.render_round_announcement(
                new_round_id=new_round_id,
                previous_round_id=old_round_id,
                players=players,
            )
            return discord.File(card, filename="tradle_round_card.png")
        except Exception:
            logger.exception("Failed to render round announcement card.")
            return None

    async def ensure_live_progress_message(self, interaction: discord.Interaction, session: PlayerSession) -> None:
        """Create or refresh a public live-progress post for this player's current round."""
        if not interaction.guild or not interaction.channel:
            return

        status = f"{interaction.user.display_name} is playing Tradle #{session.round_id}"
        try:
            await self._upsert_live_progress_message(
                guild=interaction.guild,
                channel=interaction.channel,
                user=interaction.user,
                session=session,
                status=status,
            )
        except Exception:
            logger.exception("Unable to create live progress message.")

    async def update_live_progress_message(
        self,
        interaction: discord.Interaction,
        session: PlayerSession,
        final_state: Optional[str] = None,
    ) -> None:
        """Update public live-progress post after each guess or completion."""
        if not interaction.guild:
            return

        if final_state == "solved":
            status = f"{interaction.user.display_name} solved Tradle #{session.round_id} in {len(session.guesses)}/6"
        elif final_state == "gave up":
            status = f"{interaction.user.display_name} gave up on Tradle #{session.round_id}"
        elif final_state == "game over":
            status = f"{interaction.user.display_name} finished Tradle #{session.round_id} (game over)"
        else:
            status = f"{interaction.user.display_name} is playing Tradle #{session.round_id}"

        channel = interaction.channel
        if not channel:
            live = await self.db.get_live_post(session.round_id, interaction.user.id, interaction.guild.id)
            if live:
                channel = self.bot.get_channel(int(live["channel_id"]))
        if not channel:
            return

        try:
            await self._upsert_live_progress_message(
                guild=interaction.guild,
                channel=channel,
                user=interaction.user,
                session=session,
                status=status,
            )
        except Exception:
            logger.exception("Unable to update live progress message.")

    async def _upsert_live_progress_message(
        self,
        *,
        guild: discord.Guild,
        channel: discord.abc.Messageable,
        user: discord.abc.User,
        session: PlayerSession,
        status: str,
    ) -> None:
        try:
            avatar_bytes = await self._fetch_avatar_bytes(user)
            img = TradleCardRenderer.render_live_progress(
                round_id=session.round_id,
                player_name=user.display_name,
                guesses=session.guesses,
                status_text=status,
                avatar_bytes=avatar_bytes,
            )
            file = discord.File(img, filename="tradle_live.png")
        except Exception:
            logger.exception("Failed to render live progress image.")
            file = None

        content = f"{user.mention} {status}"
        existing = await self.db.get_live_post(session.round_id, user.id, guild.id)
        target_channel = channel
        if existing:
            maybe_channel = self.bot.get_channel(int(existing["channel_id"]))
            if maybe_channel:
                target_channel = maybe_channel
            try:
                msg = await target_channel.fetch_message(int(existing["message_id"]))
                if file:
                    await msg.edit(content=content, attachments=[file])
                else:
                    await msg.edit(content=content)
                return
            except Exception:
                logger.warning("Stored live progress message not found; creating a new one.")

        if file:
            msg = await target_channel.send(content=content, file=file)
        else:
            msg = await target_channel.send(content=content)

        await self.db.upsert_live_post(
            round_id=session.round_id,
            user_id=user.id,
            guild_id=guild.id,
            channel_id=target_channel.id,
            message_id=msg.id,
        )

    async def trigger_new_round(self):
        logger.info("Triggering new Tradle round...")
        
        # 1. Pick new country
        valid_isos = list(self.engine.trade_data.keys())
        # Filter for "interesting" countries (e.g. total trade > 1B)
        target_iso = random.choice(valid_isos)
        trade_info = self.engine.trade_data[target_iso]
        
        # 2. End previous round and start new one
        old_round = await self.db.get_active_round()
        new_round = await self.db.start_new_round(target_iso, trade_info["total"])
        
        # 3. Post summary/new round in all active guilds
        active_guilds = await self.db.get_active_guilds()
        for guild_cfg in active_guilds:
            channel = self.bot.get_channel(guild_cfg["channel_id"])
            if not channel: continue
            
            # Summary of previous round
            summary_msg = ""
            results = []
            if old_round:
                results = await self.db.get_round_results(old_round.id)
                if results:
                    summary_msg = f"**Tradle #{old_round.id} Results:**\n"
                    # Sort results and show top 3
                    for i, r in enumerate(results[:3]):
                        crown = "👑 " if i == 0 else ""
                        summary_msg += f"{crown}{r['score']}/6: <@{r['user_id']}>\n"
                else:
                    summary_msg = "No one guessed yesterday's Tradle."
            
            card_file = await self._build_round_card_file(
                channel=channel,
                new_round_id=new_round.id,
                old_round_id=old_round.id if old_round else None,
                results=results,
            )

            description = "Click the button below to play privately!"
            if not card_file and summary_msg:
                description = f"{summary_msg}\n{description}"

            embed = discord.Embed(
                title=f"🌍 New Tradle Round #{new_round.id}!",
                description=description,
                color=discord.Color.gold()
            )
            embed.set_footer(text="A new round starts every 8 hours.")
            if card_file:
                embed.set_image(url="attachment://tradle_round_card.png")
            
            view = PlayTradleView(self)
            if card_file:
                await channel.send(embed=embed, file=card_file, view=view)
            else:
                await channel.send(embed=embed, view=view)

    @app_commands.command(name="tradle", description="Start or view today's Tradle game.")
    async def tradle_cmd(self, interaction: discord.Interaction):
        """Manual trigger - also opts-in the server."""
        active_round = await self.db.get_active_round()
        if not active_round:
            # If no round exists, force start one
            valid_isos = list(self.engine.trade_data.keys())
            target_iso = random.choice(valid_isos)
            trade_info = self.engine.trade_data[target_iso]
            active_round = await self.db.start_new_round(target_iso, trade_info["total"])

        embed = discord.Embed(
            title=f"🌍 Tradle Round #{active_round.id}",
            description="Click the button below to play privately!",
            color=discord.Color.gold()
        )
        view = PlayTradleView(self)
        await interaction.response.send_message(embed=embed, view=view)
        
        if interaction.guild:
            await self.db.set_guild_config(interaction.guild.id, interaction.channel.id, is_active=True)

    @app_commands.command(name="tradlestats", description="Show your personal Tradle stats.")
    async def tradlestats_cmd(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        await self.db.connect()
        async with self.db.pool.acquire() as conn:
            stats = await conn.fetchrow("SELECT * FROM tradle_stats WHERE user_id = $1", target.id)
            totals = await conn.fetchrow("""
                SELECT
                    COUNT(*) AS sessions,
                    COUNT(*) FILTER (WHERE won = TRUE) AS wins,
                    COUNT(*) FILTER (WHERE won = FALSE) AS losses,
                    MIN(completed_at) AS first_played,
                    MAX(completed_at) AS last_played
                FROM tradle_guesses
                WHERE user_id = $1
            """, target.id)
            rank_row = await conn.fetchrow("""
                SELECT rank FROM (
                    SELECT user_id,
                           DENSE_RANK() OVER (ORDER BY total_won DESC, total_score ASC, best_streak DESC) AS rank
                    FROM tradle_stats
                ) ranked
                WHERE user_id = $1
            """, target.id)
            
        if not stats:
            return await interaction.response.send_message(f"No stats found for {target.mention}.", ephemeral=True)

        played = int(stats["total_played"] or 0)
        won = int(stats["total_won"] or 0)
        lost = max(played - won, 0)
        win_pct = (won / played * 100) if played > 0 else 0.0
        avg_guesses_for_wins = (stats["total_score"] / won) if won > 0 else 0.0

        sessions = int(totals["sessions"] or 0) if totals else 0
        first_played = totals["first_played"].astimezone(IST) if totals and totals["first_played"] else None
        last_played = totals["last_played"].astimezone(IST) if totals and totals["last_played"] else None
        rank = rank_row["rank"] if rank_row else None

        embed = discord.Embed(title=f"📊 Tradle Stats: {target.display_name}", color=discord.Color.blue())
        embed.add_field(name="Games", value=f"Played: **{played}**\nWon: **{won}**\nLost: **{lost}**", inline=True)
        embed.add_field(name="Performance", value=f"Win Rate: **{win_pct:.1f}%**\nAvg Guesses (wins): **{avg_guesses_for_wins:.2f}**", inline=True)
        embed.add_field(name="Streaks", value=f"Current: **{stats['current_streak']}**\nBest: **{stats['best_streak']}**", inline=True)
        embed.add_field(name="Global Rank", value=f"#{rank}" if rank else "Unranked", inline=True)
        embed.add_field(name="Recorded Sessions", value=str(sessions), inline=True)
        embed.add_field(
            name="Activity",
            value=(
                f"First: **{first_played.strftime('%Y-%m-%d %H:%M')}**\n"
                f"Last: **{last_played.strftime('%Y-%m-%d %H:%M')}**"
                if first_played and last_played else "Not enough history"
            ),
            inline=False
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Tip: Use /tradle daily to keep your streak alive.")
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="tradleforce", description="Force start a new Tradle round (Restricted).")
    async def tradleforce_cmd(self, interaction: discord.Interaction):
        """Force start a new round and reset the 8-hour timer. Only for authorized user."""
        if interaction.user.id != 1384163020439158867:
            return await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        # Restarting the loop will stop it and then start it, which calls the function once immediately.
        self.tradle_loop.restart()
        await interaction.followup.send("✅ New Tradle round generated and timer reset to 8 hours from now.")

async def setup(bot):
    await bot.add_cog(TradleCog(bot))
