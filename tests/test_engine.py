import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from game.player import Player
from game.state import GameState
from game.lobby import Lobby
from game.engine import GameEngine, AnswerStatus

# --- Lobby Tests ---

def test_lobby_join():
    lobby = Lobby(123, 456)
    success, msg = lobby.join(1, "Player1")
    assert success is True
    assert len(lobby.players) == 1
    
    success, msg = lobby.join(1, "Player1")
    assert success is False # Duplicate join

def test_lobby_lock():
    lobby = Lobby(123, 456)
    lobby.join(1, "Player1")
    players, msg = lobby.lock()
    assert len(players) == 0 # Need at least 2
    
    lobby.join(2, "Player2")
    players, msg = lobby.lock()
    assert len(players) == 2
    assert lobby.locked is True

# --- Engine Tests ---

@pytest.fixture
def mock_geo_lookup():
    mock = MagicMock()
    mock.is_valid = AsyncMock(return_value=True)
    return mock

@pytest.fixture
def game_engine(mock_geo_lookup):
    players = [Player(1, "P1"), Player(2, "P2")]
    state = GameState(players=players, started=True)
    return GameEngine(state, mock_geo_lookup)

@pytest.mark.asyncio
async def test_engine_valid_answer(game_engine):
    # First turn, any letter valid
    result = await game_engine.submit_answer("Mumbai")
    assert result.status == AnswerStatus.VALID
    assert result.next_letter == "i"
    assert game_engine.state.current_player.id == 2 # Turn advanced

@pytest.mark.asyncio
async def test_engine_wrong_letter(game_engine):
    # Set current letter to 'A'
    game_engine.state.current_letter = "a"
    result = await game_engine.submit_answer("Mumbai") # Starts with M
    assert result.status == AnswerStatus.WRONG_LETTER
    assert result.player.strikes == 1
    assert game_engine.state.current_letter == "a" # Letter didn't change (same-letter rule)
    assert game_engine.state.current_player.id == 2 # Turn advanced

@pytest.mark.asyncio
async def test_engine_elimination(game_engine):
    p1 = game_engine.state.players[0]
    p1.strikes = 1
    
    game_engine.state.current_index = 0
    game_engine.geo_lookup.is_valid.return_value = False
    
    result = await game_engine.submit_answer("Fake")
    assert result.player.is_eliminated is True
    assert result.eliminated is True
    assert result.winner is not None # Only P2 left
    assert result.winner.id == 2

@pytest.mark.asyncio
async def test_engine_timeout(game_engine):
    p1 = game_engine.state.players[0]
    res = await game_engine.handle_timeout()
    assert res.player.id == 1
    assert res.strikes == 1
    assert game_engine.state.current_player.id == 2

# --- Add Player Tests ---

def test_add_player_success(game_engine):
    new_player = Player(3, "P3")
    success, msg = game_engine.add_player(new_player)
    assert success is True
    assert len(game_engine.state.players) == 3
    assert game_engine.state.players[-1].id == 3
    assert new_player in game_engine.state.active_players

def test_add_player_duplicate(game_engine):
    # P1 already exists
    success, msg = game_engine.add_player(Player(1, "P1"))
    assert success is False
    assert len(game_engine.state.players) == 2

def test_add_player_game_over(game_engine):
    # Eliminate P1 so only P2 remains -> game over
    from config import config
    game_engine.state.players[0].strikes = config.MAX_STRIKES
    assert game_engine.state.is_game_over is True

    success, msg = game_engine.add_player(Player(3, "P3"))
    assert success is False

# --- /start Bug Fix Test ---

def test_start_requires_lobby_membership():
    lobby = Lobby(123, 456)
    lobby.join(1, "Player1")
    lobby.join(2, "Player2")

    # User 999 never joined — should not be in lobby.players
    assert 999 not in lobby.players
    # User 1 did join
    assert 1 in lobby.players
