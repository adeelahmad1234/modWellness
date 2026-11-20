"""
Every message the bot sends lives here. Edit them freely.

Words in {curly braces} are filled in by the bot. You can move them around or
remove them, but don't rename them (the bot won't know what to put there).
Discord markdown works: **bold**, *italic*, `code`, emoji, and new lines.
Restart the bot after editing.
"""

# /help (only the person who ran the command sees this)
HELP = (
    "hey! i remind you to drink water every hour and get up and move every 2 hours while you're in voice or gaming, "
    "and i track your voice and game time so you can benchmark yourself. "
    "use /track on to start, then /reminder on in whatever channel you want the reminders in. "
    "/stats shows your time (or someone else's with /stats @user), "
    "and /leaderboard voice or /leaderboard games shows the top 10 for the week"
)

# /ping
PING = "Pong! 🏓 ({latency_ms} ms)"

# /track on|off (only the person who ran the command sees these)
TRACK_ON = "✅ Tracking is now **on**. I'll count your voice and game time. Use `/track off` to stop anytime."
TRACK_ALREADY_ON = "You're already being tracked. Use `/track off` to stop."
TRACK_OFF = "🛑 Tracking is now **off**. I've stopped counting your time."
TRACK_ALREADY_OFF = "You're not being tracked. Use `/track on` to start."

# /stats when the person hasn't opted in
NOT_TRACKED_SELF = "You haven't opted in yet. Use `/track on` to start tracking."
NOT_TRACKED_OTHER = "{user} hasn't opted in to tracking."

# /stats
STATS = """📊 **Stats for {user}**

**Last 7 days**
🎙️ Voice: {voice_week}
🎮 Games: {games_week}

**All time**
🎙️ Voice: {voice_all}
🎮 Games: {games_all}

**Top games**
{top_games}"""
STATS_GAME_LINE = "{rank}. {game}: {time}"
STATS_NO_GAMES = "No games tracked yet."

# /leaderboard and the weekly post
LEADERBOARD_VOICE_HEADER = "🎙️ **Voice leaderboard (last 7 days)**"
LEADERBOARD_GAMES_HEADER = "🎮 **Gaming leaderboard (last 7 days)**"
LEADERBOARD_LINE = "{rank}. {user}: {time}"
LEADERBOARD_EMPTY = "Nobody has tracked time this week yet."

# Weekly post, shown above both leaderboards
WEEKLY_INTRO = "📅 **Weekly recap!** Here's who spent the most time hanging out this week:"

# /reminder on|off (only the person who ran the command sees these)
REMINDER_ON = (
    "⏰ Reminders are **on**. I'll @ you in this channel while you're in voice or gaming. "
    "Use `/reminder on` in another channel to move them, or `/reminder off` to stop."
)
REMINDER_OFF = "🔕 Reminders are **off**."
REMINDER_ALREADY_OFF = "Your reminders are already off. Use `/reminder on` to start them."
REMINDER_NEEDS_TRACKING = "Reminders only work while tracking is on. Use `/track on` first."
REMINDER_CANT_POST = "I can't send messages in this channel. Try `/reminder on` in a different one."

# The reminder post. {user} pings the person, {reminder} is the saying(s) picked below.
REMINDER_POST = "{user} {reminder}"

# Reminder sayings. One is picked at random each time. Add or remove as many as you like.
WATER_REMINDERS = [
    "💧 Time for some water! Take a few sips.",
    "💧 Hydration check! When did you last drink something?",
    "💧 Your brain is mostly water. Top it up!",
    "💧 Grab your water bottle and take a big drink.",
    "💧 Quick reminder: drink some water before your next round.",
    "💧 Stay hydrated, stay sharp. Water break!",
]
EXERCISE_REMINDERS = [
    "🚶 You've been sitting for a while. Go for a quick walk!",
    "🧘 Stand up and stretch your arms, neck, and back for a minute.",
    "💪 Do 10 squats before you sit back down.",
    "🚶 Take a lap around your home and come right back.",
    "🙆 Roll your shoulders and stretch your wrists. Your body will thank you.",
    "🏃 Get up and move for 2 minutes. Jumping jacks, a walk, anything!",
]
