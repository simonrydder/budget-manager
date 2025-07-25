from dataclasses import dataclass, field

from budget_manager.models.amount import Amount


class CategoryLimitExceededException(Exception):
    """Exception raised when a category limit is exceeded."""

    pass


@dataclass
class Category:
    name: str
    children: list["Category"] = field(default_factory=list["Category"])
    _limit: Amount | None = None
    # TODO: Track parent category if any

    @property
    def limit(self) -> Amount | None:
        """Public read-only access to limit."""
        return self._limit

    @limit.setter
    def limit(self, new_limit: Amount | None) -> None:
        # ?: Should this raise an exception if the new limit is less than the total of existing children?
        # ?: Should this raise an exception if the new limit makes parent limit invalid?

        self._limit = new_limit

    def __contains__(self, child: "Category") -> bool:
        """Check if a child category is in this category's children."""
        return child in self.children

    def add_child(self, child: "Category") -> None:
        if not self._valid_limit(child):
            raise CategoryLimitExceededException(
                f"Adding {child.name} exceeds category limit of {self.limit}"
            )

        # TODO: set self as parent of child
        self.children.append(child)

    def remove_child(self, child: "Category") -> None:
        self.children.remove(child)

    def _valid_limit(self, child: "Category") -> bool:
        if self.limit is None:
            return True

        if child.limit is None:
            return True

        total_child_limit = child.limit
        for existing_child in self.children:
            total_child_limit += existing_child.limit or Amount(0)

        return total_child_limit < self.limit
