from __future__ import annotations

import logging
from datetime import date as date_type

import discord
from discord import app_commands, ui

from services.weather import (
    DateParseError,
    Location,
    WeatherError,
    WeatherReport,
    fetch_current_weather,
    fetch_daily_forecast,
    geocode_location,
    local_today,
    parse_forecast_date,
    validate_forecast_date,
)

log = logging.getLogger(__name__)

HELP_INFO = {
    "name": "weather",
    "emoji": "🌦️",
    "short": "Check current weather or a near-term forecast for a place",
    "usage": "`/weather location:<city/town/country> [date:<day>]`",
    "params": [
        ("`location`", "City, town, country, or a more specific place like `Glasgow, Scotland`"),
        ("`date`", "Optional forecast day: `today`, `tomorrow`, `monday`, `next friday`, `in 3 days`, `2026-07-20`"),
    ],
    "examples": [
        "`/weather location:Glasgow`",
        "`/weather location:Vancouver Island date:tomorrow`",
        "`/weather location:Toronto date:next friday`",
    ],
    "notes": "Powered by Open-Meteo. No date means current weather; adding a date returns a forecast.",
}


def setup(tree: app_commands.CommandTree, bot: discord.Client) -> None:

    @tree.command(name="weather", description="Check current weather or a near-term forecast")
    @app_commands.describe(
        location="City, town, country, or specific place to search",
        date="Optional: today, tomorrow, monday, next friday, in 3 days, 2026-07-20",
    )
    async def weather_cmd(
        interaction: discord.Interaction,
        location: str,
        date: str | None = None,
    ) -> None:
        await interaction.response.defer()

        try:
            locations = await geocode_location(location)
        except WeatherError as exc:
            await interaction.followup.send(f"weather lookup failed: {exc}", ephemeral=True)
            return

        if not locations:
            await interaction.followup.send(f"couldn't find `{location}`", ephemeral=True)
            return

        if len(locations) > 1:
            view = LocationSelectView(interaction.user.id, locations, date)
            embed = discord.Embed(
                title="Which place?",
                description=f"`{location}` matched a few places. pick one:",
                color=0x57A6FF,
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            return

        await _send_weather(interaction.followup.send, locations[0], date)


class LocationSelectView(ui.View):
    def __init__(self, user_id: int, locations: list[Location], raw_date: str | None) -> None:
        super().__init__(timeout=90)
        self.user_id = user_id
        self.locations = locations
        self.raw_date = raw_date
        self.add_item(LocationSelect(locations))


class LocationSelect(ui.Select):
    def __init__(self, locations: list[Location]) -> None:
        options = [
            discord.SelectOption(
                label=location.label[:100],
                description=_location_description(location),
                value=str(index),
            )
            for index, location in enumerate(locations[:10])
        ]
        super().__init__(placeholder="choose the location", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, LocationSelectView):
            await interaction.response.send_message("selector state broke, try the command again", ephemeral=True)
            return
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("that selector belongs to someone else", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        location = view.locations[int(self.values[0])]
        report = await _lookup_weather_for_interaction(interaction, location, view.raw_date)
        if report is None:
            return
        if interaction.channel is None:
            await interaction.followup.send("couldn't find the channel to post the weather in", ephemeral=True)
            return

        await interaction.channel.send(embed=_weather_embed(report))
        await interaction.followup.send(f"posted weather for **{location.label}**", ephemeral=True)


async def _send_weather(send, location: Location, raw_date: str | None, *, ephemeral: bool = False) -> None:
    report = await _lookup_weather_for_send(send, location, raw_date)
    if report is None:
        return

    await send(embed=_weather_embed(report), ephemeral=ephemeral)


async def _lookup_weather_for_interaction(
    interaction: discord.Interaction,
    location: Location,
    raw_date: str | None,
) -> WeatherReport | None:
    return await _lookup_weather_for_send(interaction.followup.send, location, raw_date)


async def _lookup_weather_for_send(send, location: Location, raw_date: str | None) -> WeatherReport | None:
    try:
        return await _lookup_weather(location, raw_date)
    except DateParseError as exc:
        await send(f"couldn't parse that date: {exc}", ephemeral=True)
        return None
    except WeatherError as exc:
        await send(f"weather lookup failed: {exc}", ephemeral=True)
        return None
    except Exception:
        log.exception("weather command failed for %s date=%r", location.label, raw_date)
        await send("weather lookup exploded, check the bot logs", ephemeral=True)
        return None


async def _lookup_weather(location: Location, raw_date: str | None) -> WeatherReport:
    if raw_date is None:
        return await fetch_current_weather(location)

    base = local_today(location)
    target = parse_forecast_date(raw_date, base)
    validate_forecast_date(target, base)
    return await fetch_daily_forecast(location, target)


def _weather_embed(report: WeatherReport) -> discord.Embed:
    if report.kind == "current":
        embed = discord.Embed(
            title=f"Weather in {report.location.label}",
            description=report.condition,
            color=0x57A6FF,
        )
        embed.add_field(name="temperature", value=_temp(report.temperature), inline=True)
        embed.add_field(name="feels like", value=_temp(report.apparent_temperature), inline=True)
        embed.add_field(name="humidity", value=_percent(report.humidity), inline=True)
        embed.add_field(name="wind", value=_wind(report.wind_speed), inline=True)
        embed.add_field(name="rain", value=_mm(report.precipitation), inline=True)
        if report.observed_at:
            embed.set_footer(text=f"Open-Meteo • observed {report.observed_at}")
        else:
            embed.set_footer(text="Open-Meteo")
        return embed

    embed = discord.Embed(
        title=f"Forecast for {report.location.label}",
        description=f"{_display_date(report.target_date)} • {report.condition}",
        color=0x57A6FF,
    )
    embed.add_field(name="temperature", value=f"{_temp(report.temp_min)} to {_temp(report.temp_max)}", inline=True)
    embed.add_field(name="rain chance", value=_percent(report.rain_chance), inline=True)
    embed.add_field(name="rain total", value=_mm(report.precipitation), inline=True)
    embed.add_field(name="wind", value=_wind(report.wind_speed), inline=True)
    embed.add_field(name="sunrise", value=_time(report.sunrise), inline=True)
    embed.add_field(name="sunset", value=_time(report.sunset), inline=True)
    embed.set_footer(text="Open-Meteo forecast")
    return embed


def _location_description(location: Location) -> str:
    bits = []
    if location.admin1:
        bits.append(location.admin1)
    if location.country:
        bits.append(location.country)
    if location.timezone:
        bits.append(location.timezone)
    return " • ".join(bits)[:100] or "Open-Meteo result"


def _display_date(value: date_type | None) -> str:
    if value is None:
        return "unknown date"
    return value.strftime("%A %d %B %Y")


def _time(value: str | None) -> str:
    if not value:
        return "n/a"
    return value.split("T")[-1]


def _temp(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}°C"


def _percent(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0f}%"


def _mm(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f} mm"


def _wind(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f} mph"
