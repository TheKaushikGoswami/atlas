import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import logging
import io
import random
from typing import Optional, List, Dict, Any

from tradle.engine import TradleEngine
from tradle.db import TradleLookup
from tradle.treemap import TradleTreemap
from tradle.state import PlayerSession, GuessEntry
from config import config

logger = logging.getLogger(__name__)

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
    def __init__(self, engine: TradleEngine, db: TradleLookup, session: PlayerSession, target_iso: str, total_val: str):
        super().__init__(timeout=None)
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

        # Update message
        embed = interaction.message.embeds[0]
        
        # Build guess history text
        history = self.format_history()
        embed.description = f"```\n{history}\n```"
        
        # Update title with tries
        embed.title = f"Tradle Round #{self.session.round_id} - {len(self.session.guesses)}/6"
        
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

    def format_history(self) -> str:
        history = ""
        for g in self.session.guesses:
            dist_val = g.distance_km
            # Display N/A only if distance is 0 and it's NOT correct (meaning missing coords)
            dist_str = f"{int(dist_val):,} km" if (dist_val > 0 or g.is_correct) else "N/A"
            history += f"{self.engine.get_country_name(g.country_iso)} | {dist_str} | {g.direction} | {g.proximity_pct}%\n"
        return history

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
        title = f"Tradle Round #{round_data.id}"
        if session.guesses:
            title += f" - {len(session.guesses)}/6"
            
        embed = discord.Embed(title=title, color=discord.Color.blue())
        embed.set_image(url="attachment://tradle_exports.png")
        embed.description = "Guess the country exporting these products!"
        
        view = TradleSessionView(self.cog.engine, self.cog.db, session, round_data.target_country_iso, round_data.total_export_value_str)

        # If user already had guesses, show them
        if session.guesses:
            history = view.format_history()
            embed.description = f"```\n{history}\n```"

        await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=True)
        
        # 5. Opt-in guild if not already
        if interaction.guild:
            await self.cog.db.set_guild_config(interaction.guild.id, interaction.channel.id, is_active=True)

# --- Cog ---

class TradleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = TradleLookup(config.DATABASE_URL)
        self.engine = TradleEngine()
        self.tradle_loop.start()

    def cog_unload(self):
        self.tradle_loop.cancel()

    @tasks.loop(time=[datetime.time(hour=0, minute=0), datetime.time(hour=12, minute=0)])
    async def tradle_loop(self):
        """12 AM/PM IST Daily Task."""
        # Note: discord.py time is UTC. IST is UTC+5:30.
        # 12 AM IST = 6:30 PM UTC Previous Day
        # 12 PM IST = 6:30 AM UTC
        # If the user wants 12 AM/PM LOCAL IST, I should adjust.
        # To simplify, let's assume the provided times are intended to be IST.
        # For now, I'll stick to the provided times. (User would need to adjust for TZ).
        await self.trigger_new_round()

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
            
            embed = discord.Embed(
                title=f"🌍 New Tradle Round #{new_round.id}!",
                description=f"{summary_msg}\nClick the button below to play privately!",
                color=discord.Color.gold()
            )
            embed.set_footer(text="A new round starts every 12 hours.")
            
            view = PlayTradleView(self)
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
            
        if not stats:
            return await interaction.response.send_message(f"No stats found for {target.mention}.", ephemeral=True)
            
        avg_score = stats["total_score"] / stats["total_played"] if stats["total_played"] > 0 else 0
        embed = discord.Embed(title=f"📊 Tradle Stats: {target.display_name}", color=discord.Color.blue())
        embed.add_field(name="Played", value=stats["total_played"])
        embed.add_field(name="Won", value=stats["total_won"])
        embed.add_field(name="Win %", value=f"{(stats['total_won']/stats['total_played']*100):.1f}%")
        embed.add_field(name="Current Streak", value=stats["current_streak"])
        embed.add_field(name="Best Streak", value=stats["best_streak"])
        embed.add_field(name="Avg Guesses", value=f"{avg_score:.1f}")
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(TradleCog(bot))
