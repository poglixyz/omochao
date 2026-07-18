import importlib
import pkgutil
from pathlib import Path

import discord

from config import DISABLED_MODULES
from services.module_access import add_module_check


async def load_commands(tree: discord.app_commands.CommandTree, bot: discord.Client) -> None:
    """Auto-discover every module in commands/ and call its setup(tree, bot)."""
    pkg_dir = Path(__file__).parent
    for _, name, _ in pkgutil.iter_modules([str(pkg_dir)]):
        if name in DISABLED_MODULES:
            print(f"[commands] skipped disabled module: {name}")
            continue
        module = importlib.import_module(f"commands.{name}")
        if hasattr(module, "setup"):
            before = set(tree.get_commands())
            module.setup(tree, bot)
            after = set(tree.get_commands())
            for command in after - before:
                add_module_check(command, name)
            print(f"[commands] loaded: {name}")
