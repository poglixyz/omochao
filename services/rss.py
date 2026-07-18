from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import aiohttp
import discord

from services.db import (
    add_rss_subscription,
    get_seen_rss_item_keys,
    list_all_rss_subscriptions,
    mark_rss_items_seen,
)

log = logging.getLogger(__name__)

RSS_POLL_INTERVAL = 300
HTTP_TIMEOUT = 15
MAX_DESCRIPTION_LENGTH = 400

_rss_task: asyncio.Task | None = None


@dataclass(frozen=True)
class FeedItem:
    key: str
    title: str
    url: str | None
    published: str | None


@dataclass(frozen=True)
class FeedSnapshot:
    title: str
    items: list[FeedItem]


def ensure_rss_worker(bot: discord.Client) -> None:
    global _rss_task
    if _rss_task is not None and not _rss_task.done():
        return
    _rss_task = asyncio.create_task(_rss_worker(bot))


async def add_subscription(
    guild_id: int,
    channel_id: int,
    feed_url: str,
    created_by: int,
    title_override: str | None = None,
) -> tuple[int, str]:
    snapshot = await fetch_feed(feed_url)
    title = title_override.strip() if title_override else snapshot.title
    if not title:
        title = _fallback_feed_title(feed_url)
    subscription_id = add_rss_subscription(guild_id, channel_id, feed_url, title, created_by)
    mark_rss_items_seen(subscription_id, [item.key for item in snapshot.items])
    return subscription_id, title


async def fetch_feed(feed_url: str) -> FeedSnapshot:
    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
    headers = {"User-Agent": "omochao/1.0 (+https://github.com/poglixyz/omochao)"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(feed_url, ssl=False) as response:
            response.raise_for_status()
            content = await response.text()
    return _parse_feed(feed_url, content)


async def _rss_worker(bot: discord.Client) -> None:
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await _scan_subscriptions(bot)
        except Exception:
            log.exception("rss scan failed")
        await asyncio.sleep(RSS_POLL_INTERVAL)


async def _scan_subscriptions(bot: discord.Client) -> None:
    subscriptions = list_all_rss_subscriptions()
    for subscription in subscriptions:
        await _scan_subscription(bot, subscription)


async def _scan_subscription(bot: discord.Client, subscription) -> None:
    try:
        snapshot = await fetch_feed(subscription["feed_url"])
    except Exception as exc:
        log.warning("rss fetch failed for %s: %s", subscription["feed_url"], exc)
        return

    if not snapshot.items:
        return

    item_keys = [item.key for item in snapshot.items]
    seen = get_seen_rss_item_keys(int(subscription["id"]), item_keys)
    if not seen:
        # Existing feeds with no seen-history get bootstrapped silently.
        mark_rss_items_seen(int(subscription["id"]), item_keys)
        log.info("bootstrapped rss feed %s with %d items", subscription["feed_url"], len(item_keys))
        return

    unseen_items = [item for item in snapshot.items if item.key not in seen]
    if not unseen_items:
        return

    channel = bot.get_channel(int(subscription["channel_id"]))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(subscription["channel_id"]))
        except Exception as exc:
            log.warning("rss channel lookup failed for %s: %s", subscription["channel_id"], exc)
            return

    for item in reversed(unseen_items):
        embed = _build_item_embed(subscription["title"], item)
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            await channel.send(embed=embed)
        else:
            log.warning("rss subscription %s points to unsupported channel type", subscription["id"])
            return

    mark_rss_items_seen(int(subscription["id"]), [item.key for item in unseen_items])


def _build_item_embed(feed_title: str, item: FeedItem) -> discord.Embed:
    embed = discord.Embed(title=item.title, color=0x57A6FF)
    if item.url:
        embed.url = item.url
    if item.published:
        embed.description = _truncate(item.published, MAX_DESCRIPTION_LENGTH)
    embed.set_footer(text=f"RSS • {feed_title}")
    return embed


def _parse_feed(feed_url: str, content: str) -> FeedSnapshot:
    root = ET.fromstring(content)
    root_name = _local_name(root.tag)

    if root_name == "rss":
        channel = _find_child(root, "channel")
        if channel is None:
            raise ValueError("rss feed missing channel element")
        title = _child_text(channel, "title") or _fallback_feed_title(feed_url)
        items = [_parse_rss_item(item) for item in _iter_children(channel, "item")]
        return FeedSnapshot(title=title, items=[item for item in items if item is not None])

    if root_name == "feed":
        title = _child_text(root, "title") or _fallback_feed_title(feed_url)
        items = [_parse_atom_entry(entry) for entry in _iter_children(root, "entry")]
        return FeedSnapshot(title=title, items=[item for item in items if item is not None])

    raise ValueError(f"unsupported feed type: {root_name}")


def _parse_rss_item(item: ET.Element) -> FeedItem | None:
    title = _child_text(item, "title") or "Untitled"
    link = _child_text(item, "link")
    guid = _child_text(item, "guid")
    published = _child_text(item, "pubDate")
    key = _make_item_key(guid, link, title, published)
    return FeedItem(key=key, title=title, url=link, published=_format_published(published))


def _parse_atom_entry(entry: ET.Element) -> FeedItem | None:
    title = _child_text(entry, "title") or "Untitled"
    link = _atom_link(entry)
    item_id = _child_text(entry, "id")
    published = _child_text(entry, "published") or _child_text(entry, "updated")
    key = _make_item_key(item_id, link, title, published)
    return FeedItem(key=key, title=title, url=link, published=_format_published(published))


def _make_item_key(*parts: str | None) -> str:
    raw = "||".join(part.strip() for part in parts if part and part.strip())
    if not raw:
        raise ValueError("feed item has no stable identifier")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fallback_feed_title(feed_url: str) -> str:
    parsed = urlparse(feed_url)
    return parsed.netloc or feed_url


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _iter_children(element: ET.Element, name: str) -> Iterable[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _find_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in list(element):
        if _local_name(child.tag) == name:
            return child
    return None


def _child_text(element: ET.Element, *names: str) -> str | None:
    name_set = set(names)
    for child in list(element):
        if _local_name(child.tag) in name_set:
            text = child.text.strip() if child.text else ""
            if text:
                return text
    return None


def _atom_link(entry: ET.Element) -> str | None:
    fallback = None
    for child in list(entry):
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if not href:
            continue
        rel = child.attrib.get("rel")
        if rel in {None, "", "alternate"}:
            return href
        fallback = fallback or href
    return fallback


def _format_published(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt.strftime("%Y-%m-%d %H:%M %Z").strip()
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M %Z").strip()
    except Exception:
        return value.strip()


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}…"
