"""Pronóstico de OpenWeatherMap en intervalos de 3 h (R-04)."""

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app import audit, config
from app.clock import TZ

FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
TIMEOUT_S = 5


@dataclass(frozen=True)
class Slot:
    start: datetime  # inicio del intervalo [start, start + 3 h), en Buenos Aires
    pop_pct: int
    temp_c: float
    thunderstorm: bool


@dataclass(frozen=True)
class Forecast:
    slots: list[Slot]


class WeatherUnavailableError(Exception):
    def __init__(self, reason: str, detail: str | None = None):
        self.reason = reason
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _reason_for_status(status: int) -> str:
    if status == 429:
        return "rate_limit"
    if status >= 500:
        return "server_error"
    if status == 404:
        return "city_not_found"
    return "http_error"


def _parse(payload) -> Forecast:
    slots = []
    for item in payload["list"]:
        ids = [w["id"] for w in item.get("weather", [])]
        slots.append(
            Slot(
                start=datetime.fromtimestamp(int(item["dt"]), tz=timezone.utc).astimezone(TZ),
                pop_pct=round(float(item.get("pop", 0)) * 100),
                temp_c=float(item["main"]["temp"]),
                thunderstorm=any(200 <= int(i) <= 232 for i in ids),
            )
        )
    return Forecast(slots=slots)


async def fetch_forecast(city: str, *, transport: httpx.AsyncBaseTransport | None = None) -> Forecast:
    """`transport` solo se usa en los tests. La `appid` nunca se registra."""
    params = {"q": f"{city},AR", "units": "metric", "appid": config.openweather_api_key()}
    outcome = "ok"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
            response = await client.get(FORECAST_URL, params=params)
        if response.status_code != 200:
            raise WeatherUnavailableError(_reason_for_status(response.status_code), str(response.status_code))
        try:
            return _parse(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise WeatherUnavailableError("invalid_response", type(exc).__name__) from None
    except httpx.TimeoutException:
        outcome = "timeout"
        raise WeatherUnavailableError("timeout") from None
    except httpx.HTTPError as exc:
        outcome = "network_error"
        raise WeatherUnavailableError("network_error", type(exc).__name__) from None
    except WeatherUnavailableError as exc:
        outcome = exc.reason
        raise
    finally:
        audit.event("tool_call", tool="weather", city=city, outcome=outcome)
