"""Error type raised by all maker validation."""


class MakerError(ValueError):
    """A validation failure carrying a code, a dotted path and a message."""

    def __init__(self, code: str, path: str, message: str) -> None:
        """Store the error details and format the string representation."""
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}" if path else message)
