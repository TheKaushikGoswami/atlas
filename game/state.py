from dataclasses import dataclass, field
from .player import Player

@dataclass
class GameState:
    players: list[Player]
    current_index: int = 0
    current_letter: str | None = None
    used_words: set[str] = field(default_factory=set)
    started: bool = False
    
    @property
    def current_player(self) -> Player:
        if not self.players:
            raise ValueError("No players in game state.")
        return self.players[self.current_index]

    @property
    def active_players(self) -> list[Player]:
        return [p for p in self.players if not p.is_eliminated]

    @property
    def is_game_over(self) -> bool:
        return len(self.active_players) <= 1
