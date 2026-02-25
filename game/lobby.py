import logging
from .player import Player

logger = logging.getLogger(__name__)

class Lobby:
    def __init__(self, channel_id: int, creator_id: int):
        self.channel_id = channel_id
        self.creator_id = creator_id
        self.players: dict[int, Player] = {} # ID -> Player object
        self.locked = False

    def join(self, user_id: int, user_name: str) -> tuple[bool, str]:
        """
        Add a player to the lobby.
        Returns (success, message).
        """
        if self.locked:
            return False, "The lobby is locked. A game is already starting or in progress."
        
        if user_id in self.players:
            return False, "You have already joined the lobby."
        
        self.players[user_id] = Player(id=user_id, name=user_name)
        logger.info(f"User {user_name} ({user_id}) joined lobby in channel {self.channel_id}")
        return True, f"**{user_name}** has joined the game!"

    def leave(self, user_id: int) -> tuple[bool, str]:
        """Remove a player from the lobby."""
        if self.locked:
            return False, "You cannot leave a locked lobby."
        
        if user_id not in self.players:
            return False, "You are not in the lobby."
        
        player = self.players.pop(user_id)
        return True, f"**{player.name}** has left the lobby."

    def lock(self) -> tuple[list[Player], str]:
        """
        Lock the lobby and return the list of players.
        Requires at least 2 players.
        """
        if len(self.players) < 2:
            return [], "Need at least 2 players to start the game."
        
        self.locked = True
        # Return players in the order they joined (dict is insertion ordered in modern Python)
        return list(self.players.values()), "Lobby locked. Starting game..."
