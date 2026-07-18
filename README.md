# omochao

`omochao` is a modular Python Discord bot.
It started as a reminder bot and is designed to grow by adding new command modules.

## how config works

Most local config lives in `local/`.

The bot will auto-create any missing local config file from its matching `.example` file on startup.

- `.env`
  - `TOKEN=...`
  - `HA_TOKEN=...` if you want Home Assistant light flashing
- `local/fast_sync_guilds.txt`
  - optional
  - one guild id per line
  - used for faster slash-command sync in specific servers
- `local/home_assistant.json`
  - optional
  - used for Home Assistant reminder light flashing
  - shape:

```json
{
  "url": "https://your-home-assistant.example",
  "lights": {
    "office": "light.office_light"
  }
}
```

- `local/game_status.json`
  - optional
  - used by `/status` providers
  - shape:

```json
{
  "minecraft": [
    {
      "name": "Example Server",
      "host": "mc.example.com",
      "port": 25565
    }
  ],
  "tarkov": [
    {
      "name": "Example Tarkov",
      "url": "https://example.com:6969/"
    }
  ]
}
```

- `local/disabled_modules.txt`
  - optional
  - one module name per line, without `.py`
  - anything listed here will not be loaded when the bot starts

## how to disable modules

There are two ways:

1. Restrict a module inside Discord with `/omowizard`
   - this is per-server
   - you can limit a module to specific roles
   - leaving the role list empty means the module is open to everyone

2. Fully disable a module with `local/disabled_modules.txt`
   - example:

```txt
weather
status
```

   - then restart the bot

`omowizard` itself is kept available separately so you do not lock yourself out of module controls.

## how to add new modules

Adding command modules is already automatic on startup.

To add one:

1. Drop a new `commands/<name>.py` file into the repo.
2. Export a `setup(tree, bot)` function that registers the slash command.
3. Restart the bot.

Example:

```python
def setup(tree: app_commands.CommandTree, bot: discord.Client) -> None:
    ...
```

There is no manual command registry to edit. `commands/__init__.py` auto-discovers modules in `commands/` and loads them on boot.

## running the bot

```bash
python main.py
```

## keeping it alive after closing the terminal

### option 1: tmux

Start a tmux session, run the bot inside it, and detach:

```bash
tmux new -s omochao
python main.py
```

Detach with `Ctrl+B` then `D`.

Reattach later with:

```bash
tmux attach -t omochao
```

### option 2: systemd user service

There is no tracked live `omochao.service` file in the repo. Each user should create their own user service with their own paths.

An example service file is included as [omochao.service.example](omochao.service.example).

Copy it to:

```bash
mkdir -p ~/.config/systemd/user
cp omochao.service.example ~/.config/systemd/user/omochao.service
```

Edit the paths, then enable it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now omochao
```

Check status with:

```bash
systemctl --user status omochao
```
