import logging

import discord
from discord import app_commands

from commands import load_commands
from commands.remind import reload_reminders
from config import FAST_SYNC_GUILDS, bot_token
from services.module_access import handle_module_access_error

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")


class ReminderBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        await load_commands(self.tree, self)
        self.tree.on_error = self.on_app_command_error
        for guild_id in FAST_SYNC_GUILDS:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        await self.tree.sync()
        logging.getLogger(__name__).info(
            "slash commands synced (global + %d guild%s)",
            len(FAST_SYNC_GUILDS),
            "s" if len(FAST_SYNC_GUILDS) != 1 else "",
        )

    async def on_ready(self) -> None:
        await reload_reminders()
        print(f"[bot] ready as {self.user} (id={self.user.id})")

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if await handle_module_access_error(interaction, error):
            return
        raise error


if __name__ == "__main__":
    ReminderBot().run(bot_token())
