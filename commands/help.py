import importlib
import pkgutil
from pathlib import Path

import discord
from discord import app_commands, ui

from services.module_access import user_has_module_access


def _collect_help(interaction: discord.Interaction) -> list[dict]:
    """Gather HELP_INFO from every command module that defines one."""
    entries = []
    pkg_dir = Path(__file__).parent
    for _, name, _ in pkgutil.iter_modules([str(pkg_dir)]):
        if name == "help":
            continue
        module = importlib.import_module(f"commands.{name}")
        info = getattr(module, "HELP_INFO", None)
        if info and user_has_module_access(interaction, name):
            entries.append(info)
    entries.sort(key=lambda e: e["name"])
    return entries


def _home_embed(entries: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title="Omochao — Commands",
        description="tap a button below to see full details on any command",
        color=0x5865F2,
    )
    for e in entries:
        embed.add_field(
            name=f"{e['emoji']} /{e['name']}",
            value=e["short"],
            inline=False,
        )
    if not entries:
        embed.add_field(name="no commands loaded", value="something went wrong", inline=False)
    embed.set_footer(text=f"{len(entries)} command{'s' if len(entries) != 1 else ''} available")
    return embed


def _detail_embed(info: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"{info['emoji']} /{info['name']}",
        description=info["short"],
        color=0x5865F2,
    )
    embed.add_field(name="usage", value=info["usage"], inline=False)

    if info.get("params"):
        param_lines = "\n".join(f"**{name}** — {desc}" for name, desc in info["params"])
        embed.add_field(name="parameters", value=param_lines, inline=False)

    if info.get("examples"):
        embed.add_field(name="examples", value="\n".join(info["examples"]), inline=False)

    if info.get("notes"):
        embed.add_field(name="notes", value=info["notes"], inline=False)

    return embed


class HomeView(ui.View):
    def __init__(self, entries: list[dict]) -> None:
        super().__init__(timeout=120)
        self.entries = entries
        for entry in entries:
            self.add_item(CommandButton(entry, entries))


class CommandButton(ui.Button):
    def __init__(self, entry: dict, all_entries: list[dict]) -> None:
        super().__init__(
            label=f"/{entry['name']}",
            emoji=entry["emoji"],
            style=discord.ButtonStyle.primary,
        )
        self.entry = entry
        self.all_entries = all_entries

    async def callback(self, interaction: discord.Interaction) -> None:
        embed = _detail_embed(self.entry)
        view = DetailView(self.all_entries)
        await interaction.response.edit_message(embed=embed, view=view)


class DetailView(ui.View):
    def __init__(self, entries: list[dict]) -> None:
        super().__init__(timeout=120)
        self.entries = entries

    @ui.button(label="back", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: ui.Button) -> None:
        embed = _home_embed(self.entries)
        view = HomeView(self.entries)
        await interaction.response.edit_message(embed=embed, view=view)


def setup(tree: app_commands.CommandTree, bot: discord.Client) -> None:

    @tree.command(name="help", description="Browse all Omochao commands")
    async def help_cmd(interaction: discord.Interaction) -> None:
        entries = _collect_help(interaction)
        embed = _home_embed(entries)
        view = HomeView(entries)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
