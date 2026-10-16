REASONS = ("timeout", "rate_limit", "server_error", "invalid_response", "invalid_structure", "error")


class AIUnavailableError(Exception):
    """El modelo falló, tardó demasiado o devolvió algo inutilizable."""

    def __init__(self, reason: str = "error", detail: str | None = None):
        self.reason = reason if reason in REASONS else "error"
        self.detail = detail
        super().__init__(f"{self.reason}: {detail}" if detail else self.reason)
