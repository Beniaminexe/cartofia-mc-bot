import os
import asyncio

import discord
from discord.ext import commands, tasks
from mcstatus import JavaServer
from mcrcon import MCRcon

# ---- Environment config ----

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MC_HOST = os.getenv("MC_HOST", "127.0.0.1")
MC_PORT = int(os.getenv("MC_PORT", 25565))
SERVER_NAME = os.getenv("SERVER_NAME", "Cartofia")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")

RCON_HOST = os.getenv("RCON_HOST", MC_HOST)
RCON_PORT = int(os.getenv("RCON_PORT", 25575))
RCON_PASSWORD = os.getenv("RCON_PASSWORD")

STATUS_CHANNEL_ID_ENV = os.getenv("STATUS_CHANNEL_ID")
STATUS_CHANNEL_ID = int(STATUS_CHANNEL_ID_ENV) if STATUS_CHANNEL_ID_ENV else None

if not DISCORD_TOKEN:
    raise SystemExit("DISCORD_TOKEN is not set in environment or .env file")

RCON_ENABLED = bool(RCON_PASSWORD)

# ---- Discord setup ----

intents = discord.Intents.default()
intents.message_content = True  # needed for prefix commands
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# Tracks last known "server online/offline" state for announcements
last_server_online: bool | None = None


# ---- Minecraft status helpers ----

def _get_status_blocking():
    """Blocking call to ping the Minecraft server (runs in thread)."""
    server = JavaServer.lookup(f"{MC_HOST}:{MC_PORT}")
    return server.status()


async def get_status_async():
    """Run the blocking status call in a thread so we don't freeze the bot."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_status_blocking)


def _rcon_list_blocking() -> str:
    """Blocking RCON /list call."""
    with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as mcr:
        # RCON commands do NOT take the leading slash
        resp = mcr.command("list")
        return resp


async def rcon_list_async() -> str | None:
    """Async wrapper around the blocking RCON /list call."""
    if not RCON_ENABLED:
        return None

    loop = asyncio.get_running_loop()
    try:
        resp = await loop.run_in_executor(None, _rcon_list_blocking)
        return resp
    except Exception as e:
        print(f"RCON list failed: {e}")
        return None


def parse_rcon_list(resp: str) -> list[str]:
    """
    Parse player names out of a typical /list response, e.g.:

    'There are 2 of a max of 20 players online: Steve, Alex'
    'There are 0 of a max of 20 players online.'
    """
    if ":" not in resp:
        return []

    _, after_colon = resp.split(":", 1)
    names = [n.strip() for n in after_colon.split(",") if n.strip()]
    return names


# ---- Events ----

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    if not update_presence.is_running():
        update_presence.start()


# ---- Background task: presence + channel topic + announcements ----

@tasks.loop(seconds=60)
async def update_presence():
    global last_server_online

    # Default values
    server_online = False
    online = 0
    max_players = 0

    # Try to ping the server
    try:
        status = await get_status_async()
        online = status.players.online
        max_players = status.players.max
        server_online = True
    except Exception as e:
        print(f"Presence update: server unreachable: {e}")

    # Update bot presence (the little status bubble + text)
    if server_online:
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{online} player(s) on {SERVER_NAME}",
        )
        await bot.change_presence(
            status=discord.Status.online,   # green bubble
            activity=activity,
        )
    else:
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{SERVER_NAME} server offline",
        )
        # dnd gives a red-ish bubble
        await bot.change_presence(
            status=discord.Status.dnd,
            activity=activity,
        )

    # Update channel topic with players: x/y (or offline)
    if STATUS_CHANNEL_ID is not None:
        channel = bot.get_channel(STATUS_CHANNEL_ID)
        if isinstance(channel, discord.TextChannel):
            if server_online:
                topic = f"Players: {online}/{max_players} | {SERVER_NAME}"
            else:
                topic = f"{SERVER_NAME} server offline"

            try:
                if channel.topic != topic:  # avoid useless edits
                    await channel.edit(topic=topic, reason="Update Minecraft status")
            except Exception as e:
                print(f"Failed to update channel topic: {e}")

    # Announce state changes (online <-> offline) in the same channel
    if STATUS_CHANNEL_ID is not None:
        if last_server_online is None:
            # First run, just set baseline
            last_server_online = server_online
        elif last_server_online != server_online:
            last_server_online = server_online
            channel = bot.get_channel(STATUS_CHANNEL_ID)
            if isinstance(channel, discord.TextChannel):
                try:
                    if server_online:
                        await channel.send("🟢 **Cartofia server is now online!**")
                        await channel.send("IP **answers-advertising.gl.joinmc.link**")
                    else:
                        await channel.send("🔴 **Cartofia server is now offline!**")
                except Exception as e:
                    print(f"Failed to send status change message: {e}")
    else:
        last_server_online = server_online


# ---- Commands ----

@bot.command(name="online", aliases=["players"])
async def online_command(ctx: commands.Context):
    """Show how many players are online (with exact names via RCON if available)."""
    msg = await ctx.send("⏳ Checking Minecraft server status...")

    # Try to ping the Minecraft server
    try:
        status = await get_status_async()
    except Exception as e:
        await msg.edit(
            content=(
                f"🔴 Could not reach the server at `{MC_HOST}:{MC_PORT}`.\n"
                f"```{e}```"
            )
        )
        return

    online = status.players.online
    max_players = status.players.max

    # First try RCON for exact names
    player_names: list[str] = []
    if online > 0 and RCON_ENABLED:
        rcon_resp = await rcon_list_async()
        if rcon_resp:
            player_names = parse_rcon_list(rcon_resp)

    # Fallback to mcstatus sample if RCON gives nothing
    if online > 0 and not player_names:
        sample = status.players.sample or []
        player_names = [p.name for p in sample]

    # Build embed
    if online == 0:
        description = "Nobody is online right now."
        colour = discord.Colour.orange()  # empty/quiet
    else:
        colour = discord.Colour.green()
        if player_names:
            description = (
                f"**{online}/{max_players}** players online:\n"
                + ", ".join(player_names)
            )
        else:
            description = (
                f"**{online}/{max_players}** players online.\n"
                "(Player names could not be retrieved.)"
            )

    embed = discord.Embed(
        title=f"🌐 {SERVER_NAME} Minecraft Status",
        description=description,
        colour=colour,
    )
    embed.add_field(
        name="Address",
        value=f"`{MC_HOST}:{MC_PORT}`",
        inline=False,
    )

    await msg.edit(content=None, embed=embed)


# ---- Main ----

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
