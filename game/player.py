from dataclasses import dataclass

@dataclass
class Player:
    id: int          # Discord User ID
    name: str        # Display Name
    strikes: int = 0

    @property
    def is_eliminated(self) -> bool:
        return self.strikes >= 2

    def __str__(self):
        return f"{self.name} ({'Eliminated' if self.is_eliminated else f'{self.strikes}/2 Strikes'})"
