"""Lower-engine diagnostics."""


class LowerEngineError(ValueError):
    """Base error for internal lower-engine misuse."""


class StaleHandleError(LowerEngineError):
    """Raised when a handle belongs to another engine instance."""
