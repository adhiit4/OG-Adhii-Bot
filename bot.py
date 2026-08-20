import os
import json
import random
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN secret is missing")

DATA = "data.json"

# =========================================================
# DATABASE
# =========================================================

DEFAULT_DATA = {
    "warns": {},
    "xp": {},
    "welcome": {},
    "autorole": {},
    "logs": {},
    "badwords": {},
    "antilink": {},
    "antispam": {},
    "verify": {},
    "tickets": {},
    "ticket_setup": {},
    "voice": {},
    "level_channel": {},
}

try:
    with open(DATA, "r", encoding="utf-8") as f:
        D = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    D = {}

for key, value in DEFAULT_DATA.items():
    D.setdefault(key, value)

def save():
    try:
        with open(DATA, "w", encoding="utf-8") as f:
            json.dump(D, f, indent=2)
    except Exception as e:
        print("SAVE ERROR:", repr(e))

# =========================================================
# DISCORD
# =========================================================

I = discord.Intents.default()
I.guilds = True
I.members = True
I.messages = True
I.message_content = True
I.voice_states = True

bot = commands.Bot(command_prefix="!", intents=I)
tree = bot.tree

def gid(guild):
    return str(guild.id)

async def reply(interaction, text=None, embed=None, ephemeral=False):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, embed=embed, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(text, embed=embed, ephemeral=ephemeral)
    except Exception as e:
        print("REPLY ERROR:", repr(e))

async def log(guild, title, text, color=discord.Color.blurple()):
    try:
        cid = D["logs"].get(gid(guild))
        if not cid:
            return
        channel = guild.get_channel(int(cid))
        if not channel:
            return
        embed = discord.Embed(
            title=title,
            description=text[:4000],
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        await channel.send(embed=embed)
    except Exception as e:
        print("LOG ERROR:", repr(e))

def xp_level(xp):
    return int((max(0, xp) / 100) ** 0.5)

def xp_for_level(level):
    return level * level * 100

def xp_to_next_level(xp):
    level = xp_level(xp)
    return max(0, xp_for_level(level + 1) - xp)

# =========================================================
# READY / STARTUP
# =========================================================

@bot.event
async def on_ready():
    print(f"ONLINE: {bot.user} | ID: {bot.user.id}")
    print(f"COMMANDS: {len(tree.get_commands())}")

    # Reconnect to every server's saved 24/7 voice channel after a restart.
    for guild_id, channel_id in D.get("voice", {}).items():
        try:
            guild = bot.get_guild(int(guild_id))
            if not guild:
                continue

            channel = guild.get_channel(int(channel_id))
            if not isinstance(channel, discord.VoiceChannel):
                continue

            voice_client = guild.voice_client
            if voice_client and voice_client.is_connected():
                continue

            if voice_client:
                await voice_client.disconnect(force=True)

            await channel.connect(reconnect=True)
            print(f"24/7 VC CONNECTED: {guild.name} -> {channel.name}")
        except Exception as e:
            print(f"24/7 VC ERROR [{guild_id}]:", repr(e))

# =========================================================
# MEMBER EVENTS
# =========================================================

@bot.event
async def on_member_join(member):
    # Ignore bots so Carl-bot/other bots never trigger welcome messages.
    if member.bot:
        return

    try:
        role_id = D["autorole"].get(gid(member.guild))

        if role_id:
            role = member.guild.get_role(int(role_id))
            me = member.guild.me

            if role and me and role < me.top_role:
                await member.add_roles(role, reason="OG ADHII Auto Role")

    except Exception as e:
        print("AUTOROLE ERROR:", repr(e))

    try:
        data = D["welcome"].get(gid(member.guild))

        if data:
            channel = member.guild.get_channel(int(data["channel"]))

            if channel:
                message = data.get(
                    "message",
                    "👋 Welcome {user} to **{server}**!"
                )

                message = message.replace("{user}", member.mention).replace(
                    "{server}", member.guild.name
                )

                # Send exactly one welcome message with welcome.png if it exists.
                banner = "welcome.png"
                if os.path.isfile(banner):
                    await channel.send(
                        content=message,
                        file=discord.File(banner, filename="welcome.png")
                    )
                else:
                    await channel.send(message)

    except Exception as e:
        print("WELCOME ERROR:", repr(e))

    await log(
        member.guild,
        "📥 Member Joined",
        f"{member.mention} joined."
    )


@bot.event
async def on_member_remove(member):
    await log(member.guild, "📤 Member Left", f"**{member}** left.")

@bot.event
async def on_member_update(before, after):
    try:
        if before.nick != after.nick:
            await log(after.guild, "✏️ Nickname Changed",
                      f"{after.mention}: `{before.nick}` → `{after.nick}`")

        before_roles = {r.id for r in before.roles}
        after_roles = {r.id for r in after.roles}
        if before_roles != after_roles:
            added = [r.name for r in after.roles if r.id not in before_roles]
            removed = [r.name for r in before.roles if r.id not in after_roles]
            await log(
                after.guild,
                "🎭 Role Change",
                f"{after.mention}\n"
                f"Added: {', '.join(added) if added else 'None'}\n"
                f"Removed: {', '.join(removed) if removed else 'None'}"
            )
    except Exception as e:
        print("MEMBER UPDATE ERROR:", repr(e))

@bot.event
async def on_message_delete(message):
    try:
        if message.guild and message.author and not message.author.bot:
            await log(
                message.guild,
                "🗑️ Message Deleted",
                f"{message.author.mention} in {message.channel.mention}\n"
                f"`{message.content[:1200] or '[no text]'}`"
            )
    except Exception as e:
        print("DELETE LOG ERROR:", repr(e))

@bot.event
async def on_message_edit(before, after):
    try:
        if (
            after.guild and after.author and not after.author.bot
            and before.content != after.content
        ):
            await log(
                after.guild,
                "✏️ Message Edited",
                f"{after.author.mention} in {after.channel.mention}\n"
                f"Before: `{before.content[:600]}`\n"
                f"After: `{after.content[:600]}`"
            )
    except Exception as e:
        print("EDIT LOG ERROR:", repr(e))

# =========================================================
# MESSAGE / SECURITY
# =========================================================

spam = {}

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    guild_id = gid(message.guild)
    content_lower = message.content.lower()

    # Anti-link
    if (
        D["antilink"].get(guild_id)
        and re.search(r"https?://|www\.", message.content, re.IGNORECASE)
        and not message.author.guild_permissions.manage_messages
    ):
        try:
            await message.delete()
            await message.channel.send(
                f"🚫 {message.author.mention} links are disabled.",
                delete_after=3,
            )
        except Exception as e:
            print("ANTILINK ERROR:", repr(e))
        return

    # Bad words
    words = D["badwords"].get(guild_id, [])
    if (
        any(re.search(r"\b" + re.escape(w) + r"\b", content_lower) for w in words)
        and not message.author.guild_permissions.manage_messages
    ):
        try:
            await message.delete()
            await message.channel.send(
                f"🚫 {message.author.mention} that word is not allowed.",
                delete_after=3,
            )
        except Exception as e:
            print("BADWORD ERROR:", repr(e))
        return

    # Anti-spam
    if D["antispam"].get(guild_id) and not message.author.guild_permissions.manage_messages:
        key = (message.guild.id, message.author.id)
        now = datetime.now(timezone.utc).timestamp()
        queue = spam.setdefault(key, [])
        queue[:] = [t for t in queue if now - t < 5]
        queue.append(now)

        if len(queue) >= 6:
            try:
                await message.author.timeout(timedelta(minutes=1), reason="Anti-spam")
                await message.delete()
                await message.channel.send(
                    f"🛡️ {message.author.mention} was timed out for spam.",
                    delete_after=3,
                )
            except Exception as e:
                print("ANTISPAM ERROR:", repr(e))
            queue.clear()
            return

    # XP / LEVELING
    key = f"{guild_id}:{message.author.id}"
    old_xp = int(D["xp"].get(key, 0))
    new_xp = old_xp + random.randint(5, 15)
    D["xp"][key] = new_xp

    old_level = xp_level(old_xp)
    new_level = xp_level(new_xp)

    if new_level > old_level:
        try:
            level_channel_id = D["level_channel"].get(guild_id)
            level_channel = message.guild.get_channel(int(level_channel_id)) if level_channel_id else None
            target = level_channel if isinstance(level_channel, discord.TextChannel) else message.channel

            embed = discord.Embed(
                title="🎉  LEVEL UP!",
                description=(
                    f"Congratulations, {message.author.mention}!\n\n"
                    f"🏆 **Current Level**\n**{new_level}**\n\n"
                    f"📊 **Total XP**\n**{new_xp:,} XP**\n\n"
                    f"⭐ **XP to Next Level**\n**{xp_to_next_level(new_xp):,} XP**"
                ),
                color=discord.Color.from_rgb(184, 28, 48),
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)
            embed.set_footer(text=f"{message.guild.name} • Keep chatting to climb the leaderboard!")
            await target.send(embed=embed)
        except Exception as e:
            print("LEVEL UP ERROR:", repr(e))

    if new_xp % 100 < 20 or new_level > old_level:
        save()

    await bot.process_commands(message)

# =========================================================
# MODERATION
# =========================================================

@tree.command(name="ban", description="Ban a member")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await member.ban(reason=reason)
        await reply(interaction, f"🔨 Banned {member.mention}")
        await log(interaction.guild, "🔨 Ban",
                  f"{member} by {interaction.user.mention}\n{reason}", discord.Color.red())
    except discord.Forbidden:
        await reply(interaction, "❌ I cannot ban this member. Check role hierarchy and permissions.", ephemeral=True)

@tree.command(name="kick", description="Kick a member")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await member.kick(reason=reason)
        await reply(interaction, f"👢 Kicked {member.mention}")
    except discord.Forbidden:
        await reply(interaction, "❌ I cannot kick this member.", ephemeral=True)

@tree.command(name="timeout", description="Timeout a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction, member: discord.Member, minutes: int = 10, reason: str = "No reason provided"):
    minutes = max(1, min(minutes, 40320))
    try:
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await reply(interaction, f"⏳ {member.mention} timed out for **{minutes} minutes**.")
    except discord.Forbidden:
        await reply(interaction, "❌ I cannot timeout this member.", ephemeral=True)

@tree.command(name="mute", description="Mute a member using Discord timeout")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(interaction, member: discord.Member, minutes: int = 10):
    minutes = max(1, min(minutes, 40320))
    try:
        await member.timeout(timedelta(minutes=minutes), reason="Mute")
        await reply(interaction, f"🔇 Muted {member.mention} for **{minutes} minutes**.")
    except discord.Forbidden:
        await reply(interaction, "❌ I cannot mute this member.", ephemeral=True)

@tree.command(name="unmute", description="Remove timeout")
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute(interaction, member: discord.Member):
    try:
        await member.timeout(None, reason="Unmute")
        await reply(interaction, f"🔊 Unmuted {member.mention}.")
    except discord.Forbidden:
        await reply(interaction, "❌ I cannot remove this timeout.", ephemeral=True)

@tree.command(name="warn", description="Warn a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction, member: discord.Member, reason: str = "No reason provided"):
    key = f"{gid(interaction.guild)}:{member.id}"
    D["warns"][key] = D["warns"].get(key, 0) + 1
    save()
    await reply(
        interaction,
        f"⚠️ {member.mention} warned.\n"
        f"Total warnings: **{D['warns'][key]}**\nReason: {reason}"
    )
    await log(interaction.guild, "⚠️ Warning",
              f"{member.mention} warned by {interaction.user.mention}\nReason: {reason}")

# =========================================================
# CHANNEL / SERVER MANAGEMENT
# =========================================================

@tree.command(name="clear", description="Delete up to 100 messages")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction, amount: int = 10):
    if not 1 <= amount <= 100:
        return await reply(interaction, "❌ Amount must be between 1 and 100.", ephemeral=True)
    await reply(interaction, "🧹 Clearing...", ephemeral=True)
    try:
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.channel.send(f"🧹 Cleared **{len(deleted)}** messages.", delete_after=3)
    except Exception as e:
        await reply(interaction, f"❌ Clear failed: `{type(e).__name__}`", ephemeral=True)

@tree.command(name="lock", description="Lock a channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    try:
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite,
                                       reason=f"Locked by {interaction.user}")
        await reply(interaction, f"🔒 Locked {channel.mention}")
    except Exception as e:
        await reply(interaction, f"❌ Lock failed: `{type(e).__name__}`", ephemeral=True)

@tree.command(name="unlock", description="Unlock a channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    try:
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite,
                                       reason=f"Unlocked by {interaction.user}")
        await reply(interaction, f"🔓 Unlocked {channel.mention}")
    except Exception as e:
        await reply(interaction, f"❌ Unlock failed: `{type(e).__name__}`", ephemeral=True)

@tree.command(name="slowmode", description="Set slowmode seconds")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(interaction, seconds: int = 0):
    seconds = max(0, min(seconds, 21600))
    try:
        await interaction.channel.edit(slowmode_delay=seconds)
        await reply(interaction, f"🐢 Slowmode: **{seconds}s**")
    except Exception as e:
        await reply(interaction, f"❌ Slowmode failed: `{type(e).__name__}`", ephemeral=True)

@tree.command(name="createchannel", description="Create text channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def createchannel(interaction, name: str):
    try:
        channel = await interaction.guild.create_text_channel(name=name)
        await reply(interaction, f"✅ Created {channel.mention}")
    except Exception as e:
        await reply(interaction, f"❌ Create failed: `{type(e).__name__}`", ephemeral=True)

@tree.command(name="deletechannel", description="Delete text channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def deletechannel(interaction, channel: discord.TextChannel):
    try:
        await reply(interaction, f"🗑️ Deleting {channel.mention}")
        await channel.delete(reason=f"Deleted by {interaction.user}")
    except Exception as e:
        await reply(interaction, f"❌ Delete failed: `{type(e).__name__}`", ephemeral=True)

@tree.command(name="renamechannel", description="Rename text channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def renamechannel(interaction, channel: discord.TextChannel, name: str):
    try:
        await channel.edit(name=name)
        await reply(interaction, f"✏️ Renamed to **{name}**")
    except Exception as e:
        await reply(interaction, f"❌ Rename failed: `{type(e).__name__}`", ephemeral=True)

# =========================================================
# SECURITY / LOGS / WELCOME
# =========================================================

@tree.command(name="antispam", description="Toggle anti spam")
@app_commands.checks.has_permissions(manage_guild=True)
async def antispam(interaction, enabled: bool):
    D["antispam"][gid(interaction.guild)] = enabled
    save()
    await reply(interaction, f"🛡️ Anti-spam **{'ON' if enabled else 'OFF'}**")

@tree.command(name="antilink", description="Toggle anti link")
@app_commands.checks.has_permissions(manage_guild=True)
async def antilink(interaction, enabled: bool):
    D["antilink"][gid(interaction.guild)] = enabled
    save()
    await reply(interaction, f"🔗 Anti-link **{'ON' if enabled else 'OFF'}**")

@tree.command(name="badword", description="Add a filtered word")
@app_commands.checks.has_permissions(manage_guild=True)
async def badword(interaction, word: str):
    word = word.strip().lower()
    if not word:
        return await reply(interaction, "❌ Enter a word.", ephemeral=True)
    words = D["badwords"].setdefault(gid(interaction.guild), [])
    if word in words:
        return await reply(interaction, f"⚠️ `{word}` is already filtered.", ephemeral=True)
    words.append(word)
    save()
    await reply(interaction, f"🚫 Added `{word}` to bad-word filter.")

@tree.command(name="setlog", description="Set this channel as log channel")
@app_commands.checks.has_permissions(manage_guild=True)
async def setlog(interaction):
    D["logs"][gid(i
