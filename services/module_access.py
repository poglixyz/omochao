import inspect
import pkgutil
from pathlib import Path

import discord
from discord import app_commands

from config import DISABLED_MODULES
from services.db import get_module_role_ids

PROTECTED_MODULES = {"omowizard"}


class ModuleAccessDenied(app_commands.CheckFailure):
    def __init__(self, module: str, role_ids: set[int]) -> None:
        self.module = module
        self.role_ids = role_ids
        super().__init__(f"/{module} is restricted")


def command_modules() -> list[str]:
    pkg_dir = Path(__file__).resolve().parent.parent / "commands"
    modules = [
        name
        for _, name, _ in pkgutil.iter_modules([str(pkg_dir)])
        if name not in {"__init__"} and name not in PROTECTED_MODULES and name not in DISABLED_MODULES
    ]
    modules.sort()
    return modules


def user_has_module_access(interaction: discord.Interaction, module: str) -> bool:
    if module in PROTECTED_MODULES:
        return True
    if interaction.guild_id is None:
        return True

    allowed_role_ids = get_module_role_ids(interaction.guild_id, module)
    if not allowed_role_ids:
        return True

    user = interaction.user
    if not isinstance(user, discord.Member):
        return False
    user_role_ids = {role.id for role in user.roles}
    return bool(allowed_role_ids & user_role_ids)


def module_access_check(module: str):
    async def predicate(interaction: discord.Interaction) -> bool:
        if user_has_module_access(interaction, module):
            return True
        role_ids = get_module_role_ids(interaction.guild_id or 0, module)
        raise ModuleAccessDenied(module, role_ids)

    return predicate


def add_module_check(command: app_commands.Command | app_commands.Group, module: str) -> None:
    if module in PROTECTED_MODULES:
        return

    if hasattr(command, "add_check"):
        command.add_check(module_access_check(module))
    for child in getattr(command, "commands", []):
        add_module_check(child, module)


async def handle_module_access_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> bool:
    original = getattr(error, "original", error)
    if not isinstance(original, ModuleAccessDenied):
        return False

    role_mentions = ", ".join(f"<@&{role_id}>" for role_id in sorted(original.role_ids))
    message = f"`/{original.module}` is restricted to: {role_mentions or 'configured roles'}"

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
    return True


def maybe_await(value):
    if inspect.isawaitable(value):
        return value
    return None
