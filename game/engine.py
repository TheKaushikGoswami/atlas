import logging
import enum
from typing import NamedTuple, Optional
from unidecode import unidecode
from .state import GameState
from .player import Player

logger = logging.getLogger(__name__)

class AnswerStatus(enum.Enum):
    VALID = enum.auto()
    INVALID_WORD = enum.auto()
    WRONG_LETTER = enum.auto()
    ALREADY_USED = enum.auto()

from .team import Team

class Result(NamedTuple):
    status: AnswerStatus
    message: str
    player: Player
    next_letter: Optional[str] = None
    eliminated: bool = False
    winner: Optional[Player] = None
    winner_team: Optional[Team] = None

class TimeoutResult(NamedTuple):
    player: Player
    strikes: int
    eliminated: bool
    next_letter: Optional[str]
    winner: Optional[Player]
    winner_team: Optional[Team] = None

def normalise_word(word: str) -> str:
    return unidecode(word).lower().strip()

class GameEngine:
    def __init__(self, state: GameState, geo_lookup):
        self.state = state
        self.geo_lookup = geo_lookup # This is the GeoLookup instance from db/

    async def submit_answer(self, word: str) -> Result:
        """
        Process a player's answer.
        Returns a Result object with the outcome.
        """
        if self.state.is_game_over:
            return Result(AnswerStatus.INVALID_WORD, "Game is already over!", self.state.current_player)

        player = self.state.current_player
        
        # Concurrency check is handled in the Cog via a Lock, 
        # but we branch logic here for team mode.

        word = word.strip()
        
        if not word:
            return Result(AnswerStatus.INVALID_WORD, "Empty message received.", player)

        # 1. Check if first letter matches (if required)
        if self.state.current_letter:
            if word[0].lower() != self.state.current_letter:
                msg = f"Wrong letter! You were supposed to name a place starting with **{self.state.current_letter.upper()}**."
                return await self._apply_strike(player, AnswerStatus.WRONG_LETTER, msg)

        # 2. Check if place exists in DB
        is_valid_geo = await self.geo_lookup.is_valid(word)
        if not is_valid_geo:
            msg = f"**{word}** is not in my geographical database or it's not a valid place."
            return await self._apply_strike(player, AnswerStatus.INVALID_WORD, msg)

        # 3. Check if already used
        normalised = normalise_word(word)
        if normalised in self.state.used_words:
            msg = f"**{word}** has already been used in this game!"
            return await self._apply_strike(player, AnswerStatus.ALREADY_USED, msg)

        # ✅ SUCCESS
        self.state.used_words.add(normalised)
        next_letter = word[-1].lower()
        self.state.current_letter = next_letter
        
        msg = f"✅ **{word}** accepted!"
        
        # Move to next turn
        self._advance_turn()
        
        winner, winner_team = self._check_winner()
        return Result(AnswerStatus.VALID, msg, player, next_letter, winner=winner, winner_team=winner_team)

    async def handle_timeout(self) -> TimeoutResult:
        """Handle turn timeout."""
        from config import config
        player = self.state.current_player
        msg = "Time's up! You took too long to answer."
        logger.info(f"Timeout for {player.name}")
        
        eliminated = False
        strikes = 0

        if self.state.is_team_mode:
            team = self.state.current_team
            team.strikes = min(team.strikes + 1, config.MAX_STRIKES)
            eliminated = team.is_eliminated
            strikes = team.strikes
            if eliminated:
                logger.info(f"Team {team.name} eliminated on timeout.")
        else:
            if not player.is_eliminated:
                player.strikes = min(player.strikes + 1, config.MAX_STRIKES)
            eliminated = player.is_eliminated
            strikes = player.strikes
            if eliminated:
                logger.info(f"Player {player.name} eliminated on timeout.")
        
        # Advance turn but keep the current letter (same-letter rule)
        self._advance_turn()
        winner, winner_team = self._check_winner()
        
        return TimeoutResult(
            player=player,
            strikes=strikes,
            eliminated=eliminated,
            next_letter=self.state.current_letter,
            winner=winner,
            winner_team=winner_team
        )

    async def _apply_strike(self, player: Player, status: AnswerStatus, message: str) -> Result:
        """Apply a strike to the current player or team."""
        from config import config
        
        eliminated = False
        if self.state.is_team_mode:
            team = self.state.current_team
            team.strikes = min(team.strikes + 1, config.MAX_STRIKES)
            eliminated = team.is_eliminated
        else:
            if not player.is_eliminated:
                player.strikes = min(player.strikes + 1, config.MAX_STRIKES)
            eliminated = player.is_eliminated
        
        # Advanced turn
        self._advance_turn()
        winner, winner_team = self._check_winner()
        
        # When a strike is applied, the letter DOES NOT change (same-letter rule)
        return Result(
            status=status,
            message=message,
            player=player,
            next_letter=self.state.current_letter,
            eliminated=eliminated,
            winner=winner,
            winner_team=winner_team
        )

    def leave_game(self, user_id: int) -> tuple[bool, Optional[Player], Optional[Team]]:
        """
        Manually remove a player from the game.
        Returns (success, winner_player, winner_team).
        """
        from config import config
        target_player = None
        for p in self.state.players:
            if p.id == user_id:
                target_player = p
                break
        
        if not target_player or target_player.is_eliminated:
            return False, None, None

        is_current = (self.state.current_player.id == user_id)
        
        if self.state.is_team_mode:
            # Find and remove from team
            for team in self.state.teams:
                if target_player in team.players:
                    team.players.remove(team.players[team.current_player_index]) if is_current else team.players.remove(target_player)
                    # If team is empty, eliminate it
                    if not team.players:
                        team.strikes = config.MAX_STRIKES
                    break
        else:
            # Eliminate player
            target_player.strikes = config.MAX_STRIKES
        
        logger.info(f"Player {target_player.name} left the game.")

        # Advance turn if it was their turn
        if is_current and not self.state.is_game_over:
            self._advance_turn()
            
        winner, winner_team = self._check_winner()
        return True, winner, winner_team

    def add_player(self, player: Player, team_name: str | None = None) -> tuple[bool, str]:
        """
        Add a new player to an active game mid-round.
        Returns (success, message).
        """
        if self.state.is_game_over:
            return False, "The game is already over."

        for p in self.state.players:
            if p.id == player.id:
                return False, f"**{player.name}** is already in this game."

        if self.state.is_team_mode:
            if not team_name:
                return False, "This is a team game. You must specify which team to join."
            
            norm_name = team_name.strip().split()[0].lower()
            target_team = next((t for t in self.state.teams if t.name == norm_name), None)
            if not target_team:
                return False, f"Team **{team_name}** does not exist."
            
            target_team.players.append(player)
            self.state.players.append(player)
            logger.info(f"Player {player.name} added to Team {norm_name} mid-round.")
            return True, f"**{player.name}** has been added to **Team {norm_name.capitalize()}**!"

        self.state.players.append(player)
        logger.info(f"Player {player.name} added to the game mid-round.")
        return True, f"**{player.name}** has been added to the game!"

    def _advance_turn(self):
        """Move turn to the next active player/team."""
        if self.state.is_team_mode:
            # 1. Advance player inside current team
            self.state.current_team.advance_player()
            
            # 2. Switch to next active team
            if not self.state.active_teams:
                return

            while True:
                self.state.current_team_index = (self.state.current_team_index + 1) % len(self.state.teams)
                if not self.state.teams[self.state.current_team_index].is_eliminated:
                    break
            logger.debug(f"Turn switched to Team {self.state.current_team.name}")
        else:
            if not self.state.active_players:
                return

            # Start from the next index and loop around until an active player is found
            while True:
                self.state.current_index = (self.state.current_index + 1) % len(self.state.players)
                if not self.state.players[self.state.current_index].is_eliminated:
                    break
            
            logger.debug(f"Turn advanced to {self.state.current_player.name}")

    def _check_winner(self) -> tuple[Optional[Player], Optional[Team]]:
        """Return the winner (Player, Team)."""
        if self.state.is_team_mode:
            active = self.state.active_teams
            if len(active) == 1:
                # Return current player of the winning team for record_win compatibility
                return active[0].current_player, active[0]
        else:
            active = self.state.active_players
            if len(active) == 1:
                return active[0], None
        return None, None
