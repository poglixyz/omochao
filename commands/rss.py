import logging

import discord
from discord import app_commands

from services.db import get_rss_subscription, list_rss_subscriptions, remove_rss_subscription
from services.rss import add_subscription, ensure_rss_worker

log = logging.getLogger(__name__)

HELP_INFO = {
    "name": "rss",
    "emoji": "📰",
    "short": "Subscribe server channels to RSS or Atom feeds",
    "usage": "`/rss subscribe` • `/rss list` • `/rss remove`",
    "params": [
        ("`url`", "The RSS or Atom feed URL to follow"),
        ("`channel`", "Where new feed items should be posted"),
        ("`name`", "Optional display name override for the feed"),
        ("`subscription_id`", "The numeric id shown by `/rss list`"),
    ],
    "examples": [
        "`/rss subscribe url:https://example.com/feed.xml channel:#news`",
        "`/rss list`",
        "`/rss remove subscription_id:3`",
    ],
    "notes": "Only members with Manage Server can change RSS subscriptions.",
}


def _require_manage_guild(interaction: discord.Interaction) -> bool:
    permissions = getattr(interaction.user, "guild_permissions", None)
    return permissions is not None and permissions.manage_guild


def _list_embed(guild: discord.Guild, rows) -> discord.Embed:
    embed = discord.Embed(
        title="RSS Subscriptions",
        color=0x57A6FF,
    )
    if not rows:
        embed.description = "no RSS feeds configured for this server"
        return embed

    for row in rows[:25]:
        embed.add_field(
            name=f"{row['id']}. {row['title']}",
            value=f"<#{row['channel_id']}>\n`{row['feed_url']}`",
            inline=False,
        )
    embed.set_footer(text=f"{len(rows)} subscription{'s' if len(rows) != 1 else ''}")
    return embed


def setup(tree: app_commands.CommandTree, bot: discord.Client) -> None:
    ensure_rss_worker(bot)

    rss_group = app_commands.Group(name="rss", description="Manage RSS feed subscriptions")

    @rss_group.command(name="subscribe", description="Subscribe a channel to an RSS or Atom feed")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        url="RSS or Atom feed URL",
        channel="The text channel to post feed updates into",
        name="Optional display name override for this feed",
    )
    async def rss_subscribe(
        interaction: discord.Interaction,
        url: str,
        channel: discord.TextChannel,
        name: str | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("this only works in a server", ephemeral=True)
            return
        if not _require_manage_guild(interaction):
            await interaction.response.send_message("you need Manage Server for this", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            subscription_id, title = await add_subscription(
                interaction.guild.id,
                channel.id,
                url.strip(),
                interaction.user.id,
                name,
            )
        except Exception as exc:
            log.warning("rss subscribe failed for %s: %s", url, exc)
            await interaction.followup.send(f"couldn't subscribe to that feed: {exc}", ephemeral=True)
            return

        await interaction.followup.send(
            f"subscribed **{title}** to {channel.mention} as feed id `{subscription_id}`",
            ephemeral=True,
        )

    @rss_group.command(name="list", description="List RSS subscriptions for this server")
    @app_commands.default_permissions(manage_guild=True)
    async def rss_list(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("this only works in a server", ephemeral=True)
            return
        if not _require_manage_guild(interaction):
            await interaction.response.send_message("you need Manage Server for this", ephemeral=True)
            return

        rows = list_rss_subscriptions(interaction.guild.id)
        await interaction.response.send_message(embed=_list_embed(interaction.guild, rows), ephemeral=True)

    @rss_group.command(name="remove", description="Remove an RSS subscription from this server")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(subscription_id="The subscription id shown by /rss list")
    async def rss_remove(interaction: discord.Interaction, subscription_id: int) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("this only works in a server", ephemeral=True)
            return
        if not _require_manage_guild(interaction):
            await interaction.response.send_message("you need Manage Server for this", ephemeral=True)
            return

        subscription = get_rss_subscription(interaction.guild.id, subscription_id)
        if subscription is None:
            await interaction.response.send_message("that RSS subscription does not exist here", ephemeral=True)
            return

        removed = remove_rss_subscription(interaction.guild.id, subscription_id)
        if not removed:
            await interaction.response.send_message("failed to remove that RSS subscription", ephemeral=True)
            return

        await interaction.response.send_message(
            f"removed RSS feed **{subscription['title']}** from <#{subscription['channel_id']}>",
            ephemeral=True,
        )

    tree.add_command(rss_group)
