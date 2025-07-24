from dataclasses import dataclass

from budget_manager.models.amount import Amount


class CategoryLimitExceededException(Exception):
    """Exception raised when a category limit is exceeded."""

    pass


@dataclass
class Category:
    name: str
    children: list["Category"] | None = None
    _limit: Amount | None = None
    # TODO: Track parent category if any
    # TODO: Add limit setter that checks for valid limit (should not invalidate parent limit)

    @property
    def limit(self) -> Amount | None:
        """Public read-only access to limit."""
        return self._limit

    @limit.setter
    def limit(self, new_limit: Amount | None) -> None:
        self._limit = new_limit

    def __contains__(self, child: "Category") -> bool:
        if self.children is None:
            return False

        return child in self.children

    def add_child(self, child: "Category") -> None:
        if self.children is None:
            self.children = []

        if not self._valid_limit(child):
            raise CategoryLimitExceededException(
                f"Adding {child.name} exceeds category limit of {self.limit}"
            )

        # TODO: set self as parent of child
        self.children.append(child)

    def remove_child(self, child: "Category") -> None:
        if self.children is None:
            raise ValueError("No children to remove")

        self.children.remove(child)

    def _valid_limit(self, child: "Category") -> bool:
        if self.limit is None:
            return True

        if child.limit is None:
            return True

        total_child_limit = child.limit
        for existing_child in self.children or []:
            total_child_limit += existing_child.limit or Amount(0)

        return total_child_limit < self.limit
