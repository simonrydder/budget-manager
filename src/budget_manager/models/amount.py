from dataclasses import dataclass


@dataclass(frozen=True, eq=False)
class Amount:
    value: int

    @classmethod
    def from_float(cls, value: float) -> "Amount":
        return cls(int(value * 100))

    def to_float(self) -> float:
        return self.value / 100.0

    def __add__(self, other: "Amount") -> "Amount":
        return Amount(self.value + other.value)

    def __sub__(self, other: "Amount") -> "Amount":
        return self.__add__(Amount(-other.value))

    def __str__(self) -> str:
        return f"{self.to_float():.2f}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Amount):
            raise TypeError("Comparison must be with another Amount instance")

        return self.value == other.value

    def __lt__(self, other: "Amount") -> bool:
        return self.value < other.value

    def __le__(self, other: "Amount") -> bool:
        return self.value <= other.value
