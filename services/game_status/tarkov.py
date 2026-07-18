import logging
import time

import aiohttp
import discord

from config import TARKOV_STATUS_SERVERS

log = logging.getLogger(__name__)

TIMEOUT = 5


async def _query_server(server: dict) -> dict:
    started = time.monotonic()
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(server["url"], ssl=False) as response:
                await response.read()
                return {
                    "name": server["name"],
                    "url": server["url"],
                    "online": response.status < 500,
                    "status": response.status,
                    "latency_ms": round((time.monotonic() - started) * 1000),
                }
    except Exception as exc:
        log.warning("spt query failed for %s: %s", server["name"], exc)
        return {
            "name": server["name"],
            "url": server["url"],
            "online": False,
            "error": str(exc),
        }


async def build_embed() -> discord.Embed:
    embed = discord.Embed(title="SPT / Tarkov Servers", color=0xC7A25A)
    if not TARKOV_STATUS_SERVERS:
        embed.description = "no tarkov servers configured"
        return embed

    for server in TARKOV_STATUS_SERVERS:
        result = await _query_server(server)
        if result["online"]:
            embed.add_field(
                name=f"Online - {result['name']}",
                value=(
                    f"{result['url']}\n"
                    f"HTTP {result['status']} in {result['latency_ms']}ms"
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name=f"Offline - {result['name']}",
                value=f"{result['url']}\nserver offline or unreachable",
                inline=False,
            )

    return embed


PROVIDER = {
    "name": "tarkov",
    "aliases": ("tarkov", "spt"),
    "build_embed": build_embed,
}
