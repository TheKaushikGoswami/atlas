# Atlas Round-Robin Bot

A turn-based geography "Atlas" game for Discord.

## Features
- Circular player order
- 2 strikes before elimination
- Validation against millions of geographic names (GeoNames + Census 2011)
- 30s turn timer

## Setup

### Windows (Local Dev)
1. Clone the repository.
2. Run `setup_windows.bat`.
3. Edit `.env` with your `DISCORD_TOKEN` and `DATABASE_URL`.
   * Note: You must have Postgres running locally or provide a remote URL.
4. Run the bot: `python main.py`

### VPS (Ubuntu 22.04+)
1. Clone the repository.
2. Run `bash deploy/deploy.sh`.
3. Edit `.env` with your production tokens.
4. Start the service: `sudo systemctl start atlas`.
