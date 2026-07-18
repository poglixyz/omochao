import asyncio
import logging
import time

import discord
from discord import app_commands

from services.db import (
    add_reminder,
    delete_reminder,
    get_pending_reminders,
    get_pending_reminders_for_user,
    get_user_default_light,
)
from services.ha import flash_light
from services.messenger import send_dm
from utils.duration import format_duration, parse_minutes

log = logging.getLogger(__name__)
MAX_LISTED_REMINDERS = 20

HELP_INFO = {
    "name": "remind",
    "emoji": "⏰",
    "short": "Set reminders and list your pending reminders",
    "usage": "`/remind ...` or `/reminder-list`",
    "params": [
        ("`time`", "When to fire — `10`, `30m`, `1h`, `1h30m`, `90s`, `1.5h`"),
        ("`message`", "What to remind about"),
        ("`flash`", "Flash the target user's configured light when it fires (default: on)"),
    ],
    "examples": [
        "`/remind time:30m message:check the oven`",
        "`/remind time:1h30m message:CS2 lobby flash:False`",
        "`/reminder-list`",
    ],
    "notes": "Reminders persist across restarts and `/reminder-list` only shows the caller's own reminders.",
}


def _flash_note(flash: bool, entity_id: str | None) -> str:
    if not flash:
        return ""
    if entity_id is None:
        return " (no default light configured)"
    return f" + light flash `{entity_id}` <a:hchao:1519564355186987038>"


def _truncate_message(message: str, limit: int = 90) -> str:
    if len(message) <= limit:
        return message
    return f"{message[: limit - 1]}…"


def _reminder_list_embed(user: discord.abc.User, rows) -> discord.Embed:
    embed = discord.Embed(
        title="Your Pending Reminders",
        color=0x5865F2,
    )

    if not rows:
        embed.description = "you have no pending reminders"
        return embed

    lines = []
    for index, row in enumerate(rows[:MAX_LISTED_REMINDERS], start=1):
        fire_at = int(row["fire_at"])
        flash_label = "flash" if row["flash"] else "no flash"
        lines.append(
            f"{index}. <t:{fire_at}:R> • <t:{fire_at}:f> [{flash_label}] {_truncate_message(row['message'])}"
        )

    embed.description = "\n".join(lines)
    embed.set_footer(
        text=(
            f"showing {min(len(rows), MAX_LISTED_REMINDERS)} of {len(rows)} reminder"
            f"{'s' if len(rows) != 1 else ''} • only visible to you"
        )
    )
    return embed


def setup(tree: app_commands.CommandTree, bot: discord.Client) -> None:

    @tree.command(name="remind", description="Set a reminder — fires as a DM with optional configured light flash")
    @app_commands.describe(
        time="When to fire: plain minutes (10), or 30m / 1h / 1h30m / 90s",
        message="What to remind you about",
        flash="Flash the target user's configured light when it fires (default: on)",
    )
    async def remind(
        interaction: discord.Interaction,
        time: str,
        message: str,
        flash: bool = True,
    ) -> None:
        minutes = parse_minutes(time)
        if minutes is None or minutes <= 0:
            await interaction.response.send_message(
                f"couldn't parse `{time}` — try `10`, `30m`, `1h`, `1h30m`, `90s`",
                ephemeral=True,
            )
            return

        target = interaction.user
        fire_at = time.time() + (minutes * 60)
        entity_id = get_user_default_light(interaction.guild_id, target.id) if flash else None
        reminder_id = add_reminder(
            str(target.id),
            message,
            fire_at,
            flash,
            interaction.guild_id,
            entity_id,
        )

        label = format_duration(minutes)
        await interaction.response.send_message(
            f"reminder set for {target.mention} — _{message}_ in **{label}**{_flash_note(flash, entity_id)}",
            ephemeral=True,
        )

        asyncio.create_task(_fire(reminder_id, str(target.id), message, fire_at, flash, entity_id))

    @tree.command(name="reminder-list", description="List your pending reminders")
    async def reminder_list(interaction: discord.Interaction) -> None:
        rows = get_pending_reminders_for_user(interaction.user.id)
        embed = _reminder_list_embed(interaction.user, rows)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def reload_reminders() -> None:
    rows = get_pending_reminders()
    loaded = 0
    for row in rows:
        asyncio.create_task(
            _fire(
                row["id"],
                row["user_id"],
                row["message"],
                row["fire_at"],
                bool(row["flash"]),
                row["light_entity_id"],
            )
        )
        loaded += 1
    if loaded:
        log.info("reloaded %d pending reminder%s from database", loaded, "s" if loaded != 1 else "")


async def _fire(
    reminder_id: int,
    user_id: str,
    message: str,
    fire_at: float,
    flash: bool,
    light_entity_id: str | None,
) -> None:
    delay = fire_at - time.time()
    if delay > 0:
        await asyncio.sleep(delay)
    try:
        if flash:
            if light_entity_id is not None:
                await flash_light(light_entity_id)
        await send_dm(user_id, f"⏰ Reminder: {message}")
        delete_reminder(reminder_id)
    except Exception:
        log.exception("reminder delivery failed (id=%d user=%s msg=%r)", reminder_id, user_id, message)
