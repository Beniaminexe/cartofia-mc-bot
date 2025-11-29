# Cartofia Minecraft Status Bot

Small Discord bot that shows how many players are online on the Cartofia Minecraft server
and updates its Discord presence. Designed to run in Docker on the same host/CT as other bots.

---

## Features

- `!online` / `!players` command to show:
  - Online player count
  - Max slots
  - Sample list of player names (when the server exposes them)
- Discord presence text like: `3 player(s) on Cartofia`, auto-refreshed every 60s
- Configuration via `.env` file (no code editing needed)
- Docker + docker compose deployment

---

## Requirements

- Python is handled inside the Docker image
- Host machine needs:
  - Docker
  - docker compose v2
- A Discord bot application with a bot token
  - Message Content Intent enabled in the Discord Developer Portal
- A Minecraft **Java Edition** server (1.7+) reachable from the bot

---

## Configuration

Create a `.env` file (you can copy from `.env.example`):

```env
DISCORD_TOKEN=YOUR_DISCORD_BOT_TOKEN
MC_HOST=your.minecraft.server.host
MC_PORT=25565
SERVER_NAME=Cartofia
COMMAND_PREFIX=!
1
