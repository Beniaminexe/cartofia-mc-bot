import os
import asyncio

import discord
from discord.ext import commands, tasks
from mcstatus import JavaServer

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MC_HOST = os.getenv("MC_HOST", "127.0.0.1")
MC_PORT = int(os.getenv("MC_PORT", 25565))
SERVER_NAME = os.getenv("SERVER_NAME", "Cartofia")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")

if not DISCORD_TOKEN:
    raise SystemExit("DISCORD_TOKEN is not set in environment or .env file")

intents = discord.Intents.default()
intents.message_content = True  # needed for prefix commands
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)


def _get_status_blocking():
    """Blocking call to ping the Minecraft server (runs in a thread)."""
    server = JavaServer.lookup(f"{MC_HOST}:{MC_PORT}")
    return server.status()


async def get_status_async():
    """Run the blocking status call in a thread so we don't freeze the bot."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_status_blocking)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    if not update_presence.is_running():
        update_presence.start()


@tasks.loop(seconds=60)
async def update_presence():
    """Update the bot's Discord status every 60 seconds with player count."""
    try:
        status = await get_status_async()
        online = status.players.online
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{online} player(s) on {SERVER_NAME}",
        )
        await bot.change_presence(activity=activity)
    except Exception as e:
        print(f"Presence update failed: {e}")
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{SERVER_NAME} server offline",
        )
        try:
            await bot.change_presence(activity=activity)
        except Exception:
            pass


@bot.command(name="online", aliases=["players"])
async def online_command(ctx: commands.Context):
    """Show how many players are online (and sample of names if available)."""
    msg = await ctx.send("⏳ Checking Minecraft server status...")

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

    sample = status.players.sample or []
    player_names = [p.name for p in sample]

    if online == 0:
        description = "Nobody is online right now."
        colour = discord.Colour.red()
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
                "(Names not provided by server ping.)"
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


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)

