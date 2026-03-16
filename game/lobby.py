import logging
from .player import Player

logger = logging.getLogger(__name__)

class Lobby:
    def __init__(self, channel_id: int, creator_id: int):
        self.channel_id = channel_id
        self.creator_id = creator_id
        self.players: dict[int, Player] = {} # ID -> Player object
        self.teams: dict[str, list[int]] = {} # Normalized Team Name -> list of Player IDs
        self.is_team_mode: bool | None = None # None until first join establishes mode
        self.locked = False

    def join(self, user_id: int, user_name: str, team_name: str | None = None) -> tuple[bool, str]:
        """
        Add a player to the lobby.
        Returns (success, message).
        """
        if self.locked:
            return False, "The lobby is locked. A game is already starting or in progress."
        
        if user_id in self.players:
            return False, "You have already joined the lobby."

        # Establish mode on first join
        if self.is_team_mode is None:
            self.is_team_mode = team_name is not None
        
        # Enforce mode consistency
        if self.is_team_mode and not team_name:
            return False, "This is a team-based lobby. Please specify a team name (e.g., `/join team:Red`)."
        if not self.is_team_mode and team_name:
            return False, "This is a free-for-all lobby. You cannot specify a team."

        normalized_team = None
        if team_name:
            # Only the 1st word of a team would be considered
            normalized_team = team_name.strip().split()[0].lower()
            if normalized_team not in self.teams:
                self.teams[normalized_team] = []
            self.teams[normalized_team].append(user_id)

        self.players[user_id] = Player(id=user_id, name=user_name)
        logger.info(f"User {user_name} ({user_id}) joined lobby in channel {self.channel_id} (Team: {normalized_team})")
        
        msg = f"**{user_name}** has joined the game!"
        if normalized_team:
            msg = f"**{user_name}** has joined **Team {normalized_team.capitalize()}**!"
        return True, msg

    def leave(self, user_id: int) -> tuple[bool, str]:
        """Remove a player from the lobby."""
        if self.locked:
            return False, "You cannot leave a locked lobby."
        
        if user_id not in self.players:
            return False, "You are not in the lobby."
        
        player = self.players.pop(user_id)
        
        # Remove from teams if in team mode
        for team_name, player_ids in self.teams.items():
            if user_id in player_ids:
                player_ids.remove(user_id)
                if not player_ids:
                    del self.teams[team_name]
                break

        # Reset mode if lobby becomes empty
        if not self.players:
            self.is_team_mode = None

        return True, f"**{player.name}** has left the lobby."

    def lock(self) -> tuple[list[Player], dict[str, list[Player]], str]:
        """
        Lock the lobby and return the list of players and teams.
        In team mode, requires exactly 2 teams. In FFA, requires 2 players.
        """
        if self.is_team_mode:
            if len(self.teams) != 2:
                return [], {}, "Team mode requires exactly 2 teams to start."
            for tname, pids in self.teams.items():
                if not pids:
                    return [], {}, f"Team {tname.capitalize()} has no players!"
        else:
            if len(self.players) < 2:
                return [], {}, "Need at least 2 players to start the game."
        
        self.locked = True
        
        # Build team objects for return
        team_data = {}
        if self.is_team_mode:
            for tname, pids in self.teams.items():
                team_data[tname] = [self.players[pid] for pid in pids]

        return list(self.players.values()), team_data, "Lobby locked. Starting game..."
