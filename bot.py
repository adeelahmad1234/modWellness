"""modWellness: tracks voice and game time for members who opt in with /track on."""
import datetime as dt
import os
import random
import time
from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import db
import messages as msg

load_dotenv()
TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL_ID") or 0)  # 0 = no weekly post

# --- Settings ---
WEEK = 7 * 24 * 60 * 60
LEADERBOARD_SIZE = 10
TOP_GAMES_IN_STATS = 5
COUNT_AFK_CHANNEL = False   # time in the server's AFK channel doesn't count
WEEKLY_POST_DAY = 0         # 0 = Monday ... 6 = Sunday
WEEKLY_POST_TIME = dt.time(hour=17, minute=0, tzinfo=dt.timezone.utc)
WATER_EVERY_MINUTES = 60     # of continuous time in voice or a game
EXERCISE_EVERY_MINUTES = 120

# Only what we use. presences + members must also be ON in the Developer Portal.
intents = discord.Intents.none()
intents.guilds = True
intents.voice_states = True
intents.presences = True
intents.members = True


class TrackerBot(discord.Client):
    def __init__(self):
        # Mentions show as names but never ping anyone.
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await db.connect()
        # Syncing to one server makes slash commands show up instantly.
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        if LEADERBOARD_CHANNEL_ID:
            weekly_leaderboard.start()


client = TrackerBot()


# --- Helpers ---

def fmt_duration(seconds: float) -> str:
    hours, minutes = divmod(int(seconds // 60), 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def tracked_channel(member: discord.Member, state: Optional[discord.VoiceState]):
    """The voice channel that counts as tracked time, or None."""
    channel = state.channel if state else None
    if channel is None or (channel == member.guild.afk_channel and not COUNT_AFK_CHANNEL):
        return None
    return channel


def current_game(member: discord.Member) -> Optional[str]:
    for activity in member.activities:
        if activity.type == discord.ActivityType.playing:
            return activity.name
    return None


async def start_current_sessions(member: discord.Member):
    """Start sessions for whatever the member is doing right now."""
    if channel := tracked_channel(member, member.voice):
        await db.start_session(member.id, "voice", channel.name)
    if game := current_game(member):
        await db.start_session(member.id, "game", game)


async def build_leaderboard(kind: str) -> str:
    header = msg.LEADERBOARD_VOICE_HEADER if kind == "voice" else msg.LEADERBOARD_GAMES_HEADER
    rows = await db.leaderboard(kind, since=time.time() - WEEK, limit=LEADERBOARD_SIZE)
    if not rows:
        return f"{header}\n{msg.LEADERBOARD_EMPTY}"
    lines = [
        msg.LEADERBOARD_LINE.format(rank=i, user=f"<@{user_id}>", time=fmt_duration(secs))
        for i, (user_id, secs) in enumerate(rows, start=1)
    ]
    return header + "\n" + "\n".join(lines)


# --- Events ---

@client.event
async def on_ready():
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        print(f"Bot isn't in a server with ID {GUILD_ID}. Check GUILD_ID in .env.")
        return

    # Sessions left open by a crash/shutdown end when the bot was last seen running,
    # then we restart sessions for whatever people are doing right now.
    await db.close_all_open_sessions(at=await db.last_seen() or time.time())
    tracked = await db.tracked_users()
    for user_id in tracked:
        if member := guild.get_member(user_id):
            await start_current_sessions(member)

    if not heartbeat.is_running():
        heartbeat.start()
    if not reminder_loop.is_running():
        reminder_loop.start()
    print(f"Logged in as {client.user} in {guild.name}, tracking {len(tracked)} member(s).")


@client.event
async def on_voice_state_update(member: discord.Member, before, after):
    if member.guild.id != GUILD_ID or member.bot:
        return
    old, new = tracked_channel(member, before), tracked_channel(member, after)
    if old == new:  # mute/deafen/stream changes, not a join/leave/switch
        return
    if not await db.is_tracking(member.id):
        return
    if new:
        await db.start_session(member.id, "voice", new.name)  # also ends the old one
    else:
        await db.end_session(member.id, "voice")


@client.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    if after.guild.id != GUILD_ID or after.bot:
        return
    old, new = current_game(before), current_game(after)
    if old == new:  # status changes, Spotify, etc.
        return
    if not await db.is_tracking(after.id):
        return
    if new:
        await db.start_session(after.id, "game", new)  # also ends the old one
    else:
        await db.end_session(after.id, "game")


# --- Background tasks ---

@tasks.loop(seconds=60)
async def heartbeat():
    await db.set_last_seen(time.time())


# Minutes each reminder user has been continuously in voice or a game.
# Lives in memory only, so a restart resets everyone's timer.
active_minutes: dict[int, int] = {}


@tasks.loop(minutes=1)
async def reminder_loop():
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        return
    still_active = {}
    for user_id, channel_id in await db.reminder_users():
        member = guild.get_member(user_id)
        if member is None or not (tracked_channel(member, member.voice) or current_game(member)):
            continue  # not active, so their timer resets
        minutes = active_minutes.get(user_id, 0) + 1
        still_active[user_id] = minutes

        lines = []
        if minutes % WATER_EVERY_MINUTES == 0:
            lines.append(random.choice(msg.WATER_REMINDERS))
        if minutes % EXERCISE_EVERY_MINUTES == 0:
            lines.append(random.choice(msg.EXERCISE_REMINDERS))
        channel = guild.get_channel_or_thread(channel_id)
        if lines and channel:
            text = msg.REMINDER_POST.format(user=member.mention, reminder="\n".join(lines))
            try:
                # Only this person gets pinged (the bot pings nobody by default).
                await channel.send(text, allowed_mentions=discord.AllowedMentions(users=[member]))
            except discord.HTTPException:
                pass  # lost permission in that channel; they can move it with /reminder on
    active_minutes.clear()
    active_minutes.update(still_active)


@tasks.loop(time=WEEKLY_POST_TIME)
async def weekly_leaderboard():
    if dt.datetime.now(dt.timezone.utc).weekday() != WEEKLY_POST_DAY:
        return
    channel = client.get_channel(LEADERBOARD_CHANNEL_ID)
    if channel is None:
        print(f"Can't see channel {LEADERBOARD_CHANNEL_ID}. Check LEADERBOARD_CHANNEL_ID in .env.")
        return
    parts = [msg.WEEKLY_INTRO, await build_leaderboard("voice"), await build_leaderboard("game")]
    await channel.send("\n\n".join(parts))


@weekly_leaderboard.before_loop
async def before_weekly_leaderboard():
    await client.wait_until_ready()


# --- Slash commands ---

@client.tree.command(name="help", description="What this bot does")
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message(msg.HELP, ephemeral=True)


@client.tree.command(description="Check that the bot is alive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(msg.PING.format(latency_ms=round(client.latency * 1000)))


@client.tree.command(description="Turn voice and game tracking on or off for yourself")
@app_commands.describe(mode="on to start tracking, off to stop")
async def track(interaction: discord.Interaction, mode: Literal["on", "off"]):
    user_id = interaction.user.id
    was_tracking = await db.is_tracking(user_id)

    if mode == "on":
        if was_tracking:
            reply = msg.TRACK_ALREADY_ON
        else:
            await db.set_tracking(user_id, True)
            if member := interaction.guild.get_member(user_id):
                await start_current_sessions(member)
            reply = msg.TRACK_ON
    else:
        if not was_tracking:
            reply = msg.TRACK_ALREADY_OFF
        else:
            await db.set_tracking(user_id, False)
            await db.set_reminder_channel(user_id, None)  # reminders need tracking
            await db.end_session(user_id)
            reply = msg.TRACK_OFF

    await interaction.response.send_message(reply, ephemeral=True)


@client.tree.command(description="Get water and exercise reminders while you're in voice or gaming")
@app_commands.describe(mode="on to get reminders in this channel, off to stop")
async def reminder(interaction: discord.Interaction, mode: Literal["on", "off"]):
    user_id = interaction.user.id

    if mode == "on":
        perms = interaction.app_permissions  # the bot's permissions in this channel
        if isinstance(interaction.channel, discord.Thread):
            can_post = perms.view_channel and perms.send_messages_in_threads
        else:
            can_post = perms.view_channel and perms.send_messages

        if not await db.is_tracking(user_id):
            reply = msg.REMINDER_NEEDS_TRACKING
        elif not can_post:
            reply = msg.REMINDER_CANT_POST
        else:
            # One channel per person: turning on somewhere new moves reminders there.
            await db.set_reminder_channel(user_id, interaction.channel_id)
            reply = msg.REMINDER_ON
    else:
        if await db.reminder_channel(user_id) is None:
            reply = msg.REMINDER_ALREADY_OFF
        else:
            await db.set_reminder_channel(user_id, None)
            reply = msg.REMINDER_OFF

    await interaction.response.send_message(reply, ephemeral=True)


@client.tree.command(description="Show voice and game time for you or someone else")
@app_commands.describe(user="Whose stats to show (defaults to you)")
async def stats(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    user = user or interaction.user
    if not await db.is_tracking(user.id):
        if user == interaction.user:
            reply = msg.NOT_TRACKED_SELF
        else:
            reply = msg.NOT_TRACKED_OTHER.format(user=user.mention)
        await interaction.response.send_message(reply, ephemeral=True)
        return

    week_ago = time.time() - WEEK
    games = await db.top_games(user.id, limit=TOP_GAMES_IN_STATS)
    top_games = "\n".join(
        msg.STATS_GAME_LINE.format(rank=i, game=name, time=fmt_duration(secs))
        for i, (name, secs) in enumerate(games, start=1)
    ) or msg.STATS_NO_GAMES

    reply = msg.STATS.format(
        user=user.mention,
        voice_week=fmt_duration(await db.total_seconds(user.id, "voice", since=week_ago)),
        games_week=fmt_duration(await db.total_seconds(user.id, "game", since=week_ago)),
        voice_all=fmt_duration(await db.total_seconds(user.id, "voice")),
        games_all=fmt_duration(await db.total_seconds(user.id, "game")),
        top_games=top_games,
    )
    await interaction.response.send_message(reply)


@client.tree.command(description="Top members by voice or game time over the last 7 days")
@app_commands.describe(category="Which leaderboard to show")
async def leaderboard(interaction: discord.Interaction, category: Literal["voice", "games"] = "voice"):
    kind = "voice" if category == "voice" else "game"
    await interaction.response.send_message(await build_leaderboard(kind))


client.run(TOKEN)
