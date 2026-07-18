import asyncio
import json
import logging
import socket
import struct
from typing import Tuple

import discord

from config import MINECRAFT_STATUS_SERVERS

log = logging.getLogger(__name__)

TIMEOUT = 5.0
DEFAULT_PROTOCOL = 767


def _enc_varint(value: int) -> bytes:
    value &= 0xFFFFFFFF
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _enc_string(value: str) -> bytes:
    data = value.encode("utf-8")
    return _enc_varint(len(data)) + data


def _read_varint(sock: socket.socket) -> int:
    value = 0
    shift = 0
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise EOFError("connection closed")
        byte = chunk[0]
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return value
        shift += 7
        if shift > 35:
            raise ValueError("varint too large")


def _read_varint_from(buf: bytes, offset: int = 0) -> Tuple[int, int]:
    value = 0
    shift = 0
    idx = offset
    while True:
        byte = buf[idx]
        idx += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return value, idx
        shift += 7
        if shift > 35:
            raise ValueError("varint too large")


def _status_ping(host: str, port: int) -> dict:
    handshake = (
        _enc_varint(0)
        + _enc_varint(DEFAULT_PROTOCOL)
        + _enc_string(host)
        + struct.pack(">H", port)
        + _enc_varint(1)
    )
    packet = _enc_varint(len(handshake)) + handshake
    status_request = _enc_varint(1) + _enc_varint(0)

    with socket.create_connection((host, port), timeout=TIMEOUT) as sock:
        sock.sendall(packet + status_request)
        length = _read_varint(sock)
        data = bytearray()
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                raise EOFError("connection closed")
            data.extend(chunk)

        packet_id, idx = _read_varint_from(bytes(data))
        if packet_id != 0:
            raise ValueError(f"unexpected packet id {packet_id}")

        json_len, idx = _read_varint_from(bytes(data), idx)
        return json.loads(bytes(data)[idx : idx + json_len].decode("utf-8", "replace"))


async def _query_server(server: dict) -> dict:
    loop = asyncio.get_running_loop()
    try:
        status = await loop.run_in_executor(
            None, _status_ping, server["host"], server["port"]
        )
        players = status.get("players", {})
        sample = players.get("sample") or []
        version = status.get("version", {}).get("name", "unknown")
        return {
            "name": server["name"],
            "online": True,
            "current": players.get("online", 0),
            "max": players.get("max", 0),
            "players": [p.get("name", "?") for p in sample],
            "version": version,
        }
    except Exception as exc:
        log.warning("mc query failed for %s: %s", server["name"], exc)
        return {"name": server["name"], "online": False, "error": str(exc)}


async def build_embed() -> discord.Embed:
    embed = discord.Embed(title="Minecraft Servers", color=0x55FF55)
    if not MINECRAFT_STATUS_SERVERS:
        embed.description = "no minecraft servers configured"
        return embed

    results = await asyncio.gather(*[_query_server(s) for s in MINECRAFT_STATUS_SERVERS])

    for result in results:
        if result["online"]:
            player_list = ", ".join(result["players"]) if result["players"] else "nobody"
            value = (
                f"**{result['current']}/{result['max']}** players online\n"
                f"{result['version']}\n"
                f"Players: {player_list}"
            )
            embed.add_field(
                name=f"Online - {result['name']}",
                value=value,
                inline=False,
            )
        else:
            embed.add_field(
                name=f"Offline - {result['name']}",
                value="server offline or unreachable",
                inline=False,
            )

    return embed


PROVIDER = {
    "name": "minecraft",
    "aliases": ("minecraft", "mc"),
    "build_embed": build_embed,
}
