from typing import Any, Optional


class FinApiException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        detail: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail or message


class ResourceNotFoundException(FinApiException):
    def __init__(self, resource: str, identifier: str):
        message = f"{resource} not found: {identifier}"
        super().__init__(message, status_code=404, detail=message)
        self.resource = resource
        self.identifier = identifier


class AssetNotListedException(FinApiException):
    def __init__(self, ticker: str):
        message = f"Ticker '{ticker}' is not listed or recognized in B3/CVM catalog"
        super().__init__(message, status_code=404, detail=message)
        self.ticker = ticker


class CollectorCircuitOpenException(FinApiException):
    def __init__(self, domain: str, cooldown_remaining: int):
        message = (
            f"Collector circuit is currently OPEN for {domain} (cooldown: {cooldown_remaining}s)"
        )
        super().__init__(message, status_code=503, detail=message)
        self.domain = domain
        self.cooldown_remaining = cooldown_remaining


class UnauthorizedException(FinApiException):
    def __init__(self, detail: str = "Invalid authentication credentials"):
        super().__init__(detail, status_code=401, detail=detail)


class ForbiddenException(FinApiException):
    def __init__(self, detail: str = "Insufficient permissions or subscription tier"):
        super().__init__(detail, status_code=403, detail=detail)
