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
