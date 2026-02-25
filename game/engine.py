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

class Result(NamedTuple):
    status: AnswerStatus
    message: str
    player: Player
    next_letter: Optional[str] = None
    eliminated: bool = False
    winner: Optional[Player] = None

class TimeoutResult(NamedTuple):
    player: Player
    strikes: int
    eliminated: bool
    next_letter: Optional[str]
    winner: Optional[Player]

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
        if player.is_eliminated:
            # This should ideally not happen if turn advancement is correct
            self._advance_turn()
            player = self.state.current_player

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
        
        winner = self._check_winner()
        return Result(AnswerStatus.VALID, msg, player, next_letter, winner=winner)

    async def handle_timeout(self) -> TimeoutResult:
        """Handle turn timeout."""
        from config import config
        player = self.state.current_player
        msg = "Time's up! You took too long to answer."
        logger.info(f"Timeout for {player.name}")
        
        # Timeout is a strike
        if not player.is_eliminated:
            player.strikes = min(player.strikes + 1, config.MAX_STRIKES)
        eliminated = player.is_eliminated
        
        if eliminated:
            logger.info(f"Player {player.name} eliminated on timeout.")
        
        # Advance turn but keep the current letter (same-letter rule)
        self._advance_turn()
        winner = self._check_winner()
        
        return TimeoutResult(
            player=player,
            strikes=player.strikes,
            eliminated=eliminated,
            next_letter=self.state.current_letter,
            winner=winner
        )

    async def _apply_strike(self, player: Player, status: AnswerStatus, message: str) -> Result:
        """Apply a strike to the current player."""
        from config import config
        
        if not player.is_eliminated:
            player.strikes = min(player.strikes + 1, config.MAX_STRIKES)
        
        eliminated = player.is_eliminated
        
        # Advanced turn
        self._advance_turn()
        winner = self._check_winner()
        
        # When a strike is applied, the letter DOES NOT change (same-letter rule)
        return Result(
            status=status,
            message=message,
            player=player,
            next_letter=self.state.current_letter,
            eliminated=eliminated,
            winner=winner
        )

    def leave_game(self, user_id: int) -> tuple[bool, Optional[Player]]:
        """
        Manually remove a player from the game.
        Returns (success, winner).
        """
        from config import config
        target_player = None
        for p in self.state.players:
            if p.id == user_id:
                target_player = p
                break
        
        if not target_player or target_player.is_eliminated:
            return False, None

        is_current = (self.state.current_player.id == user_id)
        
        # Eliminate player
        target_player.strikes = config.MAX_STRIKES
        logger.info(f"Player {target_player.name} left the game.")

        # Advance turn if it was their turn
        if is_current and not self.state.is_game_over:
            self._advance_turn()
            
        return True, self._check_winner()

    def _advance_turn(self):
        """Move current_index to the next active player."""
        if not self.state.active_players:
            return

        # Start from the next index and loop around until an active player is found
        while True:
            self.state.current_index = (self.state.current_index + 1) % len(self.state.players)
            if not self.state.players[self.state.current_index].is_eliminated:
                break
        
        logger.debug(f"Turn advanced to {self.state.current_player.name}")

    def _check_winner(self) -> Optional[Player]:
        """Return the winner if only 1 active player remains."""
        active = self.state.active_players
        if len(active) == 1:
            return active[0]
        return None
