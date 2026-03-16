from dataclasses import dataclass, field
from .player import Player
from .team import Team

@dataclass
class GameState:
    players: list[Player]
    teams: list[Team] | None = None
    current_index: int = 0
    current_team_index: int = 0
    current_letter: str | None = None
    used_words: set[str] = field(default_factory=set)
    started: bool = False
    
    @property
    def is_team_mode(self) -> bool:
        return self.teams is not None

    @property
    def current_team(self) -> Team:
        if not self.teams:
            raise ValueError("Not in team mode.")
        return self.teams[self.current_team_index]

    @property
    def current_player(self) -> Player:
        if self.is_team_mode:
            return self.current_team.current_player
        
        if not self.players:
            raise ValueError("No players in game state.")
        return self.players[self.current_index]

    @property
    def active_players(self) -> list[Player]:
        return [p for p in self.players if not p.is_eliminated]

    @property
    def active_teams(self) -> list[Team]:
        if not self.teams:
            return []
        return [t for t in self.teams if not t.is_eliminated]

    @property
    def is_game_over(self) -> bool:
        if self.is_team_mode:
            return len(self.active_teams) <= 1
        return len(self.active_players) <= 1
