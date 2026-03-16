from dataclasses import dataclass
from .player import Player
from config import config

@dataclass
class Team:
    name: str                    # Normalized team name (first word, lowered)
    players: list[Player]
    strikes: int = 0
    current_player_index: int = 0

    @property
    def is_eliminated(self) -> bool:
        return self.strikes >= config.MAX_STRIKES

    @property
    def current_player(self) -> Player:
        if not self.players:
            raise ValueError(f"Team {self.name} has no players.")
        return self.players[self.current_player_index]

    def advance_player(self):
        """Rotate to the next player within this team."""
        if not self.players:
            return
        self.current_player_index = (self.current_player_index + 1) % len(self.players)

    def __str__(self):
        status = "Eliminated" if self.is_eliminated else f"{self.strikes}/{config.MAX_STRIKES} Strikes"
        return f"Team {self.name.capitalize()} ({status})"
