import discord
from discord import app_commands

from services.game_status import get_provider, providers, supported_games

HELP_INFO = {
    "name": "status",
    "emoji": "📡",
    "short": "Check game server status by game",
    "usage": "`/status game:<game>`",
    "params": [
        ("game", "any loaded game status provider"),
    ],
    "examples": ["`/status minecraft`", "`/status tarkov`", "`/status spt`"],
    "notes": "Game-specific checks are auto-discovered from services/game_status/.",
}


async def _build_status_embed(game: str) -> discord.Embed:
    provider = get_provider(game)
    if provider:
        return await provider.build_embed()

    embed = discord.Embed(title="Unknown Game", color=0xED4245)
    embed.description = f"Supported games: {supported_games() or 'none loaded'}"
    return embed


def setup(tree: app_commands.CommandTree, bot: discord.Client) -> None:

    @tree.command(name="status", description="Check game server status")
    @app_commands.describe(game="Which game server group to check")
    async def status_cmd(
        interaction: discord.Interaction,
        game: str,
    ) -> None:
        await interaction.response.defer()
        embed = await _build_status_embed(game)
        await interaction.followup.send(embed=embed)

    @status_cmd.autocomplete("game")
    async def game_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        current = current.lower()
        choices = []
        for provider in providers():
            names = (provider.name, *provider.aliases)
            for name in sorted(set(names)):
                if not current or current in name:
                    choices.append(app_commands.Choice(name=name, value=name))
        return choices[:25]
