from dataclasses import dataclass
from config import config

@dataclass
class Player:
    id: int          # Discord User ID
    name: str        # Display Name
    strikes: int = 0

    @property
    def is_eliminated(self) -> bool:
        return self.strikes >= config.MAX_STRIKES

    def __str__(self):
        return f"{self.name} ({'Eliminated' if self.is_eliminated else f'{self.strikes}/{config.MAX_STRIKES} Strikes'})"
