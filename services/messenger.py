import aiohttp
from config import bot_token


async def send_dm(user_id: str, text: str) -> None:
    headers = {"Authorization": f"Bot {bot_token()}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(
            "https://discord.com/api/v10/users/@me/channels",
            json={"recipient_id": user_id},
        ) as r:
            r.raise_for_status()
            channel_id = (await r.json())["id"]

        async with session.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            json={"content": text},
        ) as r:
            r.raise_for_status()
