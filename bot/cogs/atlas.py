import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands
from typing import Dict, Optional

from game.lobby import Lobby
from game.state import GameState
from game.engine import GameEngine, AnswerStatus, Result

logger = logging.getLogger(__name__)

class LocationSuggestionView(discord.ui.View):
    def __init__(self, location: str):
        super().__init__(timeout=60)
        self.location = location

    @discord.ui.button(label="Request to Add Location", style=discord.ButtonStyle.secondary, emoji="📍")
    async def suggest(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(f"User {interaction.user.name} suggested adding: {self.location}")
        
        from config import config
        import json
        import datetime
        
        # Ensure data dir exists
        config.DATA_DIR.mkdir(exist_ok=True)
        
        suggestion = {
            "location": self.location,
            "suggested_by": f"{interaction.user.name}#{interaction.user.discriminator}",
            "user_id": interaction.user.id,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        suggestions = []
        if config.SUGGESTIONS_FILE.exists():
            try:
                with open(config.SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
                    suggestions = json.load(f)
            except Exception as e:
                logger.error(f"Error reading suggestions file: {e}")
        
        # Avoid duplicate suggestions for the same location
        if not any(s["location"].lower() == self.location.lower() for s in suggestions):
            suggestions.append(suggestion)
            try:
                with open(config.SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
                    json.dump(suggestions, f, indent=4)
            except Exception as e:
                logger.error(f"Error writing suggestions file: {e}")
        
        await interaction.response.send_message(
            f"✅ Thanks! Your request to add '**{self.location}**' has been saved to the review queue.",
            ephemeral=True
        )
        button.disabled = True
        await interaction.edit_original_response(view=self)

    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 Pong! Latency: **{latency}ms**")

class AtlasCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # channel_id -> Lobby
        self.lobbies: Dict[int, Lobby] = {}
        # channel_id -> GameEngine
        self.engines: Dict[int, GameEngine] = {}
        # channel_id -> asyncio.Task (Timer)
        self.timers: Dict[int, asyncio.Task] = {}
        
        self.config = getattr(bot, "config", None) # fallback if not injected
        self.turn_timeout = 30 # Default

    def get_timeout(self):
        from config import config
        return config.TURN_TIMEOUT

    # --- Slash Commands ---

    @app_commands.command(name="join", description="Join the Atlas game lobby in this channel.")
    async def join(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        
        if channel_id in self.engines:
            await interaction.response.send_message("❌ A game is already in progress in this channel.", ephemeral=True)
            return
        
        if channel_id not in self.lobbies:
            self.lobbies[channel_id] = Lobby(channel_id, interaction.user.id)
            
        lobby = self.lobbies[channel_id]
        success, message = lobby.join(interaction.user.id, interaction.user.display_name)
        await interaction.response.send_message(message)

    @app_commands.command(name="start", description="Start the Atlas game with the current lobby.")
    async def start(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        
        if channel_id in self.engines:
            await interaction.response.send_message("❌ A game is already in progress.", ephemeral=True)
            return
            
        if channel_id not in self.lobbies:
            await interaction.response.send_message("❌ No lobby found. Use `/join` first.", ephemeral=True)
            return
            
        lobby = self.lobbies[channel_id]
        players, message = lobby.lock()
        
        if not players:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return
            
        # Initialise game
        state = GameState(players=players, started=True)
        engine = GameEngine(state, self.bot.geo_lookup)
        self.engines[channel_id] = engine
        
        # Clean up lobby
        del self.lobbies[channel_id]
        
        # Initial embed
        embed = discord.Embed(
            title="🌍 Atlas Round-Robin Started!",
            description=f"Players: {', '.join([p.name for p in players])}\n\n**Turn Order:** " + " ➔ ".join([p.name for p in players]),
            color=discord.Color.blue()
        )
        embed.add_field(name="Current Player", value=f"{players[0].name}", inline=False)
        embed.add_field(name="Rule", value="First player can start with **any** geographical place!", inline=False)
        
        await interaction.response.send_message(content=f"🔔 <@{players[0].id}>, you start!", embed=embed)
        
        # Start timer
        self._start_timer(channel_id)

    @app_commands.command(name="stop", description="Stop the current game (Admin/Creator only).")
    async def stop(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        
        if channel_id not in self.engines and channel_id not in self.lobbies:
            await interaction.response.send_message("❌ No game or lobby active in this channel.", ephemeral=True)
            return
            
        # Permission check: Creator or Manage Messages
        is_creator = False
        if channel_id in self.lobbies:
            is_creator = interaction.user.id == self.lobbies[channel_id].creator_id
        
        can_manage = interaction.user.guild_permissions.manage_messages
        
        if not (is_creator or can_manage):
            await interaction.response.send_message("❌ Only the game creator or admins can stop the game.", ephemeral=True)
            return
            
        self._cleanup_game(channel_id)
        await interaction.response.send_message("🛑 Game has been stopped and cleared.")

    @app_commands.command(name="leave", description="Leave the current game or lobby.")
    async def leave(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        user_id = interaction.user.id
        
        # 1. Handle Lobby
        if channel_id in self.lobbies:
            success, message = self.lobbies[channel_id].leave(user_id)
            await interaction.response.send_message(message, ephemeral=not success)
            return
            
        # 2. Handle Active Game
        if channel_id in self.engines:
            engine = self.engines[channel_id]
            player_name = interaction.user.display_name
            success, winner = engine.leave_game(user_id)
            
            if not success:
                await interaction.response.send_message("❌ You are not an active player in this game.", ephemeral=True)
                return
            
            await interaction.response.send_message(f"🚪 **{player_name}** has left the game and been eliminated.")
            
            if winner:
                embed = discord.Embed(
                    title="🏆 GAME OVER!",
                    description=f"Everyone else left! Congratulations **{winner.name}**, you won by default!",
                    color=discord.Color.gold()
                )
                await interaction.followup.send(embed=embed)
                self._cleanup_game(channel_id)
            else:
                # If it was their turn, notify the next player
                next_player = engine.state.current_player
                letter_hint = engine.state.current_letter.upper() if engine.state.current_letter else "ANY"
                await interaction.followup.send(f"🔤 <@{next_player.id}>, turn passes to you! Letter is **{letter_hint}**.")
                self._start_timer(channel_id)
            return

        await interaction.response.send_message("❌ No active game or lobby in this channel.", ephemeral=True)

    @app_commands.command(name="status", description="Show the current game status.")
    async def status(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        if channel_id not in self.engines:
            await interaction.response.send_message("❌ No active game in this channel.", ephemeral=True)
            return
            
        engine = self.engines[channel_id]
        state = engine.state
        
        embed = discord.Embed(title="🌍 Atlas Game Status", color=discord.Color.blue())
        embed.add_field(name="Current Turn", value=f"{state.current_player.name}", inline=True)
        embed.add_field(name="Required Letter", value=f"**{state.current_letter.upper() if state.current_letter else 'ANY'}**", inline=True)
        
        scoreboard = "\n".join([f"{p.name}: {'❌' * p.strikes}{'✅' * (self.bot.config.MAX_STRIKES - p.strikes)}" for p in state.players])
        embed.add_field(name="Scoreboard (Strikes)", value=scoreboard, inline=False)
        embed.add_field(name="Words Used", value=str(len(state.used_words)), inline=True)
        
        await interaction.response.send_message(embed=embed)

    # --- Message Listener ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
            
        channel_id = message.channel.id
        if channel_id not in self.engines:
            return
            
        engine = self.engines[channel_id]
        state = engine.state
        
        # Only listen to current player
        if message.author.id != state.current_player.id:
            return
            
        # Stop existing timer
        self._cancel_timer(channel_id)
        
        # Process answer
        result: Result = await engine.submit_answer(message.content)
        
        if result.status == AnswerStatus.VALID:
            await self._handle_valid(message, result)
        else:
            await self._handle_strike(message, result)

    # --- Helper Handlers ---

    async def _handle_valid(self, message, result: Result):
        embed = discord.Embed(
            title="✅ Valid Answer!",
            description=f"**{message.author.display_name}** said **{message.content.strip()}**.",
            color=discord.Color.green()
        )
        
        if result.winner:
            embed.title = "🏆 WINNER!"
            embed.description += f"\n\nCongratulations **{result.winner.name}**, you won the game!"
            embed.color = discord.Color.gold()
            await message.channel.send(embed=embed)
            self._cleanup_game(message.channel.id)
            return

        next_player = self.engines[message.channel.id].state.current_player
        embed.add_field(name="Next Turn", value=f"**{next_player.name}**", inline=False)
        embed.set_footer(text=f"Letter: {result.next_letter.upper()}")
        
        await message.channel.send(embed=embed)
        await message.channel.send(f"🔤 <@{next_player.id}>, your turn! Name a geographical place starting with **{result.next_letter.upper()}**!")
        
        self._start_timer(message.channel.id)

    async def _handle_strike(self, message, result: Result):
        color = discord.Color.red() if result.eliminated else discord.Color.orange()
        title = "❌ ELIMINATED!" if result.eliminated else "⚠️ STRIKE!"
        
        embed = discord.Embed(title=title, description=result.message, color=color)
        embed.add_field(name="Player", value=message.author.display_name, inline=True)
        embed.add_field(name="Strikes", value=f"{result.player.strikes}/{self.bot.config.MAX_STRIKES}", inline=True)
        
        if result.winner:
            embed.title = "🏆 GAME OVER!"
            embed.description += f"\n\nCongratulations **{result.winner.name}**, you won by default!"
            embed.color = discord.Color.gold()
            await message.channel.send(embed=embed)
            self._cleanup_game(message.channel.id)
            return

        next_player = self.engines[message.channel.id].state.current_player
        letter_hint = result.next_letter.upper() if result.next_letter else "ANY"
        embed.set_footer(text=f"Same-letter rule applies. Next up: {next_player.name} | Letter: {letter_hint}")
        
        view = None
        if result.status == AnswerStatus.INVALID_WORD:
            # Add the "Request to Add Location" button
            view = LocationSuggestionView(message.content.strip())

        await message.channel.send(embed=embed, view=view)
        await message.channel.send(f"🔤 <@{next_player.id}>, turn passes to you! Still waiting for a place starting with **{letter_hint}**!")
        
        self._start_timer(message.channel.id)

    # --- Timer Logic ---

    def _start_timer(self, channel_id: int):
        self._cancel_timer(channel_id)
        self.timers[channel_id] = asyncio.create_task(self._timer_task(channel_id))

    def _cancel_timer(self, channel_id: int):
        if channel_id in self.timers:
            self.timers[channel_id].cancel()
            del self.timers[channel_id]

    async def _timer_task(self, channel_id: int):
        try:
            timeout = self.get_timeout()
            await asyncio.sleep(timeout)
            
            # If we reach here, time is up
            if channel_id in self.engines:
                engine = self.engines[channel_id]
                res = await engine.handle_timeout()
                
                channel = self.bot.get_channel(channel_id)
                if channel:
                    color = discord.Color.red() if res.eliminated else discord.Color.orange()
                    title = "⏰ TIME'S UP!"
                    if res.eliminated: title = "⏰ ELIMINATED ON TIMEOUT!"
                    
                    embed = discord.Embed(title=title, description=f"**{res.player.name}** failed to answer in time.", color=color)
                    embed.add_field(name="Strikes", value=f"{res.strikes}/{self.bot.config.MAX_STRIKES}")
                    
                    if res.winner:
                        embed.title = "🏆 WINNER!"
                        embed.description += f"\n\nCongratulations **{res.winner.name}**, you won by default!"
                        await channel.send(embed=embed)
                        self._cleanup_game(channel_id)
                        return
                        
                    next_player = engine.state.current_player
                    letter_hint = res.next_letter.upper() if res.next_letter else "ANY"
                    await channel.send(embed=embed)
                    await channel.send(f"🔤 <@{next_player.id}>, your turn! Letter is still **{letter_hint}**.")
                    
                    self._start_timer(channel_id)
        except asyncio.CancelledError:
            pass

    def _cleanup_game(self, channel_id: int):
        self._cancel_timer(channel_id)
        if channel_id in self.engines: del self.engines[channel_id]
        if channel_id in self.lobbies: del self.lobbies[channel_id]

async def setup(bot):
    await bot.add_cog(AtlasCog(bot))
