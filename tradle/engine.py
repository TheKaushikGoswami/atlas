import math
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from unidecode import unidecode
from .state import GuessEntry, PlayerSession, TradleRound, GuessResult

logger = logging.getLogger(__name__)

class TradleEngine:
    def __init__(self, data_dir: Path = Path("data")):
        self.data_dir = data_dir
        self.trade_data = self._load_json("trade_data.json")
        self.centroid_coords = self._load_json("country_centroids.json")
        if not self.centroid_coords:
            self.centroid_coords = self._load_packaged_json("country_centroids.json")
        self.capital_coords = self._load_json("capitals_coords.json")
        self.country_names = self._load_country_names()

    def _load_json(self, name: str) -> Dict[str, Any]:
        path = self.data_dir / name
        if not path.exists():
            logger.warning(f"Data file {path} not found.")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_packaged_json(self, name: str) -> Dict[str, Any]:
        path = Path(__file__).parent / name
        if not path.exists():
            logger.warning(f"Packaged data file {path} not found.")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_country_names(self) -> Dict[str, str]:
        """Map normalised name to ISO2."""
        names = {}
        # Try to use countryInfo.txt if exists
        info_path = self.data_dir / "countryInfo.txt"
        if info_path.exists():
            with open(info_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("#"): continue
                    parts = line.split("\t")
                    if len(parts) > 4:
                        iso2 = parts[0]
                        name = parts[4]
                        names[self.normalise(name)] = iso2
        
        # Also add names from trade_data (OEC captions might be different)
        # Using known coordinate keys as source of truth for ISO2s we have.
        known_isos = set(self.centroid_coords.keys()) | set(self.capital_coords.keys())
        for iso2 in known_isos:
            # We don't have a direct name map here, but we can assume common names
            pass
            
        return names

    def _get_country_point(self, iso2: str) -> Optional[Dict[str, float]]:
        """Return country point preferring geographic centroid, fallback to capital coords."""
        return self.centroid_coords.get(iso2) or self.capital_coords.get(iso2)

    @staticmethod
    def normalise(name: str) -> str:
        return unidecode(name).lower().strip()

    def resolve_country(self, name: str) -> Optional[str]:
        """Resolve a country name to its ISO2 code."""
        norm = self.normalise(name)
        if norm in self.country_names:
            return self.country_names[norm]
        
        # Common aliases
        aliases = {
            "usa": "US", "united states": "US", "united states of america": "US",
            "uk": "GB", "united kingdom": "GB", "britain": "GB",
            "uae": "AE", "united arab emirates": "AE",
            "russia": "RU", "russian federation": "RU",
            "south korea": "KR", "korea": "KR", "republic of korea": "KR",
            "north korea": "KP",
            "china": "CN",
            "hkg": "HK", "hong kong": "HK"
        }
        if norm in aliases:
            return aliases[norm]
        
        # Partial match
        for cn, iso in self.country_names.items():
            if norm in cn or cn in norm:
                return iso
                
        return None

    def calculate_distance(self, iso_a: str, iso_b: str) -> float:
        """Calculate Haversine distance in km (country centroid-based)."""
        coord_a = self._get_country_point(iso_a)
        coord_b = self._get_country_point(iso_b)
        if not coord_a or not coord_b:
            return 0.0

        lat1, lon1 = math.radians(coord_a["lat"]), math.radians(coord_a["lng"])
        lat2, lon2 = math.radians(coord_b["lat"]), math.radians(coord_b["lng"])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        radius = 6371 # Earth's radius in km
        return radius * c

    def calculate_bearing(self, iso_a: str, iso_b: str) -> str:
        """Calculate centroid-to-centroid bearing and return arrow emoji."""
        coord_a = self._get_country_point(iso_a)
        coord_b = self._get_country_point(iso_b)
        if not coord_a or not coord_b:
            return "❓"

        if iso_a == iso_b:
            return "🎉"

        lat1, lon1 = math.radians(coord_a["lat"]), math.radians(coord_a["lng"])
        lat2, lon2 = math.radians(coord_b["lat"]), math.radians(coord_b["lng"])

        y = math.sin(lon2 - lon1) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
        bearing = (math.degrees(math.atan2(y, x)) + 360) % 360

        # Map bearing to arrow
        arrows = {
            "N": "⬆️", "NE": "↗️", "E": "➡️", "SE": "↘️",
            "S": "⬇️", "SW": "↙️", "W": "⬅️", "NW": "↖️"
        }
        
        if 337.5 <= bearing or bearing < 22.5: return arrows["N"]
        if 22.5 <= bearing < 67.5: return arrows["NE"]
        if 67.5 <= bearing < 112.5: return arrows["E"]
        if 112.5 <= bearing < 157.5: return arrows["SE"]
        if 157.5 <= bearing < 202.5: return arrows["S"]
        if 202.5 <= bearing < 247.5: return arrows["SW"]
        if 247.5 <= bearing < 292.5: return arrows["W"]
        if 292.5 <= bearing < 337.5: return arrows["NW"]
        return "➡️"

    def proximity_percentage(self, distance_km: float) -> int:
        """Calculate proximity percentage (0-100%). Max distance on Earth is ~20,000km."""
        max_dist = 20000.0
        pct = max(0, 100 - (distance_km / max_dist) * 100)
        return int(round(pct))

    def get_country_name(self, iso2: str) -> str:
        # Inverse lookup (not efficient but fine for small list)
        for name, iso in self.country_names.items():
            if iso == iso2:
                # Return original capitalization if possible (too lazy now, just title case it)
                return name.title()
        return iso2

    def process_guess(self, session: PlayerSession, target_iso: str, guess_name: str) -> Optional[GuessResult]:
        """Process a user guess and return the result."""
        guess_iso = self.resolve_country(guess_name)
        if not guess_iso:
            return None # Invalid country name

        dist = self.calculate_distance(guess_iso, target_iso)
        bearing = self.calculate_bearing(guess_iso, target_iso)
        prox = self.proximity_percentage(dist)
        is_correct = (guess_iso == target_iso)

        entry = GuessEntry(
            country_iso=guess_iso,
            country_name=self.get_country_name(guess_iso),
            distance_km=dist,
            direction=bearing,
            proximity_pct=prox,
            is_correct=is_correct
        )

        session.guesses.append(entry)
        if is_correct:
            session.won = True
            session.game_over = True
        elif len(session.guesses) >= 6:
            session.game_over = True
        
        # Generate share text emoji pattern
        squares = ""
        for g in session.guesses:
            if g.is_correct: squares += "🟩"
            elif g.proximity_pct > 90: squares += "🟨"
            else: squares += "⬛"
        
        share_text = f"Tradle #{session.round_id} {len(session.guesses)}/6\n{squares}"

        return GuessResult(entry=entry, session=session, share_text=share_text)
