import importlib
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

import discord

BuildEmbed = Callable[[], Awaitable[discord.Embed]]


@dataclass(frozen=True)
class StatusProvider:
    name: str
    aliases: tuple[str, ...]
    build_embed: BuildEmbed


def _normalise(value: str) -> str:
    return value.lower().strip()


def providers() -> list[StatusProvider]:
    found = []
    pkg_dir = Path(__file__).parent

    for _, name, _ in pkgutil.iter_modules([str(pkg_dir)]):
        module = importlib.import_module(f"services.game_status.{name}")
        provider = getattr(module, "PROVIDER", None)
        if provider:
            found.append(
                StatusProvider(
                    name=provider["name"],
                    aliases=tuple(_normalise(alias) for alias in provider["aliases"]),
                    build_embed=provider["build_embed"],
                )
            )

    found.sort(key=lambda item: item.name)
    return found


def get_provider(game: str) -> StatusProvider | None:
    game_key = _normalise(game)
    for provider in providers():
        if game_key == _normalise(provider.name) or game_key in provider.aliases:
            return provider
    return None


def supported_games() -> str:
    names = []
    for provider in providers():
        names.append(provider.name)
        names.extend(alias for alias in provider.aliases if alias != _normalise(provider.name))
    return ", ".join(sorted(set(names)))
