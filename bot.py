import os
import json
import random
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, render_template
from threading import Thread
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
    "gender": {},
    "logs": {},
    "badwords": {},
    "antilink": {},
    "antispam": {},
    "verify": {},
    "tickets": {},
    "ticket_setup": {},
    "voice": {},
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
    return int((xp / 100) ** 0.5)

# =========================================================
# READY / STARTUP
# =========================================================

@bot.event
async def on_ready():
    print(f"ONLINE: {bot.user} | ID: {bot.user.id}")
    print(f"COMMANDS: {len(tree.get_commands())}")

    # Reconnect to every server's saved 24/7 voice channel after a restart.
    for guild_id, channel_id in D.get("voice", {}).items():
        guild = bot.get_guild(int(guild_id))
        if guild:
            await reconnect_saved_vc(guild, channel_id)

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

    # XP
    key = f"{guild_id}:{message.author.id}"
    old_xp = int(D["xp"].get(key, 0))
    new_xp = old_xp + random.randint(5, 15)
    D["xp"][key] = new_xp

    if xp_level(new_xp) > xp_level(old_xp):
        try:
            await message.channel.send(
                f"🎉 {message.author.mention} reached **Level {xp_level(new_xp)}**!"
            )
        except Exception:
            pass

    if new_xp % 100 < 20:
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
    D["logs"][gid(interaction.guild)] = interaction.channel.id
    save()
    await reply(interaction, "📊 Log channel set.")

@tree.command(name="welcome", description="Set welcome channel and message")
@app_commands.checks.has_permissions(manage_guild=True)
async def welcome(interaction, channel: discord.TextChannel,
                  message: str = "👋 Welcome {user} to **{server}**!"):
    D["welcome"][gid(interaction.guild)] = {"channel": channel.id, "message": message}
    save()
    await reply(interaction, f"👋 Welcome set to {channel.mention}")

@tree.command(name="autorole", description="Set auto role")
@app_commands.checks.has_permissions(manage_roles=True)
async def autorole(interaction, role: discord.Role):
    me = interaction.guild.me
    if not me or role >= me.top_role:
        return await reply(interaction, "❌ The role must be below my bot role.", ephemeral=True)
    D["autorole"][gid(interaction.guild)] = role.id
    save()
    await reply(interaction, f"🎭 Auto role: **{role.name}**")

@tree.command(name="addrole", description="Add role")
@app_commands.checks.has_permissions(manage_roles=True)
async def addrole(interaction, member: discord.Member, role: discord.Role):
    if role >= interaction.guild.me.top_role:
        return await reply(interaction, "❌ I cannot manage this role.", ephemeral=True)
    try:
        await member.add_roles(role)
        await reply(interaction, f"🎭 Added **{role.name}** to {member.mention}")
    except Exception as e:
        await reply(interaction, f"❌ Failed: `{type(e).__name__}`", ephemeral=True)

@tree.command(name="removerole", description="Remove role")
@app_commands.checks.has_permissions(manage_roles=True)
async def removerole(interaction, member: discord.Member, role: discord.Role):
    if role >= interaction.guild.me.top_role:
        return await reply(interaction, "❌ I cannot manage this role.", ephemeral=True)
    try:
        await member.remove_roles(role)
        await reply(interaction, f"🎭 Removed **{role.name}** from {member.mention}")
    except Exception as e:
        await reply(interaction, f"❌ Failed: `{type(e).__name__}`", ephemeral=True)

@tree.command(name="createrole", description="Create role")
@app_commands.checks.has_permissions(manage_roles=True)
async def createrole(interaction, name: str):
    try:
        role = await interaction.guild.create_role(name=name)
        await reply(interaction, f"🎭 Created {role.mention}")
    except Exception as e:
        await reply(interaction, f"❌ Failed: `{type(e).__name__}`", ephemeral=True)


# =========================================================
# GENDER ROLE SELECTOR
# =========================================================

class GenderSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Male", value="male", emoji="♂️"),
            discord.SelectOption(label="Female", value="female", emoji="♀️"),
        ]
        super().__init__(
            placeholder="Select your gender role...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="og_gender_select",
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            guild = interaction.guild
            config = D["gender"].get(gid(guild)) if guild else None
            if not guild or not config:
                return await reply(
                    interaction,
                    "❌ Gender roles are not configured. Ask staff to run `/setupgender`.",
                    ephemeral=True,
                )

            male_role = guild.get_role(int(config["male"]))
            female_role = guild.get_role(int(config["female"]))
            me = guild.me

            if not male_role or not female_role:
                return await reply(interaction, "❌ Gender roles are missing. Run `/setupgender` again.", ephemeral=True)

            if not me or male_role >= me.top_role or female_role >= me.top_role:
                return await reply(interaction, "❌ Move the bot role above both gender roles.", ephemeral=True)

            add_role = male_role if self.values[0] == "male" else female_role
            remove_role = female_role if self.values[0] == "male" else male_role

            if remove_role in interaction.user.roles:
                await interaction.user.remove_roles(remove_role, reason="Gender role changed")
            if add_role not in interaction.user.roles:
                await interaction.user.add_roles(add_role, reason="Gender role selection")

            await reply(interaction, f"✅ You selected **{add_role.name}**.", ephemeral=True)

        except discord.Forbidden:
            await reply(interaction, "❌ I cannot manage these roles. Check Manage Roles and role hierarchy.", ephemeral=True)
        except Exception as e:
            print("GENDER SELECT ERROR:", repr(e))
            await reply(interaction, f"❌ Gender selection failed: `{type(e).__name__}`", ephemeral=True)


class GenderPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(GenderSelect())


@tree.command(name="setupgender", description="Set Male/Female roles and send the gender selector")
@app_commands.checks.has_permissions(manage_roles=True)
async def setupgender(
    interaction: discord.Interaction,
    male_role: discord.Role,
    female_role: discord.Role,
):
    guild = interaction.guild
    if not guild:
        return await reply(interaction, "❌ Server only.", ephemeral=True)

    me = guild.me
    if not me:
        return await reply(interaction, "❌ Bot member not found.", ephemeral=True)

    if male_role == female_role:
        return await reply(interaction, "❌ Male and Female roles must be different.", ephemeral=True)

    if male_role >= me.top_role or female_role >= me.top_role:
        return await reply(
            interaction,
            "❌ Move the bot role above both **Male** and **Female** roles.",
            ephemeral=True,
        )

    D["gender"][gid(guild)] = {
        "male": male_role.id,
        "female": female_role.id,
    }
    save()

    embed = discord.Embed(
        title="👤 Choose Your Gender",
        description="Select **Male** or **Female** below.\n\nYou can change your selection later.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="♂️ Male", value=male_role.mention, inline=True)
    embed.add_field(name="♀️ Female", value=female_role.mention, inline=True)

    await interaction.channel.send(embed=embed, view=GenderPanel())
    await reply(interaction, "✅ Gender selector panel sent.", ephemeral=True)

# =========================================================
# FUN / INFO
# =========================================================

@tree.command(name="ping", description="Bot latency")
async def ping(interaction):
    await reply(interaction, f"🏓 Pong! **{round(bot.latency * 1000)}ms**")

@tree.command(name="avatar", description="Show avatar")
async def avatar(interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"🖼 {member.display_name}")
    embed.set_image(url=member.display_avatar.url)
    await reply(interaction, embed=embed)

@tree.command(name="userinfo", description="User information")
async def userinfo(interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"👤 {member}", color=member.color)
    embed.add_field(name="ID", value=str(member.id), inline=False)
    embed.add_field(name="Joined", value=discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "?")
    embed.add_field(name="Created", value=discord.utils.format_dt(member.created_at, "R"))
    await reply(interaction, embed=embed)

@tree.command(name="server", description="Server information")
async def server(interaction):
    g = interaction.guild
    embed = discord.Embed(title=f"📊 {g.name}")
    embed.add_field(name="Members", value=str(g.member_count))
    embed.add_field(name="Channels", value=str(len(g.channels)))
    embed.add_field(name="Roles", value=str(len(g.roles)))
    await reply(interaction, embed=embed)

@tree.command(name="coinflip", description="Flip coin")
async def coinflip(interaction):
    await reply(interaction, f"🪙 **{random.choice(['Heads', 'Tails'])}**")

@tree.command(name="dice", description="Roll dice")
async def dice(interaction, sides: int = 6):
    sides = max(2, min(sides, 1000))
    await reply(interaction, f"🎲 **{random.randint(1, sides)}**")

@tree.command(name="joke", description="Random joke")
async def joke(interaction):
    await reply(interaction, random.choice([
        "Why did the developer go broke? He used all his cache.",
        "I told my bot to behave. It returned 403.",
        "There are 10 types of people: binary readers and everyone else.",
    ]))

@tree.command(name="quote", description="Random quote")
async def quote(interaction):
    await reply(interaction, random.choice([
        "“Discipline beats motivation.”",
        "“Consistency compounds.”",
        "“Build first, optimize later.”",
    ]))

@tree.command(name="calculator", description="Basic calculator")
async def calculator(interaction, expression: str):
    if not re.fullmatch(r"[0-9+\-*/(). %]+", expression):
        return await reply(interaction, "❌ Invalid expression.", ephemeral=True)
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        await reply(interaction, f"🧮 `{expression}` = **{result}**")
    except Exception:
        await reply(interaction, "❌ Calculation failed.", ephemeral=True)

@tree.command(name="poll", description="Create yes/no poll")
async def poll(interaction, question: str):
    await interaction.response.send_message(f"📊 **{question}**\n👍 Yes\n👎 No")
    msg = await interaction.original_response()
    try:
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
    except Exception as e:
        print("POLL ERROR:", repr(e))

@tree.command(name="rank", description="Show XP rank")
async def rank(interaction, member: discord.Member = None):
    member = member or interaction.user
    xp = int(D["xp"].get(f"{gid(interaction.guild)}:{member.id}", 0))
    await reply(interaction, f"🏆 {member.mention}\nLevel **{xp_level(xp)}** • **{xp} XP**")

@tree.command(name="leaderboard", description="Top XP members")
async def leaderboard(interaction):
    prefix = gid(interaction.guild) + ":"
    rows = sorted(
        [(k, v) for k, v in D["xp"].items() if k.startswith(prefix)],
        key=lambda x: int(x[1]),
        reverse=True,
    )[:10]
    if not rows:
        return await reply(interaction, "No XP yet.")
    out = []
    for n, (key, xp) in enumerate(rows, 1):
        out.append(f"**{n}.** <@{key.split(':')[1]}> — {xp} XP")
    await reply(interaction, "\n".join(out))

# =========================================================
# TICKET SYSTEM - FIXED
# =========================================================

SUPPORT_ROLE_NAMES = {"staff", "support", "moderator", "admin"}

def bot_member(guild):
    return guild.me

def ticket_overwrites(guild, user):
    me = bot_member(guild)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
        ),
    }
    if me:
        overwrites[me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
        )

    for role in guild.roles:
        if role.name.lower() in SUPPORT_ROLE_NAMES:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            )
    return overwrites

class Ticket(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Create Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="og_ticket_create",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            guild = interaction.guild
            if not guild:
                return await reply(interaction, "❌ Server only.", ephemeral=True)

            setup = D["ticket_setup"].get(gid(guild))
            if not setup:
                return await reply(
                    interaction,
                    "❌ Ticket system is not configured. Use `/setupsupport` first.",
                    ephemeral=True,
                )

            category = guild.get_channel(int(setup["category"]))
            if not isinstance(category, discord.CategoryChannel):
                return await reply(
                    interaction,
                    "❌ Ticket category is missing. Run `/setupsupport` again.",
                    ephemeral=True,
                )

            channel_name = f"ticket-{interaction.user.id}"
            existing = discord.utils.get(guild.text_channels, name=channel_name)
            if existing:
                return await reply(
                    interaction,
                    f"🎫 You already have {existing.mention}",
                    ephemeral=True,
                )

            me = bot_member(guild)
            if not me or not guild.me.guild_permissions.manage_channels:
                return await reply(
                    interaction,
                    "❌ Bot needs **Manage Channels** permission.",
                    ephemeral=True,
                )

            channel = await guild.create_text_channel(
                channel_name,
                category=category,
                overwrites=ticket_overwrites(guild, interaction.user),
                reason=f"Ticket opened by {interaction.user}",
            )

            D["tickets"][str(channel.id)] = {
                "user": interaction.user.id,
                "guild": guild.id,
                "created": datetime.now(timezone.utc).isoformat(),
            }
            save()

            embed = discord.Embed(
                title="🎫 Support Ticket",
                description=(
                    f"Welcome {interaction.user.mention}!\n\n"
                    "Please explain your issue clearly.\n"
                    "A staff member will assist you shortly.\n\n"
                    "Use the button below to close this ticket."
                ),
                color=discord.Color.blurple(),
            )
            embed.set_footer(text=f"{guild.name} • Support")

            await channel.send(
                content=interaction.user.mention,
                embed=embed,
                view=CloseTicket(),
            )

            await reply(
                interaction,
                f"🎫 Ticket created: {channel.mention}",
                ephemeral=True,
            )

        except discord.Forbidden:
            await reply(
                interaction,
                "❌ Discord denied the ticket creation. Give the bot **Manage Channels** permission and move its role high enough.",
                ephemeral=True,
            )
        except Exception as e:
            print("TICKET CREATE ERROR:", repr(e))
            await reply(
                interaction,
                f"❌ Ticket creation failed: `{type(e).__name__}`\n`{str(e)[:500]}`",
                ephemeral=True,
            )

class CloseTicket(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="og_ticket_close",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            channel = interaction.channel
            data = D["tickets"].get(str(channel.id))

            if not data:
                return await reply(interaction, "❌ This is not a ticket channel.", ephemeral=True)

            is_owner = int(data["user"]) == interaction.user.id
            is_staff = interaction.user.guild_permissions.manage_channels

            if not (is_owner or is_staff):
                return await reply(interaction, "❌ You cannot close this ticket.", ephemeral=True)

            await reply(interaction, "🔒 Closing ticket...", ephemeral=True)
            D["tickets"].pop(str(channel.id), None)
            save()
            await channel.delete(reason=f"Ticket closed by {interaction.user}")

        except discord.Forbidden:
            await reply(interaction, "❌ I cannot delete this ticket. Check Manage Channels.", ephemeral=True)
        except Exception as e:
            print("TICKET CLOSE ERROR:", repr(e))

@tree.command(name="setupsupport", description="Create or repair the complete ticket support system")
@app_commands.checks.has_permissions(manage_channels=True)
async def setupsupport(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        return await reply(interaction, "❌ Server only.", ephemeral=True)

    # Defer immediately so Discord does not expire the interaction while channels are created.
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        pass

    try:
        me = guild.me
        if not me:
            return await reply(interaction, "❌ Bot member not found.", ephemeral=True)

        missing = []
        if not me.guild_permissions.manage_channels:
            missing.append("Manage Channels")
        if missing:
            return await reply(
                interaction,
                "❌ Bot is missing: **" + ", ".join(missing) + "**",
                ephemeral=True,
            )

        # Category
        category = discord.utils.get(guild.categories, name="🆘 SUPPORT")
        if not category:
            category = await guild.create_category(
                "🆘 SUPPORT",
                reason=f"Support setup by {interaction.user}",
            )

        # Ticket creation channel
        ticket_channel = discord.utils.get(
            guild.text_channels,
            name="🎫・create-ticket",
        )
        if not ticket_channel:
            ticket_channel = await guild.create_text_channel(
                "🎫・create-ticket",
                category=category,
                reason="Support ticket setup",
            )
        elif ticket_channel.category_id != category.id:
            await ticket_channel.edit(category=category)

        # Support VC
        support_vc = discord.utils.get(
            guild.voice_channels,
            name="🔊・Support VC",
        )
        if not support_vc:
            support_vc = await guild.create_voice_channel(
                "🔊・Support VC",
                category=category,
                reason="Support VC setup",
            )
        elif support_vc.category_id != category.id:
            await support_vc.edit(category=category)

        # Save
        D["ticket_setup"][gid(guild)] = {
            "category": category.id,
            "ticket_channel": ticket_channel.id,
            "support_vc": support_vc.id,
        }
        save()

        # Send a fresh panel. Old panels remain usable because custom_id is persistent.
        embed = discord.Embed(
            title="🎫 Support Center",
            description=(
                "**Need help? Open a ticket.**\n\n"
                "Click the button below to create a private support ticket.\n\n"
                "🎫 **Create Ticket**\n"
                "🔒 Private staff support\n"
                "🔊 Support VC available"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{guild.name} • Support System")

        await ticket_channel.send(embed=embed, view=Ticket())

        await reply(
            interaction,
            "✅ **Support system is ready!**\n\n"
            f"📁 Category: {category.mention}\n"
            f"🎫 Ticket panel: {ticket_channel.mention}\n"
            f"🔊 Support VC: {support_vc.mention}",
            ephemeral=True,
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ Discord denied the setup. Give the bot **Manage Channels** permission.",
            ephemeral=True,
        )
    except Exception as e:
        print("SUPPORT SETUP ERROR:", repr(e))
        await reply(
            interaction,
            f"❌ **Setup failed**\n`{type(e).__name__}: {str(e)[:700]}`",
            ephemeral=True,
        )

# =========================================================
# 24/7 VOICE CHANNEL - STABLE VC JOIN
# =========================================================

async def connect_saved_voice(guild, channel):
    """Connect/reconnect the bot to a saved voice channel."""
    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        raise TypeError("Saved channel is not a voice/stage channel")

    me = guild.me
    if not me:
        raise RuntimeError("Bot member not found")

    permissions = channel.permissions_for(me)
    if not permissions.connect:
        raise PermissionError("Missing Connect permission")

    existing = guild.voice_client

    if existing and existing.is_connected():
        if existing.channel and existing.channel.id == channel.id:
            return existing
        await existing.move_to(channel)
        return existing

    if existing:
        try:
            await existing.disconnect(force=True)
        except Exception:
            pass

    return await channel.connect(reconnect=True, self_deaf=True)


async def reconnect_saved_vc(guild, channel_id):
    """Reconnect to the saved VC after startup/restart."""
    try:
        channel = guild.get_channel(int(channel_id))
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            print(f"24/7 VC SKIP [{guild.id}]: saved channel is missing or not a VC")
            return

        await connect_saved_voice(guild, channel)
        print(f"24/7 VC CONNECTED: {guild.name} -> {channel.name}")
    except Exception as e:
        print(f"24/7 VC ERROR [{guild.id}]: {type(e).__name__}: {e}")


async def join_voice_for_interaction(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        return "❌ Server only."

    if not interaction.user.voice or not interaction.user.voice.channel:
        return "❌ Join a voice channel first, then use `/joinvc`."

    channel = interaction.user.voice.channel
    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        return "❌ Please use a normal voice channel."

    me = guild.me
    if not me:
        return "❌ Bot member not found."

    permissions = channel.permissions_for(me)
    if not permissions.connect:
        return "❌ I need **Connect** permission in that VC."

    await connect_saved_voice(guild, channel)
    D.setdefault("voice", {})[gid(guild)] = channel.id
    save()
    return f"🔊 **VC connected!**\nBot joined {channel.mention} and will reconnect after a restart."


@tree.command(name="joinvc", description="Join your current voice channel and keep it as the 24/7 VC")
@app_commands.checks.has_permissions(manage_guild=True)
async def joinvc(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        pass

    try:
        message = await join_voice_for_interaction(interaction)
        await reply(interaction, message, ephemeral=True)
    except discord.Forbidden:
        await reply(
            interaction,
            "❌ Discord denied the VC connection. Check the bot's **Connect** permission in that VC.",
            ephemeral=True,
        )
    except discord.ClientException as e:
        print("JOINVC CLIENT ERROR:", repr(e))
        await reply(
            interaction,
            f"❌ Discord voice connection failed: `{type(e).__name__}`",
            ephemeral=True,
        )
    except Exception as e:
        print("JOINVC ERROR:", repr(e))
        await reply(
            interaction,
            f"❌ VC connection failed: `{type(e).__name__}: {str(e)[:400]}`",
            ephemeral=True,
        )


@tree.command(name="setvc", description="Set your current voice channel as the bot's 24/7 VC")
@app_commands.checks.has_permissions(manage_guild=True)
async def setvc(interaction: discord.Interaction):
    # /setvc remains available for compatibility with the old command.
    await joinvc.callback(interaction)


@tree.command(name="leavevc", description="Stop the bot's 24/7 voice channel")
@app_commands.checks.has_permissions(manage_guild=True)
async def leavevc(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        return await reply(interaction, "❌ Server only.", ephemeral=True)

    D.setdefault("voice", {}).pop(gid(guild), None)
    save()

    try:
        if guild.voice_client:
            await guild.voice_client.disconnect(force=True)
    except Exception as e:
        print("LEAVEVC ERROR:", repr(e))

    await reply(interaction, "🔇 **24/7 VC disabled.** Bot left the voice channel.", ephemeral=True)

# =========================================================
# VERIFY
# =========================================================

class Verify(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="og_verify",
    )
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            role_id = D["verify"].get(gid(interaction.guild))
            if not role_id:
                return await reply(interaction, "❌ Verification role not configured.", ephemeral=True)

            role = interaction.guild.get_role(int(role_id))
            if not role:
                return await reply(interaction, "❌ Verification role no longer exists.", ephemeral=True)

            me = interaction.guild.me
            if not me or role >= me.top_role:
                return await reply(
                    interaction,
                    "❌ Move the bot role above the verification role.",
                    ephemeral=True,
                )

            await interaction.user.add_roles(role, reason="Verification")
            await reply(interaction, "✅ Verified!", ephemeral=True)

        except discord.Forbidden:
            await reply(interaction, "❌ I cannot give the verification role.", ephemeral=True)
        except Exception as e:
            print("VERIFY ERROR:", repr(e))
            await reply(interaction, f"❌ Verification failed: `{type(e).__name__}`", ephemeral=True)

@tree.command(name="verify", description="Set verify role and send panel")
@app_commands.checks.has_permissions(manage_guild=True)
async def verify(interaction, role: discord.Role):
    me = interaction.guild.me
    if not me or role >= me.top_role:
        return await reply(interaction, "❌ Move my bot role above the verification role.", ephemeral=True)

    D["verify"][gid(interaction.guild)] = role.id
    save()

    embed = discord.Embed(
        title="🔐 Verification",
        description="Click **Verify** to get access.",
        color=discord.Color.green(),
    )
    await interaction.channel.send(embed=embed, view=Verify())
    await reply(interaction, "✅ Verification panel sent.", ephemeral=True)

# =========================================================
# SUGGEST / REPORT / RULES / HELP
# =========================================================

@tree.command(name="suggest", description="Submit suggestion")
async def suggest(interaction, text: str):
    await log(interaction.guild, "💡 Suggestion", f"{interaction.user.mention}: {text}")
    await reply(interaction, "💡 Suggestion submitted.", ephemeral=True)

@tree.command(name="report", description="Report a member")
async def report(interaction, member: discord.Member, reason: str):
    await log(
        interaction.guild,
        "🚨 Report",
        f"Reporter: {interaction.user.mention}\nMember: {member.mention}\nReason: {reason}",
        discord.Color.red(),
    )
    await reply(interaction, "🚨 Report sent to staff.", ephemeral=True)

@tree.command(name="rules", description="Show rules")
async def rules(interaction):
    embed = discord.Embed(
        title="📜 Rules",
        description=(
            "1. Respect others.\n"
            "2. No spam.\n"
            "3. No harmful links.\n"
            "4. Follow Discord ToS.\n"
            "5. Follow staff instructions."
        ),
    )
    await reply(interaction, embed=embed)

@tree.command(name="help", description="Show command categories")
async def help_command(interaction):
    embed = discord.Embed(
        title="🤖 OG ADHII BOT",
        description=(
            "Use `/` to browse commands.\n\n"
            "🛡️ **Moderation**\n"
            "Ban • Kick • Timeout • Warn • Mute • Clear • Lock • Unlock • Slowmode\n\n"
            "🛡️ **Security**\n"
            "Anti-link • Anti-spam • Badword\n\n"
            "🎫 **Tickets**\n"
            "Setupsupport • Create Ticket • Close Ticket\n\n"
            "🎭 **Roles**\n"
            "AutoRole • AddRole • RemoveRole • CreateRole\n\n"
            "📊 **Logs**\n"
            "Join • Leave • Edit • Delete • Role changes\n\n"
            "🎮 **Fun**\n"
            "Ping • Avatar • UserInfo • Server • Coinflip • Dice • Joke • Quote • Calculator • Poll\n\n"
            "📈 **Levels**\n"
            "Rank • Leaderboard\n\n"
            "🔐 **Verify**\n"
            "Verification system\n\n"
            "⚙️ **Server**\n"
            "Welcome • Logs • Channel management"
        ),
        color=discord.Color.blurple(),
    )
    await reply(interaction, embed=embed)

# =========================================================
# PERSISTENT VIEWS + COMMAND SYNC
# =========================================================

@bot.event
async def setup_hook():
    # These make buttons continue working after a bot restart.
    bot.add_view(Ticket())
    bot.add_view(CloseTicket())
    bot.add_view(Verify())
    bot.add_view(GenderPanel())

    try:
        synced = await tree.sync()
        print(f"SLASH COMMANDS SYNCED: {len(synced)}")
    except Exception as e:
        print("SETUP SYNC ERROR:", repr(e))

# =========================================================
# COMMAND ERROR HANDLER
# =========================================================

@tree.error
async def command_error(interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        return await reply(interaction, "❌ You do not have permission.", ephemeral=True)

    if isinstance(error, app_commands.errors.BotMissingPermissions):
        return await reply(interaction, "❌ Bot is missing a required permission.", ephemeral=True)

    if isinstance(error, app_commands.errors.CommandOnCooldown):
        return await reply(interaction, "⏳ Please wait before using this command again.", ephemeral=True)

    print("COMMAND ERROR:", repr(error))
    await reply(
        interaction,
        f"❌ Command failed.\n`{type(error).__name__}: {str(error)[:500]}`",
        ephemeral=True,
    )

# =========================================================
# RUN
# =========================================================

bot.run(TOKEN)
