import json
import os
from pathlib import Path
from shutil import copyfile

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
LOCAL_CONFIG_DIR = BASE_DIR / "local"
FAST_SYNC_GUILDS_PATH = LOCAL_CONFIG_DIR / "fast_sync_guilds.txt"
FAST_SYNC_GUILDS_EXAMPLE_PATH = LOCAL_CONFIG_DIR / "fast_sync_guilds.txt.example"
HOME_ASSISTANT_CONFIG_PATH = LOCAL_CONFIG_DIR / "home_assistant.json"
HOME_ASSISTANT_CONFIG_EXAMPLE_PATH = LOCAL_CONFIG_DIR / "home_assistant.json.example"
GAME_STATUS_CONFIG_PATH = LOCAL_CONFIG_DIR / "game_status.json"
GAME_STATUS_CONFIG_EXAMPLE_PATH = LOCAL_CONFIG_DIR / "game_status.json.example"
DISABLED_MODULES_PATH = LOCAL_CONFIG_DIR / "disabled_modules.txt"
DISABLED_MODULES_EXAMPLE_PATH = LOCAL_CONFIG_DIR / "disabled_modules.txt.example"


def _ensure_local_file(path: Path, example_path: Path, hint: str) -> Path:
    LOCAL_CONFIG_DIR.mkdir(exist_ok=True)
    if not path.is_file():
        if not example_path.is_file():
            raise RuntimeError(f"missing config template: {example_path} ({hint})")
        copyfile(example_path, path)
    return path


def _load_json(path: Path, example_path: Path, hint: str) -> dict:
    return json.loads(_ensure_local_file(path, example_path, hint).read_text())


def _load_fast_sync_guilds(path: Path) -> list[int]:
    guild_ids: list[int] = []
    for raw_line in _ensure_local_file(
        path,
        FAST_SYNC_GUILDS_EXAMPLE_PATH,
        "copy the example file and add your guild ids",
    ).read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        guild_ids.append(int(line))
    return guild_ids


def _load_name_list(path: Path, example_path: Path, hint: str) -> set[str]:
    values: set[str] = set()
    for raw_line in _ensure_local_file(path, example_path, hint).read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        values.add(line)
    return values


FAST_SYNC_GUILDS = _load_fast_sync_guilds(FAST_SYNC_GUILDS_PATH)
HOME_ASSISTANT = _load_json(
    HOME_ASSISTANT_CONFIG_PATH,
    HOME_ASSISTANT_CONFIG_EXAMPLE_PATH,
    "copy the example file and add your Home Assistant settings",
)
GAME_STATUS = _load_json(
    GAME_STATUS_CONFIG_PATH,
    GAME_STATUS_CONFIG_EXAMPLE_PATH,
    "copy the example file and add your game status server settings",
)
DISABLED_MODULES = _load_name_list(
    DISABLED_MODULES_PATH,
    DISABLED_MODULES_EXAMPLE_PATH,
    "copy the example file and add any command modules to disable",
)
HA_URL = HOME_ASSISTANT.get("url")
HA_LIGHTS = HOME_ASSISTANT.get("lights") or {}
OFFICE_LIGHT = HA_LIGHTS.get("office")
MINECRAFT_STATUS_SERVERS = GAME_STATUS.get("minecraft") or []
TARKOV_STATUS_SERVERS = GAME_STATUS.get("tarkov") or []


def ha_token() -> str:
    token = os.getenv("HA_TOKEN")
    if not token:
        raise RuntimeError("HA_TOKEN not set in .env")
    return token


def bot_token() -> str:
    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("TOKEN not set in .env")
    return token
