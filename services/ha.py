import asyncio
import aiohttp
from config import HA_URL, ha_token


def _headers() -> dict:
    return {"Authorization": f"Bearer {ha_token()}", "Content-Type": "application/json"}


async def _get_state(session: aiohttp.ClientSession, entity_id: str) -> dict:
    async with session.get(f"{HA_URL}/api/states/{entity_id}", ssl=False) as r:
        r.raise_for_status()
        return await r.json()


async def _restore(session: aiohttp.ClientSession, entity_id: str, state: dict) -> None:
    if state["state"] == "off":
        async with session.post(
            f"{HA_URL}/api/services/light/turn_off",
            json={"entity_id": entity_id},
            ssl=False,
        ):
            pass
        return

    attrs = state["attributes"]
    payload: dict = {"entity_id": entity_id}

    if "brightness" in attrs:
        payload["brightness"] = attrs["brightness"]

    mode = attrs.get("color_mode")
    if mode == "rgbw" and "rgbw_color" in attrs:
        payload["rgbw_color"] = attrs["rgbw_color"]
    elif mode == "rgb" and "rgb_color" in attrs:
        payload["rgb_color"] = attrs["rgb_color"]
    elif mode == "color_temp" and "color_temp_kelvin" in attrs:
        payload["color_temp_kelvin"] = attrs["color_temp_kelvin"]

    async with session.post(
        f"{HA_URL}/api/services/light/turn_on", json=payload, ssl=False
    ):
        pass


async def flash_light(entity_id: str, pulses: int = 6, interval: float = 0.35) -> None:
    if not HA_URL:
        print("[ha] Home Assistant URL not configured; skipping flash")
        return
    async with aiohttp.ClientSession(headers=_headers()) as session:
        try:
            prev = await _get_state(session, entity_id)
        except Exception as e:
            print(f"[ha] could not read light state for {entity_id}: {e}")
            return

        for _ in range(pulses):
            async with session.post(
                f"{HA_URL}/api/services/light/turn_on",
                json={
                    "entity_id": entity_id,
                    "rgbw_color": [255, 0, 0, 0],
                    "brightness_pct": 100,
                    "transition": 0,
                },
                ssl=False,
            ):
                pass
            await asyncio.sleep(interval)
            await _restore(session, entity_id, prev)
            await asyncio.sleep(interval)

        await asyncio.sleep(0.2)
        await _restore(session, entity_id, prev)
