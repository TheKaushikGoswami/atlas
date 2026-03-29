import pytest
from pathlib import Path
from tradle.engine import TradleEngine
from tradle.state import PlayerSession, GuessEntry

@pytest.fixture
def engine():
    return TradleEngine(data_dir=Path("data"))

def test_resolve_country(engine):
    assert engine.resolve_country("France") == "FR"
    assert engine.resolve_country("USA") == "US"
    assert engine.resolve_country("United States") == "US"
    assert engine.resolve_country("South Korea") == "KR"
    assert engine.resolve_country("Japan") == "JP"

def test_distance_calculation(engine):
    # Centroid-based distance between FR and GB is ~1,091km
    dist = engine.calculate_distance("FR", "GB")
    assert 1000 < dist < 1200

def test_bearing_calculation(engine):
    # France is South of UK
    bearing = engine.calculate_bearing("GB", "FR")
    assert bearing in ["⬇️", "↘️", "↙️"]

def test_proximity_percentage(engine):
    assert engine.proximity_percentage(0) == 100
    assert engine.proximity_percentage(20000) == 0
    assert 90 < engine.proximity_percentage(500) < 100

def test_process_guess_correct(engine):
    session = PlayerSession(user_id=1, round_id=1)
    result = engine.process_guess(session, "FR", "France")
    assert result.entry.is_correct is True
    assert session.won is True
    assert session.game_over is True
    assert "🟩" in result.share_text

def test_process_guess_wrong(engine):
    session = PlayerSession(user_id=1, round_id=1)
    result = engine.process_guess(session, "FR", "Japan")
    assert result.entry.is_correct is False
    assert session.won is False
    assert session.game_over is False
    assert "⬛" in result.share_text
    assert len(session.guesses) == 1

def test_max_guesses(engine):
    session = PlayerSession(user_id=1, round_id=1)
    for _ in range(6):
        engine.process_guess(session, "FR", "Japan")
    assert len(session.guesses) == 6
    assert session.game_over is True
    assert session.won is False
