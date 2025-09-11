from typing import Annotated

Month = Annotated[int, lambda x: 1 <= x <= 12]
