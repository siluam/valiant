from rich.prompt import PromptBase, InvalidResponse
from rich.text import Text
from typing import List, TypeVar


# Adapted From: https://github.com/Textualize/rich/blob/master/rich/prompt.py#L322
class Confirm(PromptBase[bool]):
    """A yes / no confirmation prompt.
    Example:
        >>> if Confirm.ask("Continue"):
                run_job()
    """

    response_type = bool
    validate_error_message = "[prompt.invalid]Please enter Y/Yes or N/No"
    choices: List[str] = ["y", "yes", "n", "no"]

    def render_default(self, default: TypeVar("DefaultType")) -> Text:
        """Render the default as (y) or (n) rather than True/False."""
        y, yes, n, no = self.choices
        return Text(
            f"({y})/({yes})" if default else f"({n})/({no})", style="prompt.default"
        )

    def process_response(self, value: str) -> bool:
        """Convert choices to a bool."""
        value = value.strip().lower()
        if value not in self.choices:
            raise InvalidResponse(self.validate_error_message)
        return value == self.choices[0]
