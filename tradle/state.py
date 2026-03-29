from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

@dataclass
class GuessEntry:
    country_iso: str
    country_name: str
    distance_km: float
    direction: str # Emoji arrow
    proximity_pct: int
    is_correct: bool

@dataclass
class PlayerSession:
    user_id: int
    round_id: int
    guesses: List[GuessEntry] = field(default_factory=list)
    won: bool = False
    game_over: bool = False
    completed_at: Optional[datetime] = None

@dataclass
class TradleRound:
    id: int
    target_country_iso: str
    started_at: datetime
    total_export_value_str: str
    ended_at: Optional[datetime] = None
    is_active: bool = True

@dataclass
class GuessResult:
    entry: GuessEntry
    session: PlayerSession
    share_text: str # E.g. "Tradle #42 3/6\n🟩⬜️🟨"
