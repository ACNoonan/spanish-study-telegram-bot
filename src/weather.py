"""Simple Open-Meteo client for daily weather summary (Madrid default).

This module intentionally keeps things minimal: it fetches the current weather
for Madrid (or a provided lat/lon) and reduces it to a coarse category plus
temperature in Celsius for tone adjustments.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


# Madrid coordinates (Puerta del Sol area)
DEFAULT_LAT = 40.4168
DEFAULT_LON = -3.7038


def _weathercode_to_category(code: int) -> str:
    """Map Open-Meteo weathercode to a coarse category string."""
    # https://open-meteo.com/en/docs#api_form
    mapping = {
        0: "clear",
        1: "mainly_clear",
        2: "partly_cloudy",
        3: "overcast",
        45: "fog",
        48: "fog",
        51: "drizzle",
        53: "drizzle",
        55: "drizzle",
        56: "freezing_drizzle",
        57: "freezing_drizzle",
        61: "rain",
        63: "rain",
        65: "rain",
        66: "freezing_rain",
        67: "freezing_rain",
        71: "snow",
        73: "snow",
        75: "snow",
        77: "snow_grains",
        80: "rain_showers",
        81: "rain_showers",
        82: "rain_showers",
        85: "snow_showers",
        86: "snow_showers",
        95: "thunderstorm",
        96: "thunderstorm_hail",
        99: "thunderstorm_hail",
    }
    return mapping.get(int(code), "unknown")


async def fetch_daily_weather_summary(
    *,
    latitude: float = DEFAULT_LAT,
    longitude: float = DEFAULT_LON,
) -> Optional[Tuple[str, float]]:
    """Return (category, temp_c) using Open-Meteo current weather, or None on failure."""
    url = (
        "https://api.open-meteo.com/v1/forecast?latitude="
        f"{latitude}&longitude={longitude}&current_weather=true"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            current = data.get("current_weather") or {}
            code = int(current.get("weathercode", -1))
            temp_c = float(current.get("temperature", 0.0))
            category = _weathercode_to_category(code)
            return category, temp_c
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Weather fetch failed: %s", exc)
        return None


