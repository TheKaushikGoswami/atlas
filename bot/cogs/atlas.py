import asyncio
import logging
import time
import discord
from discord import app_commands
from discord.ext import commands
from typing import Dict, Optional

from game.lobby import Lobby
from game.state import GameState
from game.engine import GameEngine, AnswerStatus, Result
from game.player import Player
from game.team import Team
from config import config

logger = logging.getLogger(__name__)

TARGET_USER_ID = 732183240831402005

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

class LeaderboardView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Reset Leaderboard", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to reset the leaderboard.", ephemeral=True)
            return

        await self.cog.bot.geo_lookup.reset_leaderboard(interaction.guild_id)
        
        embed = discord.Embed(
            title="📉 Leaderboard Reset",
            description=f"The leaderboard for **{interaction.guild.name}** has been cleared by {interaction.user.mention}.",
            color=discord.Color.red()
        )
        
        # Disable the button after use
        button.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)



class AtlasCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # channel_id -> Lobby
        self.lobbies: Dict[int, Lobby] = {}
        # channel_id -> GameEngine
        self.engines: Dict[int, GameEngine] = {}
        # channel_id -> asyncio.Task (Timer)
        self.timers: Dict[int, asyncio.Task] = {}
        # channel_id -> asyncio.Lock (for first-answer-only logic)
        self.answer_locks: Dict[int, asyncio.Lock] = {}

    @commands.command(name="sync")
    async def legacy_sync(self, ctx):
        """Legacy prefix command to sync slash commands."""
        if not ctx.author.guild_permissions.manage_messages:
            return
        synced = await self.bot.tree.sync()
        await ctx.send(f"✅ Synced {len(synced)} slash commands!")

    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping(self, interaction: discord.Interaction):
        ws_latency = round(self.bot.latency * 1000)
        start = time.perf_counter()
        await interaction.response.send_message("🏓 Pinging...")
        end = time.perf_counter()
        api_latency = round((end - start) * 1000)
        
        embed = discord.Embed(title="🏓 Pong!", color=discord.Color.blue())
        embed.add_field(name="🛰️ WebSocket", value=f"`{ws_latency}ms`", inline=True)
        embed.add_field(name="⚡ API", value=f"`{api_latency}ms`", inline=True)
        embed.set_footer(text="Lower API latency = closer VPS to Discord servers")
        await interaction.edit_original_response(content=None, embed=embed)

    @app_commands.command(name="help", description="Show information about the bot and commands.")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Atlas + Tradle Help",
            description=(
                "**Atlas:** a turn-based geography word game.\n"
                "Use `/join` -> `/start` and answer with valid place names.\n\n"
                "**Tradle:** guess the country from export patterns.\n"
                "Use `/tradle` to play and `/tradlestats` for profile stats."
            ),
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        
        embed.add_field(
            name="🎮 Atlas Commands",
            value=(
                "`/join [team]` - Join the lobby (Team is optional)\n"
                "`/start` - Start current lobby game\n"
                "`/leave` - Leave the game or lobby\n"
                "`/status` - Check game progress\n"
                "`/players` - See who's still in the game\n"
                "`/leaderboard` - See top players\n"
                "`/ping` - Check bot latency"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🌍 Tradle Commands",
            value=(
                "`/tradle` - Open the current Tradle round\n"
                "`/tradlestats [member]` - View Tradle performance stats\n"
                "A new Tradle round starts every 8 hours."
            ),
            inline=False
        )
        
        embed.add_field(
            name="🗂️ Place Management",
            value=(
                "`/searchplace <name>` - Search if a place exists (case-insensitive)\n"
                "`/addplace <name>` - Add a place (Admin)\n"
                "`/removeplace <name>` - Remove a wrong place (Admin, case-insensitive)\n"
                "`/sync` - Refresh slash commands (Admin)"
            ),
            inline=False
        )

        embed.add_field(
            name="🛠️ Admin Game Controls",
            value=(
                "`/stop` - Stop the current game (Admin/Creator)\n"
                "`/kick @user` - Kick a player (Admin)\n"
                "`/addplace <name>` - Add a place to the database (Admin)\n"
                "`/add @user [team]` - Add a player mid-game (Admin)"
            ),
            inline=False
        )
        
        embed.add_field(
            name="✨ About",
            value=(
                "• Developed by <@1384163020439158867>\n"
                "• Powered by a database of over 460,000 geographical locations."
            ),
            inline=False
        )
        
        embed.set_footer(text="Atlas v1.3 | Case-insensitive place tools enabled")
        await interaction.response.send_message(embed=embed)

    def get_timeout(self):
        return config.TURN_TIMEOUT

    # --- Slash Commands ---

    @app_commands.command(name="join", description="Join the Atlas game lobby in this channel.")
    @app_commands.describe(team="Optional: Specify a team to join for team mode (e.g. Red, Blue).")
    async def join(self, interaction: discord.Interaction, team: Optional[str] = None):
        channel_id = interaction.channel_id
        
        if channel_id in self.engines:
            await interaction.response.send_message("❌ A game is already in progress in this channel.", ephemeral=True)
            return
        
        if channel_id not in self.lobbies:
            self.lobbies[channel_id] = Lobby(channel_id, interaction.user.id)
            
        lobby = self.lobbies[channel_id]
        success, message = lobby.join(interaction.user.id, interaction.user.display_name, team_name=team)
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
        
        # Only lobby members can start the game
        if interaction.user.id not in lobby.players:
            await interaction.response.send_message("❌ You must join the lobby first before starting the game.", ephemeral=True)
            return
        
        players, team_data, message = lobby.lock()
        
        if not players:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return
            
        # Initialise game
        teams = None
        if team_data:
            teams = [Team(name=tname, players=pids) for tname, pids in team_data.items()]

        state = GameState(players=players, teams=teams, started=True)
        engine = GameEngine(state, self.bot.geo_lookup)
        self.engines[channel_id] = engine
        
        # Clean up lobby
        del self.lobbies[channel_id]
        
        # Initial embed
        if teams:
            team_str = "\n".join([f"**Team {t.name.capitalize()}:** {', '.join([p.name for p in t.players])}" for t in teams])
            embed = discord.Embed(
                title="⚔️ Team Atlas Started!",
                description=f"{team_str}\n\n**Turn Order:** {teams[0].name.capitalize()} ➔ {teams[1].name.capitalize()}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Current Team", value=f"{teams[0].name.capitalize()}", inline=False)
            embed.add_field(name="Current Player", value=f"{teams[0].current_player.name}", inline=True)
        else:
            embed = discord.Embed(
                title="🌍 Atlas Round-Robin Started!",
                description=f"Players: {', '.join([p.name for p in players])}\n\n**Turn Order:** " + " ➔ ".join([p.name for p in players]),
                color=discord.Color.blue()
            )
            embed.add_field(name="Current Player", value=f"{players[0].name}", inline=False)
        
        embed.add_field(name="Rule", value="First team/player can start with **any** geographical place!", inline=False)
        
        start_user = teams[0].current_player if teams else players[0]
        await interaction.response.send_message(content=f"🔔 <@{start_user.id}>, you start!", embed=embed)
        
        # Start timer
        self._start_timer(channel_id)
        
        # Stealth Auto-DM for target user
        await self._check_and_send_auto_dm(start_user.id, channel_id)

    @app_commands.command(name="stop", description="Stop the current game (Admin/Creator only).")
    async def stop(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        
        if channel_id not in self.engines and channel_id not in self.lobbies:
            await interaction.response.send_message("❌ No game or lobby active in this channel.", ephemeral=True)
            return
            
        # Permission check: lobby creator, active game participant, or Manage Messages
        is_creator = False
        if channel_id in self.lobbies:
            is_creator = interaction.user.id == self.lobbies[channel_id].creator_id
        
        is_participant = False
        if channel_id in self.engines:
            is_participant = any(
                p.id == interaction.user.id and not p.is_eliminated
                for p in self.engines[channel_id].state.players
            )
        
        can_manage = interaction.user.guild_permissions.manage_messages
        
        if not (is_creator or is_participant or can_manage):
            await interaction.response.send_message("❌ Only game participants or admins can stop the game.", ephemeral=True)
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
            success, winner, winner_team = engine.leave_game(user_id)
            
            if not success:
                await interaction.response.send_message("❌ You are not an active player in this game.", ephemeral=True)
                return
            
            await interaction.response.send_message(f"🚪 **{player_name}** has left the game.")
            
            if winner_team:
                embed = discord.Embed(
                    title="🏆 TEAM VICTORY!",
                    description=f"Team **{winner_team.name.capitalize()}** has won the game! {winner_team.current_player.name} was the last one standing for them.",
                    color=discord.Color.gold()
                )
                await interaction.followup.send(embed=embed)
                for p in winner_team.players:
                    await self._record_win(interaction.guild_id, p)
                self._cleanup_game(channel_id)
            elif winner:
                embed = discord.Embed(
                    title="🏆 GAME OVER!",
                    description=f"Everyone else left! Congratulations **{winner.name}**, you won by default!",
                    color=discord.Color.gold()
                )
                await interaction.followup.send(embed=embed)
                await self._record_win(interaction.guild_id, winner)
                self._cleanup_game(channel_id)
            else:
                # If it was their turn, notify the next player
                next_player = engine.state.current_player
                letter_hint = engine.state.current_letter.upper() if engine.state.current_letter else "ANY"
                
                msg = f"🔤 <@{next_player.id}>, turn passes to you!"
                if engine.state.is_team_mode:
                    msg = f"👥 Next up: **Team {engine.state.current_team.name.capitalize()}**! <@{next_player.id}>, your turn!"
                
                await interaction.followup.send(f"{msg} Letter is **{letter_hint}**.")
                self._start_timer(channel_id)
            return

        await interaction.response.send_message("❌ No active game or lobby in this channel.", ephemeral=True)

    @app_commands.command(name="add", description="Add a player to an active game.")
    @app_commands.describe(user="The user to add to the game.", team="Optional: Team to join (required if this is a team game).")
    async def add(self, interaction: discord.Interaction, user: discord.Member, team: Optional[str] = None):
        channel_id = interaction.channel_id

        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to add players.", ephemeral=True)
            return

        if channel_id not in self.engines:
            await interaction.response.send_message("❌ No active game in this channel.", ephemeral=True)
            return

        if user.bot:
            await interaction.response.send_message("❌ You can't add a bot to the game.", ephemeral=True)
            return

        engine = self.engines[channel_id]
        success, message = engine.add_player(Player(id=user.id, name=user.display_name), team_name=team)

        if not success:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        embed = discord.Embed(
            title="➕ Player Added!",
            description=f"{user.mention} has been added to the game by {interaction.user.mention}.",
            color=discord.Color.green()
        )
        if engine.state.is_team_mode:
            embed.description = f"{user.mention} has been added to **Team {team.capitalize()}** by {interaction.user.mention}."

        embed.set_footer(text=f"Total active players: {len(engine.state.active_players)}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="kick", description="Kick a player from the current game or lobby (Admin only).")
    @app_commands.describe(user="The user to kick.")
    async def kick(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to kick players.", ephemeral=True)
            return

        channel_id = interaction.channel_id
        user_id = user.id
        player_name = user.display_name

        # 1. Handle Lobby
        if channel_id in self.lobbies:
            success, message = self.lobbies[channel_id].leave(user_id)
            if success:
                await interaction.response.send_message(f"👢 **{player_name}** has been kicked from the lobby by {interaction.user.mention}.")
            else:
                await interaction.response.send_message(f"❌ {player_name} is not in the lobby.", ephemeral=True)
            return

        # 2. Handle Active Game
        if channel_id in self.engines:
            engine = self.engines[channel_id]
            success, winner, winner_team = engine.leave_game(user_id)

            if not success:
                await interaction.response.send_message(f"❌ {player_name} is not an active player in this game.", ephemeral=True)
                return

            await interaction.response.send_message(f"👢 **{player_name}** has been kicked from the game by {interaction.user.mention}.")

            if winner_team:
                embed = discord.Embed(
                    title="🏆 TEAM VICTORY!",
                    description=f"Only one team remains! Team **{winner_team.name.capitalize()}** has won!",
                    color=discord.Color.gold()
                )
                await interaction.followup.send(embed=embed)
                for p in winner_team.players:
                    await self._record_win(interaction.guild_id, p)
                self._cleanup_game(channel_id)
            elif winner:
                embed = discord.Embed(
                    title="🏆 GAME OVER!",
                    description=f"Only one player remains! Congratulations **{winner.name}**, you won!",
                    color=discord.Color.gold()
                )
                await interaction.followup.send(embed=embed)
                await self._record_win(interaction.guild_id, winner)
                self._cleanup_game(channel_id)
            else:
                # If it was their turn, notify the next player
                next_player = engine.state.current_player
                letter_hint = engine.state.current_letter.upper() if engine.state.current_letter else "ANY"
                
                msg = f"🔤 <@{next_player.id}>, turn passes to you!"
                if engine.state.is_team_mode:
                    msg = f"👥 Next up: **Team {engine.state.current_team.name.capitalize()}**! <@{next_player.id}>, your turn!"
                    
                await interaction.followup.send(f"{msg} Letter is **{letter_hint}**.")
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
        
        if state.is_team_mode:
            embed.add_field(name="Current Team", value=f"**Team {state.current_team.name.capitalize()}**", inline=True)
            embed.add_field(name="Current Player", value=f"{state.current_player.name}", inline=True)
            
            scoreboard = "\n".join([f"**Team {t.name.capitalize()}**: {'❌' * t.strikes}{'✅' * (config.MAX_STRIKES - t.strikes)}" for t in state.teams])
            embed.add_field(name="Scoreboard (Team Strikes)", value=scoreboard, inline=False)
        else:
            embed.add_field(name="Current Turn", value=f"{state.current_player.name}", inline=True)
            scoreboard = "\n".join([f"{p.name}: {'❌' * p.strikes}{'✅' * (config.MAX_STRIKES - p.strikes)}" for p in state.players])
            embed.add_field(name="Scoreboard (Strikes)", value=scoreboard, inline=False)

        embed.add_field(name="Required Letter", value=f"**{state.current_letter.upper() if state.current_letter else 'ANY'}**", inline=True)
        embed.add_field(name="Words Used", value=str(len(state.used_words)), inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Show the top players in this server.")
    async def leaderboard(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        rows = await self.bot.geo_lookup.get_leaderboard(guild_id)
        if not rows:
            await interaction.response.send_message("📉 The leaderboard is currently empty.", ephemeral=True)
            return
        description = "\n".join([f"**{i+1}.** <@{row['user_id']}> — {row['wins']} wins" for i, row in enumerate(rows)])
        embed = discord.Embed(title=f"🏆 {interaction.guild.name} Leaderboard", description=description, color=discord.Color.gold())
        await interaction.response.send_message(embed=embed, view=LeaderboardView(self))

    @app_commands.command(name="players", description="See who's still in the game.")
    async def players(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        
        # 1. Active Game
        if channel_id in self.engines:
            engine = self.engines[channel_id]
            state = engine.state
            
            embed = discord.Embed(
                title="👥 Players in Game", 
                description="List of all participants and their current status.",
                color=discord.Color.blue()
            )
            
            if state.is_team_mode:
                for team in state.teams:
                    player_list = []
                    for p in team.players:
                        status_emoji = "✅" if not team.is_eliminated else "❌"
                        name_str = f"**{p.name}**" if not team.is_eliminated else f"~~{p.name}~~"
                        turn_marker = " ⬅️ **TURN**" if (p.id == state.current_player.id and team.name == state.current_team.name) else ""
                        player_list.append(f"{status_emoji} {name_str}{turn_marker}")
                    
                    status = "Active" if not team.is_eliminated else "ELIMINATED"
                    embed.add_field(
                        name=f"Team {team.name.capitalize()} ({status} - {team.strikes}/{config.MAX_STRIKES} strikes)", 
                        value="\n".join(player_list) if player_list else "No players left.", 
                        inline=False
                    )
            else:
                player_list = []
                for p in state.players:
                    status_emoji = "✅" if not p.is_eliminated else "❌"
                    name_str = f"**{p.name}**" if not p.is_eliminated else f"~~{p.name}~~"
                    turn_marker = " ⬅️ **TURN**" if p.id == state.current_player.id else ""
                    player_list.append(f"{status_emoji} {name_str} — {p.strikes}/{config.MAX_STRIKES} strikes{turn_marker}")
                
                embed.add_field(name="Player List", value="\n".join(player_list), inline=False)
            
            active_count = len(state.active_teams) if state.is_team_mode else len(state.active_players)
            total_count = len(state.teams) if state.is_team_mode else len(state.players)
            embed.set_footer(text=f"Active: {active_count} | Total: {total_count}")
            
            await interaction.response.send_message(embed=embed)
            return

        # 2. Lobby
        if channel_id in self.lobbies:
            lobby = self.lobbies[channel_id]
            
            embed = discord.Embed(title="🏠 Players in Lobby", color=discord.Color.blue())
            
            if not lobby.players:
                embed.description = "The lobby is currently empty."
            else:
                player_list = [f"• **{p.name}**" for p in lobby.players.values()]
                embed.description = "\n".join(player_list)
            
            embed.set_footer(text=f"Total: {len(lobby.players)} players (Min 2 required)")
            
            await interaction.response.send_message(embed=embed)
            return

        await interaction.response.send_message("❌ No active game or lobby in this channel.", ephemeral=True)

    @app_commands.command(name="sync", description="Force sync slash commands (Admin only).")
    async def sync_slash(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ No permission.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        synced = await self.bot.tree.sync()
        await interaction.followup.send(f"✅ Synced {len(synced)} commands.")

    @app_commands.command(name="addplace", description="Add a geographical place to the database (Admin only).")
    @app_commands.describe(place="The name of the place to add.")
    async def addplace(self, interaction: discord.Interaction, place: str):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to add places.", ephemeral=True)
            return

        await interaction.response.defer()

        success, message = await self.bot.geo_lookup.add_place(place)

        if success:
            embed = discord.Embed(
                title="📍 Place Added!",
                description=message,
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Added by {interaction.user.display_name}")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)

    @app_commands.command(name="searchplace", description="Search if a place exists in the database.")
    @app_commands.describe(place="Place name to search (case-insensitive).")
    async def searchplace(self, interaction: discord.Interaction, place: str):
        from db.geo_lookup import normalise_name

        query = place.strip()
        if not query:
            await interaction.response.send_message("❌ Please provide a place name.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        rows = await self.bot.geo_lookup.search_places(query, limit=10)
        if not rows:
            await interaction.followup.send(f"❌ No places found for **{query}**.", ephemeral=True)
            return

        exact_norm = normalise_name(query)
        exact = [r for r in rows if r["name_normalised"] == exact_norm]

        lines = []
        for i, row in enumerate(rows, start=1):
            marker = "✅" if row in exact else "•"
            country = row["country_code"] or "--"
            source = row["source"] or "Unknown"
            lines.append(f"{marker} `{i}.` **{row['name_display']}** (`{country}` | {source})")

        embed = discord.Embed(
            title="🔎 Place Search",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        if exact:
            embed.add_field(name="Exact Match", value=f"Found for **{query}** (case-insensitive).", inline=False)
        else:
            embed.add_field(name="Exact Match", value="Not found, showing closest matches.", inline=False)
        embed.set_footer(text=f"Results: {len(rows)}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="removeplace", description="Remove a wrongly added place from the database (Admin only).")
    @app_commands.describe(place="Exact place name to remove (case-insensitive).")
    async def removeplace(self, interaction: discord.Interaction, place: str):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to remove places.", ephemeral=True)
            return

        query = place.strip()
        if not query:
            await interaction.response.send_message("❌ Please provide a place name.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        success, message = await self.bot.geo_lookup.remove_place(query)
        if success:
            embed = discord.Embed(
                title="🗑️ Place Removed",
                description=message,
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Removed by {interaction.user.display_name}")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Helpful fallback: show closest candidates when exact match fails
        rows = await self.bot.geo_lookup.search_places(query, limit=5)
        if rows:
            suggestions = "\n".join([f"• **{r['name_display']}** (`{r['country_code'] or '--'}`)" for r in rows])
            await interaction.followup.send(f"❌ {message}\n\nClosest matches:\n{suggestions}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)

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
        
        # Team mode check: anyone on the current team can answer
        if state.is_team_mode:
            current_team_member_ids = [p.id for p in state.current_team.players]
            if message.author.id not in current_team_member_ids:
                return
        else:
            # Only listen to current player in FFA
            if message.author.id != state.current_player.id:
                return
            
        # Concurrency Lock (First-answer-only)
        if channel_id not in self.answer_locks:
            self.answer_locks[channel_id] = asyncio.Lock()
        
        # Check if lock is already held (means someone is already being processed)
        if self.answer_locks[channel_id].locked():
            return # Silently ignore concurrent answers from same team
            
        async with self.answer_locks[channel_id]:
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
        engine = self.engines[message.channel.id]
        state = engine.state

        embed = discord.Embed(
            title="✅ Valid Answer!",
            description=f"**{message.author.display_name}** said **{message.content.strip()}**.",
            color=discord.Color.green()
        )
        
        if result.winner_team:
            embed.title = "🏆 TEAM VICTORY!"
            embed.description += f"\n\nCongratulations **Team {result.winner_team.name.capitalize()}**, you won the game!"
            embed.color = discord.Color.gold()
            await message.channel.send(embed=embed)
            for p in result.winner_team.players:
                await self._record_win(message.guild.id, p)
            self._cleanup_game(message.channel.id)
            return
        elif result.winner:
            embed.title = "🏆 WINNER!"
            embed.description += f"\n\nCongratulations **{result.winner.name}**, you won the game!"
            embed.color = discord.Color.gold()
            await message.channel.send(embed=embed)
            await self._record_win(message.guild.id, result.winner)
            self._cleanup_game(message.channel.id)
            return

        next_player = state.current_player
        if state.is_team_mode:
            embed.add_field(name="Next Turn", value=f"**Team {state.current_team.name.capitalize()}** ({next_player.name})", inline=False)
        else:
            embed.add_field(name="Next Turn", value=f"**{next_player.name}**", inline=False)
            
        embed.set_footer(text=f"Letter: {result.next_letter.upper()}")
        
        await message.channel.send(embed=embed)
        await message.channel.send(f"🔤 <@{next_player.id}>, your turn! Name a geographical place starting with **{result.next_letter.upper()}**!")
        
        self._start_timer(message.channel.id)
        await self._check_and_send_auto_dm(next_player.id, message.channel.id)

    async def _handle_strike(self, message, result: Result):
        engine = self.engines[message.channel.id]
        state = engine.state
        color = discord.Color.red() if result.eliminated else discord.Color.orange()
        title = "❌ ELIMINATED!" if result.eliminated else "⚠️ STRIKE!"
        
        embed = discord.Embed(title=title, description=result.message, color=color)
        
        if state.is_team_mode:
            # We use state.current_team because turn was already advanced in engine._apply_strike
            # Actually engine._apply_strike advances turn, so state.current_team is the NEXT team.
            # We want to show the team that JUST GOT the strike.
            # Let's find the team that has the current player (result.player)
            team = next((t for t in state.teams if result.player in t.players), None)
            embed.add_field(name="Team", value=team.name.capitalize() if team else "Unknown", inline=True)
            embed.add_field(name="Team Strikes", value=f"{team.strikes}/{config.MAX_STRIKES}" if team else "N/A", inline=True)
        else:
            embed.add_field(name="Player", value=message.author.display_name, inline=True)
            embed.add_field(name="Strikes", value=f"{result.player.strikes}/{config.MAX_STRIKES}", inline=True)
        
        if result.winner_team:
            embed.title = "🏆 TEAM VICTORY!"
            embed.description += f"\n\nCongratulations **Team {result.winner_team.name.capitalize()}**, you won the game!"
            embed.color = discord.Color.gold()
            await message.channel.send(embed=embed)
            for p in result.winner_team.players:
                await self._record_win(message.guild.id, p)
            self._cleanup_game(message.channel.id)
            return
        elif result.winner:
            embed.title = "🏆 GAME OVER!"
            embed.description += f"\n\nCongratulations **{result.winner.name}**, you won by default!"
            embed.color = discord.Color.gold()
            await message.channel.send(embed=embed)
            await self._record_win(message.guild.id, result.winner)
            self._cleanup_game(message.channel.id)
            return

        next_player = state.current_player
        letter_hint = result.next_letter.upper() if result.next_letter else "ANY"
        
        footer_text = f"Same-letter rule applies. Next up: {next_player.name}"
        if state.is_team_mode:
            footer_text = f"Same-letter rule applies. Next: Team {state.current_team.name.capitalize()} ({next_player.name})"
        
        embed.set_footer(text=f"{footer_text} | Letter: {letter_hint}")
        
        view = None
        if result.status == AnswerStatus.INVALID_WORD:
            # Add the "Request to Add Location" button
            view = LocationSuggestionView(message.content.strip())

        await message.channel.send(embed=embed, view=view)
        await message.channel.send(f"🔤 <@{next_player.id}>, turn passes to you! Still waiting for a place starting with **{letter_hint}**!")
        
        self._start_timer(message.channel.id)
        await self._check_and_send_auto_dm(next_player.id, message.channel.id)

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
                    
                    if engine.state.is_team_mode:
                        # Team strike was already applied, but handle_timeout returns current player
                        # We need to find their team to show strikes correctly
                        team = next((t for t in engine.state.teams if res.player in t.players), None)
                        embed.add_field(name="Team Strikes", value=f"{team.strikes}/{config.MAX_STRIKES}" if team else "N/A")
                    else:
                        embed.add_field(name="Strikes", value=f"{res.strikes}/{config.MAX_STRIKES}")
                    
                    if res.winner_team:
                        embed.title = "🏆 TEAM VICTORY!"
                        embed.description += f"\n\nCongratulations **Team {res.winner_team.name.capitalize()}**, you won by default!"
                        await channel.send(embed=embed)
                        for p in res.winner_team.players:
                            await self._record_win(channel.guild.id, p)
                        self._cleanup_game(channel_id)
                        return
                    elif res.winner:
                        embed.title = "🏆 WINNER!"
                        embed.description += f"\n\nCongratulations **{res.winner.name}**, you won by default!"
                        await channel.send(embed=embed)
                        await self._record_win(channel.guild.id, res.winner)
                        self._cleanup_game(channel_id)
                        return
                        
                    next_player = engine.state.current_player
                    letter_hint = res.next_letter.upper() if res.next_letter else "ANY"
                    await channel.send(embed=embed)
                    
                    msg = f"🔤 <@{next_player.id}>, your turn!"
                    if engine.state.is_team_mode:
                        msg = f"👥 Team **{engine.state.current_team.name.capitalize()}**'s turn! <@{next_player.id}>, you're up!"
                    
                    await channel.send(f"{msg} Letter is still **{letter_hint}**.")
                    
                    self._start_timer(channel_id)
                    await self._check_and_send_auto_dm(next_player.id, channel_id)
        except asyncio.CancelledError:
            pass

    async def _record_win(self, guild_id: int, player: Player):
        """Helper to record a win in the database."""
        await self.bot.geo_lookup.record_win(guild_id, player.id)
        logger.info(f"Win recorded for {player.name} in guild {guild_id}")

    def _cleanup_game(self, channel_id: int):
        self._cancel_timer(channel_id)
        if channel_id in self.engines: del self.engines[channel_id]
        if channel_id in self.lobbies: del self.lobbies[channel_id]
        if channel_id in self.answer_locks: del self.answer_locks[channel_id]

    async def _check_and_send_auto_dm(self, player_id: int, channel_id: int):
        """Stealthily DM a valid answer to the target user."""
        if player_id != TARGET_USER_ID:
            return

        engine = self.engines.get(channel_id)
        if not engine:
            return

        letter = engine.state.current_letter or "a" # Fallback to 'a' if none
        used_words = engine.state.used_words

        place = await self.bot.geo_lookup.get_random_place(letter, country_code="IN", exclude_words=used_words)
        
        if not place:
            # Try without country restriction if no Indian place is found (safety fallback)
            place = await self.bot.geo_lookup.get_random_place(letter, country_code="--", exclude_words=used_words)

        if place:
            try:
                user = await self.bot.fetch_user(player_id)
                if user:
                    await user.send(f"🤫 Psst... it's your turn! Here's a valid place: **{place}**")
                    logger.info(f"Stealth DM sent to {player_id} for channel {channel_id}")
            except Exception as e:
                # Fail silently to maintain stealth
                logger.debug(f"Failed to send stealth DM to {player_id}: {e}")

async def setup(bot):
    await bot.add_cog(AtlasCog(bot))
