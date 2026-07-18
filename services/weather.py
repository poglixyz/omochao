from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

FORECAST_LIMIT_DAYS = 16


class WeatherError(Exception):
    pass


class DateParseError(WeatherError):
    pass


@dataclass(frozen=True)
class Location:
    name: str
    country: str
    latitude: float
    longitude: float
    admin1: str | None = None
    timezone: str | None = None

    @property
    def label(self) -> str:
        parts = [self.name]
        if self.admin1 and self.admin1 != self.name:
            parts.append(self.admin1)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)


@dataclass(frozen=True)
class WeatherReport:
    location: Location
    kind: str
    condition: str
    observed_at: str | None = None
    target_date: date | None = None
    temperature: float | None = None
    apparent_temperature: float | None = None
    humidity: int | None = None
    precipitation: float | None = None
    temp_min: float | None = None
    temp_max: float | None = None
    rain_chance: int | None = None
    wind_speed: float | None = None
    sunrise: str | None = None
    sunset: str | None = None


WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


def condition_for(code: int | None) -> str:
    if code is None:
        return "Unknown"
    return WEATHER_CODES.get(code, f"Weather code {code}")


def local_today(location: Location) -> date:
    timezone = ZoneInfo(location.timezone or "UTC")
    return datetime.now(timezone).date()


def parse_forecast_date(raw: str, base: date) -> date:
    value = " ".join(raw.lower().strip().split())
    if not value:
        raise DateParseError("date was empty")

    if value in {"today", "now", "current"}:
        return base
    if value == "tomorrow":
        return base + timedelta(days=1)
    if value in {"weekend", "this weekend"}:
        days_until_saturday = (5 - base.weekday()) % 7
        return base + timedelta(days=days_until_saturday)
    if value == "next weekend":
        days_until_saturday = (5 - base.weekday()) % 7
        return base + timedelta(days=days_until_saturday + 7)

    if match := re.fullmatch(r"in\s+(\d{1,2})\s+days?", value):
        return base + timedelta(days=int(match.group(1)))

    if match := re.fullmatch(r"next\s+([a-z]+)", value):
        weekday = WEEKDAYS.get(match.group(1))
        if weekday is not None:
            days = (weekday - base.weekday()) % 7
            return base + timedelta(days=days or 7)

    if value in WEEKDAYS:
        days = (WEEKDAYS[value] - base.weekday()) % 7
        return base + timedelta(days=days)

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DateParseError(
            "try `today`, `tomorrow`, `monday`, `next friday`, `in 3 days`, or `2026-07-20`"
        ) from exc


def validate_forecast_date(target: date, base: date) -> None:
    latest = base + timedelta(days=FORECAST_LIMIT_DAYS)
    if target < base:
        raise DateParseError("historical weather is not enabled yet")
    if target > latest:
        raise DateParseError(f"forecasts are available up to {FORECAST_LIMIT_DAYS} days ahead")


async def geocode_location(query: str, *, limit: int = 5) -> list[Location]:
    params = {
        "name": query,
        "count": limit,
        "language": "en",
        "format": "json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(GEOCODING_URL, params=params) as response:
            if response.status >= 400:
                raise WeatherError(f"geocoding failed with HTTP {response.status}")
            payload = await response.json()

    results = payload.get("results") or []
    return [
        Location(
            name=item["name"],
            admin1=item.get("admin1"),
            country=item.get("country") or "",
            latitude=item["latitude"],
            longitude=item["longitude"],
            timezone=item.get("timezone"),
        )
        for item in results
    ]


async def fetch_current_weather(location: Location) -> WeatherReport:
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "timezone": "auto",
        "temperature_unit": "celsius",
        "wind_speed_unit": "mph",
        "precipitation_unit": "mm",
        "current": ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
            ]
        ),
    }
    payload = await _fetch_forecast(params)
    current = payload.get("current") or {}
    return WeatherReport(
        location=location,
        kind="current",
        condition=condition_for(current.get("weather_code")),
        observed_at=current.get("time"),
        temperature=current.get("temperature_2m"),
        apparent_temperature=current.get("apparent_temperature"),
        humidity=current.get("relative_humidity_2m"),
        precipitation=current.get("precipitation"),
        wind_speed=current.get("wind_speed_10m"),
    )


async def fetch_daily_forecast(location: Location, target: date) -> WeatherReport:
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "timezone": "auto",
        "temperature_unit": "celsius",
        "wind_speed_unit": "mph",
        "precipitation_unit": "mm",
        "start_date": target.isoformat(),
        "end_date": target.isoformat(),
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "precipitation_probability_max",
                "wind_speed_10m_max",
                "sunrise",
                "sunset",
            ]
        ),
    }
    payload = await _fetch_forecast(params)
    daily = payload.get("daily") or {}
    if not daily.get("time"):
        raise WeatherError("no forecast data returned for that date")

    return WeatherReport(
        location=location,
        kind="forecast",
        condition=condition_for(_first(daily, "weather_code")),
        target_date=target,
        temp_min=_first(daily, "temperature_2m_min"),
        temp_max=_first(daily, "temperature_2m_max"),
        precipitation=_first(daily, "precipitation_sum"),
        rain_chance=_first(daily, "precipitation_probability_max"),
        wind_speed=_first(daily, "wind_speed_10m_max"),
        sunrise=_first(daily, "sunrise"),
        sunset=_first(daily, "sunset"),
    )


async def _fetch_forecast(params: dict) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(FORECAST_URL, params=params) as response:
            if response.status >= 400:
                text = await response.text()
                raise WeatherError(f"weather lookup failed with HTTP {response.status}: {text[:120]}")
            return await response.json()


def _first(payload: dict, key: str):
    values = payload.get(key)
    if not values:
        return None
    return values[0]
