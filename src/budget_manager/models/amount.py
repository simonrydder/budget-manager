from dataclasses import dataclass


@dataclass(frozen=True)
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
