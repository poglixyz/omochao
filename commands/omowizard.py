import discord
from discord import app_commands, ui

from services.db import (
    clear_user_default_light,
    get_all_module_role_ids,
    get_user_default_light,
    get_user_default_light_for_scope,
    set_module_role_ids,
    set_user_default_light,
)
from services.module_access import command_modules

HCHAO_EMOTE = "<a:hchao:1519564355186987038>"

HELP_INFO = {
    "name": "omowizard",
    "emoji": "🛠️",
    "short": "Configure Omochao module role restrictions",
    "usage": "`/omowizard`",
    "params": [],
    "examples": ["`/omowizard`"],
    "notes": "Requires Manage Server. Configure module roles and per-user reminder lights.",
}


def _welcome_embed() -> discord.Embed:
    return discord.Embed(
        title="Omochao Config Wizard",
        description=(
            "Welcome to the omochao config wizard, select from the buttons below "
            f"what you would like to change {HCHAO_EMOTE}"
        ),
        color=0x57F287,
    )


def _role_list(guild: discord.Guild, role_ids: set[int]) -> str:
    if not role_ids:
        return "everyone"
    names = []
    for role_id in sorted(role_ids):
        role = guild.get_role(role_id)
        names.append(role.mention if role else f"`missing role {role_id}`")
    return ", ".join(names)


def _embed(guild: discord.Guild, selected_module: str | None = None) -> discord.Embed:
    rules = get_all_module_role_ids(guild.id)
    embed = discord.Embed(
        title="Omochao Config Wizard",
        description="pick a module, then choose the roles allowed to use it",
        color=0x57F287,
    )
    for module in command_modules():
        prefix = "▶ " if module == selected_module else ""
        embed.add_field(
            name=f"{prefix}/{module}",
            value=_role_list(guild, rules.get(module, set())),
            inline=False,
        )
    embed.set_footer(text="no roles selected = unrestricted")
    return embed


def _user_label(guild: discord.Guild, user_id: int | None) -> str:
    if user_id is None:
        return "none selected"
    member = guild.get_member(user_id)
    return member.mention if member is not None else f"<@{user_id}>"


def _light_scope_label(scope: str) -> str:
    return "global" if scope == "global" else "this server"


def _scope_guild_id(guild: discord.Guild, scope: str) -> int | None:
    return None if scope == "global" else guild.id


def _light_embed(
    guild: discord.Guild,
    selected_user_id: int | None = None,
    selected_scope: str = "server",
) -> discord.Embed:
    server_entity = (
        get_user_default_light_for_scope(guild.id, selected_user_id)
        if selected_user_id is not None
        else None
    )
    global_entity = (
        get_user_default_light_for_scope(None, selected_user_id)
        if selected_user_id is not None
        else None
    )
    effective_entity = (
        get_user_default_light(guild.id, selected_user_id)
        if selected_user_id is not None
        else None
    )
    embed = discord.Embed(
        title="Reminder Light Defaults",
        description="pick a user, choose this-server or global scope, then set or clear their Home Assistant light entity",
        color=0x57F287,
    )
    embed.add_field(name="user", value=_user_label(guild, selected_user_id), inline=False)
    embed.add_field(name="selected scope", value=_light_scope_label(selected_scope), inline=False)
    embed.add_field(name="this server", value=f"`{server_entity}`" if server_entity else "none", inline=True)
    embed.add_field(name="global", value=f"`{global_entity}`" if global_entity else "none", inline=True)
    embed.add_field(name="effective", value=f"`{effective_entity}`" if effective_entity else "none", inline=False)
    return embed


class ModuleSelect(ui.Select):
    def __init__(self, selected_module: str | None) -> None:
        options = [
            discord.SelectOption(
                label=f"/{module}",
                value=module,
                default=module == selected_module,
            )
            for module in command_modules()[:25]
        ]
        super().__init__(
            placeholder="choose a module",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        module = self.values[0]
        view = WizardView(module)
        await interaction.response.edit_message(embed=_embed(interaction.guild, module), view=view)


class RoleRestrictionSelect(ui.RoleSelect):
    def __init__(self, selected_module: str | None) -> None:
        self.selected_module = selected_module
        super().__init__(
            placeholder="allowed roles for selected module",
            min_values=0,
            max_values=25,
            disabled=selected_module is None,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.selected_module is None:
            await interaction.response.send_message("choose a module first", ephemeral=True)
            return
        role_ids = [role.id for role in self.values]
        set_module_role_ids(interaction.guild_id, self.selected_module, role_ids)
        view = WizardView(self.selected_module)
        await interaction.response.edit_message(
            embed=_embed(interaction.guild, self.selected_module),
            view=view,
        )


class WizardHomeView(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=180)

    @ui.button(label="module permissions", style=discord.ButtonStyle.primary)
    async def module_permissions(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=_embed(interaction.guild),
            view=WizardView(),
        )

    @ui.button(label="reminder lights", style=discord.ButtonStyle.primary)
    async def reminder_lights(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=_light_embed(interaction.guild),
            view=LightWizardView(),
        )


class WizardView(ui.View):
    def __init__(self, selected_module: str | None = None) -> None:
        super().__init__(timeout=180)
        self.selected_module = selected_module
        self.add_item(ModuleSelect(selected_module))
        self.add_item(RoleRestrictionSelect(selected_module))

    @ui.button(label="unrestrict", style=discord.ButtonStyle.secondary)
    async def clear(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.selected_module is None:
            await interaction.response.send_message("choose a module first", ephemeral=True)
            return
        set_module_role_ids(interaction.guild_id, self.selected_module, [])
        view = WizardView(self.selected_module)
        await interaction.response.edit_message(
            embed=_embed(interaction.guild, self.selected_module),
            view=view,
        )

    @ui.button(label="refresh", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=_embed(interaction.guild, self.selected_module),
            view=WizardView(self.selected_module),
        )

    @ui.button(label="back", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=_welcome_embed(),
            view=WizardHomeView(),
        )


class ReminderUserSelect(ui.UserSelect):
    def __init__(self, selected_user_id: int | None, selected_scope: str) -> None:
        self.selected_user_id = selected_user_id
        self.selected_scope = selected_scope
        super().__init__(
            placeholder="choose a reminder user",
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        user = self.values[0]
        selected_user_id = user.id
        await interaction.response.edit_message(
            embed=_light_embed(interaction.guild, selected_user_id, self.selected_scope),
            view=LightWizardView(selected_user_id, self.selected_scope),
        )


class ReminderLightScopeSelect(ui.Select):
    def __init__(self, selected_user_id: int | None, selected_scope: str) -> None:
        self.selected_user_id = selected_user_id
        options = [
            discord.SelectOption(
                label="this server",
                value="server",
                description="only this Discord server",
                default=selected_scope == "server",
            ),
            discord.SelectOption(
                label="global",
                value="global",
                description="fallback for this user across servers",
                default=selected_scope == "global",
            ),
        ]
        super().__init__(
            placeholder="choose light scope",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected_scope = self.values[0]
        await interaction.response.edit_message(
            embed=_light_embed(interaction.guild, self.selected_user_id, selected_scope),
            view=LightWizardView(self.selected_user_id, selected_scope),
        )


class ReminderLightModal(ui.Modal, title="Set Reminder Light"):
    entity_id = ui.TextInput(
        label="Home Assistant light entity",
        placeholder="light.office_light",
        max_length=128,
    )

    def __init__(self, guild_id: int | None, selected_user_id: int, scope: str) -> None:
        super().__init__()
        self.guild_id = guild_id
        self.selected_user_id = selected_user_id
        self.scope = scope
        current = get_user_default_light_for_scope(guild_id, selected_user_id)
        if current is not None:
            self.entity_id.default = current

    async def on_submit(self, interaction: discord.Interaction) -> None:
        entity_id = str(self.entity_id).strip()
        if not entity_id.startswith("light.") or any(char.isspace() for char in entity_id):
            await interaction.response.send_message(
                "use a Home Assistant light entity id like `light.office_light`",
                ephemeral=True,
            )
            return

        set_user_default_light(self.guild_id, self.selected_user_id, entity_id)
        await interaction.response.send_message(
            f"set {_light_scope_label(self.scope)} reminder light for <@{self.selected_user_id}> to `{entity_id}`",
            ephemeral=True,
        )


class LightWizardView(ui.View):
    def __init__(self, selected_user_id: int | None = None, selected_scope: str = "server") -> None:
        super().__init__(timeout=180)
        self.selected_user_id = selected_user_id
        self.selected_scope = selected_scope
        self.add_item(ReminderUserSelect(selected_user_id, selected_scope))
        self.add_item(ReminderLightScopeSelect(selected_user_id, selected_scope))

    @ui.button(label="set light", style=discord.ButtonStyle.primary)
    async def set_light(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.selected_user_id is None:
            await interaction.response.send_message("choose a user first", ephemeral=True)
            return
        await interaction.response.send_modal(
            ReminderLightModal(
                _scope_guild_id(interaction.guild, self.selected_scope),
                self.selected_user_id,
                self.selected_scope,
            )
        )

    @ui.button(label="clear light", style=discord.ButtonStyle.secondary)
    async def clear_light(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.selected_user_id is None:
            await interaction.response.send_message("choose a user first", ephemeral=True)
            return
        clear_user_default_light(
            _scope_guild_id(interaction.guild, self.selected_scope),
            self.selected_user_id,
        )
        await interaction.response.edit_message(
            embed=_light_embed(interaction.guild, self.selected_user_id, self.selected_scope),
            view=LightWizardView(self.selected_user_id, self.selected_scope),
        )

    @ui.button(label="back", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=_welcome_embed(),
            view=WizardHomeView(),
        )

    @ui.button(label="refresh", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=_light_embed(interaction.guild, self.selected_user_id, self.selected_scope),
            view=LightWizardView(self.selected_user_id, self.selected_scope),
        )


def setup(tree: app_commands.CommandTree, bot: discord.Client) -> None:

    @tree.command(name="omowizard", description="Configure Omochao module role restrictions")
    @app_commands.default_permissions(manage_guild=True)
    async def omowizard(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("this only works in a server", ephemeral=True)
            return
        permissions = getattr(interaction.user, "guild_permissions", None)
        if permissions is None or not permissions.manage_guild:
            await interaction.response.send_message("you need Manage Server for this", ephemeral=True)
            return

        await interaction.response.send_message(
            embed=_welcome_embed(),
            view=WizardHomeView(),
            ephemeral=True,
        )
