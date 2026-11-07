class GenerationError(Exception):
    """An expected generation failure with a message safe to return to a user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
