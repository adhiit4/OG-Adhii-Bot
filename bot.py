import os
import json
import random
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands


# =========================
# CONFIG
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN secret is missing")

DATA = "data.json"


# =========================
# DATABASE
# =========================

try:
    with open(DATA, "r", encoding="utf-8") as f:
        D = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    D = {}

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
}

for key, value in DEFAULT_DATA.items():
    D.setdefault(key, value)


def save():
    try:
        with open(DATA, "w", encoding="utf-8") as f:
            json.dump(D, f, indent=2)
    except Exception as e:
        print("SAVE ERROR:", repr(e))


# =========================
# DISCORD
# =========================

I = discord.Intents.default()
I.guilds = True
I.members = True
I.messages = True
I.message_content = True
I.voice_states = True

bot = commands.Bot(
    command_prefix="!",
    intents=I
)

tree = bot.tree


# =========================
# HELPERS
# =========================

def gid(guild):
    return str(guild.id)


async def log(
    guild,
    title,
    text,
    color=discord.Color.blurple()
):
    try:
        cid = D["logs"].get(gid(guild))

        if not cid:
            return

        channel = guild.get_channel(int(cid))

        if not channel:
            return

        embed = discord.Embed(
            title=title,
            description=text,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )

        await channel.send(embed=embed)

    except Exception as e:
        print("LOG ERROR:", repr(e))


async def reply(
    interaction,
    text=None,
    embed=None,
    ephemeral=False
):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                text,
                embed=embed,
                ephemeral=ephemeral
            )
        else:
            await interaction.response.send_message(
                text,
                embed=embed,
                ephemeral=ephemeral
            )
    except Exception as e:
        print("REPLY ERROR:", repr(e))


def xp_level(xp):
    return int((xp / 100) ** 0.5)


# =========================
# READY
# =========================

@bot.event
async def on_ready():
    try:
        await tree.sync()
        print(f"ONLINE: {bot.user}")
        print(f"COMMANDS: {len(tree.get_commands())}")
    except Exception as e:
        print("SYNC ERROR:", repr(e))


# =========================
# MEMBER JOIN
# =========================

@bot.event
async def on_member_join(member):

    # Auto role
    try:
        role_id = D["autorole"].get(gid(member.guild))

        if role_id:
            role = member.guild.get_role(int(role_id))

            if role:
                await member.add_roles(
                    role,
                    reason="OG ADHII Auto Role"
                )

    except Exception as e:
        print("AUTOROLE ERROR:", repr(e))

    # Welcome
    try:
        welcome_data = D["welcome"].get(gid(member.guild))

        if welcome_data:
            channel = member.guild.get_channel(
                int(welcome_data["channel"])
            )

            if channel:
                message = welcome_data.get(
                    "message",
                    "👋 Welcome {user} to **{server}**!"
                )

                message = message.replace(
                    "{user}",
                    member.mention
                ).replace(
                    "{server}",
                    member.guild.name
                )

                await channel.send(message)

    except Exception as e:
        print("WELCOME ERROR:", repr(e))

    await log(
        member.guild,
        "📥 Member Joined",
        f"{member.mention} joined."
    )


# =========================
# MEMBER LEAVE
# =========================

@bot.event
async def on_member_remove(member):
    await log(
        member.guild,
        "📤 Member Left",
        f"**{member}** left."
    )


# =========================
# MEMBER UPDATE
# =========================

@bot.event
async def on_member_update(before, after):

    try:
        if before.nick != after.nick:
            await log(
                after.guild,
                "✏️ Nickname Changed",
                f"{after.mention}: `{before.nick}` → `{after.nick}`"
            )

        before_roles = {role.id for role in before.roles}
        after_roles = {role.id for role in after.roles}

        if before_roles != after_roles:

            added = [
                role.name
                for role in after.roles
                if role.id not in before_roles
            ]

            removed = [
                role.name
                for role in before.roles
                if role.id not in after_roles
            ]

            await log(
                after.guild,
                "🎭 Role Change",
                f"{after.mention}\n"
                f"Added: {', '.join(added) if added else 'None'}\n"
                f"Removed: {', '.join(removed) if removed else 'None'}"
            )

    except Exception as e:
        print("MEMBER UPDATE ERROR:", repr(e))


# =========================
# MESSAGE DELETE
# =========================

@bot.event
async def on_message_delete(message):

    try:
        if (
            message.guild
            and message.author
            and not message.author.bot
        ):
            content = message.content[:1200] or "[no text]"

            await log(
                message.guild,
                "🗑️ Message Deleted",
                f"{message.author.mention} in "
                f"{message.channel.mention}\n"
                f"`{content}`"
            )

    except Exception as e:
        print("DELETE LOG ERROR:", repr(e))


# =========================
# MESSAGE EDIT
# =========================

@bot.event
async def on_message_edit(before, after):

    try:
        if (
            after.guild
            and after.author
            and not after.author.bot
            and before.content != after.content
        ):
            await log(
                after.guild,
                "✏️ Message Edited",
                f"{after.author.mention} in "
                f"{after.channel.mention}\n"
                f"Before: `{before.content[:600]}`\n"
                f"After: `{after.content[:600]}`"
            )

    except Exception as e:
        print("EDIT LOG ERROR:", repr(e))


# =========================
# ANTI SPAM
# =========================

spam = {}


# =========================
# MESSAGE HANDLER
# =========================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if not message.guild:
        return

    guild_id = gid(message.guild)
    content_lower = message.content.lower()

    # -------------------------
    # ANTI LINK
    # -------------------------

    if (
        D["antilink"].get(guild_id)
        and re.search(
            r"https?://|www\.",
            message.content,
            re.IGNORECASE
        )
        and not message.author.guild_permissions.manage_messages
    ):
        try:
            await message.delete()

            await message.channel.send(
                f"🚫 {message.author.mention} links are disabled.",
                delete_after=3
            )

        except discord.Forbidden:
            pass

        except Exception as e:
            print("ANTILINK ERROR:", repr(e))

        return

    # -------------------------
    # BAD WORD FILTER
    # -------------------------

    words = D["badwords"].get(guild_id, [])

    if (
        any(
            re.search(
                r"\b" + re.escape(word) + r"\b",
                content_lower
            )
            for word in words
        )
        and not message.author.guild_permissions.manage_messages
    ):
        try:
            await message.delete()

            await message.channel.send(
                f"🚫 {message.author.mention} "
                f"that word is not allowed.",
                delete_after=3
            )

        except discord.Forbidden:
            pass

        except Exception as e:
            print("BADWORD ERROR:", repr(e))

        return

    # -------------------------
    # ANTI SPAM
    # -------------------------

    if (
        D["antispam"].get(guild_id)
        and not message.author.guild_permissions.manage_messages
    ):
        key = (
            message.guild.id,
            message.author.id
        )

        now = datetime.now(
            timezone.utc
        ).timestamp()

        queue = spam.setdefault(key, [])

        queue[:] = [
            timestamp
            for timestamp in queue
            if now - timestamp < 5
        ]

        queue.append(now)

        if len(queue) >= 6:

            try:
                await message.author.timeout(
                    timedelta(minutes=1),
                    reason="Anti-spam"
                )

                await message.delete()

                await message.channel.send(
                    f"🛡️ {message.author.mention} "
                    f"was timed out for spam.",
                    delete_after=3
                )

            except discord.Forbidden:
                pass

            except Exception as e:
                print("ANTISPAM ERROR:", repr(e))

            return

    # -------------------------
    # XP
    # -------------------------

    xp_key = f"{guild_id}:{message.author.id}"

    old_xp = int(
        D["xp"].get(xp_key, 0)
    )

    new_xp = old_xp + random.randint(5, 15)

    D["xp"][xp_key] = new_xp

    old_level = xp_level(old_xp)
    new_level = xp_level(new_xp)

    if new_level > old_level:

        try:
            await message.channel.send(
                f"🎉 {message.author.mention} "
                f"reached **Level {new_level}**!"
            )
        except:
            pass

    if new_xp % 100 < 20:
        save()

    await bot.process_commands(message)


# =========================
# MODERATION
# =========================

@tree.command(
    name="ban",
    description="Ban a member"
)
@app_commands.checks.has_permissions(
    ban_members=True
)
async def ban(
    interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):
    try:
        await member.ban(reason=reason)

        await reply(
            interaction,
            f"🔨 Banned {member.mention}"
        )

        await log(
            interaction.guild,
            "🔨 Ban",
            f"{member} by {interaction.user.mention}\n{reason}",
            discord.Color.red()
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I cannot ban this member. "
            "Check my role position and Ban Members permission.",
            ephemeral=True
        )


@tree.command(
    name="kick",
    description="Kick a member"
)
@app_commands.checks.has_permissions(
    kick_members=True
)
async def kick(
    interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):
    try:
        await member.kick(reason=reason)

        await reply(
            interaction,
            f"👢 Kicked {member.mention}"
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I cannot kick this member. "
            "Check my role position and Kick Members permission.",
            ephemeral=True
        )


@tree.command(
    name="timeout",
    description="Timeout a member"
)
@app_commands.checks.has_permissions(
    moderate_members=True
)
async def timeout(
    interaction,
    member: discord.Member,
    minutes: int = 10,
    reason: str = "No reason provided"
):

    minutes = max(
        1,
        min(minutes, 40320)
    )

    try:
        await member.timeout(
            timedelta(minutes=minutes),
            reason=reason
        )

        await reply(
            interaction,
            f"⏳ {member.mention} "
            f"timed out for **{minutes} minutes**."
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I cannot timeout this member. "
            "Check Moderate Members permission and role hierarchy.",
            ephemeral=True
        )


@tree.command(
    name="mute",
    description="Mute a member using Discord timeout"
)
@app_commands.checks.has_permissions(
    moderate_members=True
)
async def mute(
    interaction,
    member: discord.Member,
    minutes: int = 10
):

    minutes = max(
        1,
        min(minutes, 40320)
    )

    try:
        await member.timeout(
            timedelta(minutes=minutes),
            reason="Mute"
        )

        await reply(
            interaction,
            f"🔇 Muted {member.mention} "
            f"for **{minutes} minutes**."
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I cannot mute this member.",
            ephemeral=True
        )


@tree.command(
    name="unmute",
    description="Remove timeout"
)
@app_commands.checks.has_permissions(
    moderate_members=True
)
async def unmute(
    interaction,
    member: discord.Member
):

    try:
        await member.timeout(
            None,
            reason="Unmute"
        )

        await reply(
            interaction,
            f"🔊 Unmuted {member.mention}."
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I cannot remove this timeout.",
            ephemeral=True
        )


@tree.command(
    name="warn",
    description="Warn a member"
)
@app_commands.checks.has_permissions(
    moderate_members=True
)
async def warn(
    interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):

    # Server-specific warning
    key = f"{gid(interaction.guild)}:{member.id}"

    D["warns"][key] = (
        D["warns"].get(key, 0) + 1
    )

    save()

    await reply(
        interaction,
        f"⚠️ {member.mention} warned.\n"
        f"Total warnings: **{D['warns'][key]}**\n"
        f"Reason: {reason}"
    )

    await log(
        interaction.guild,
        "⚠️ Warning",
        f"{member.mention} warned by "
        f"{interaction.user.mention}\n"
        f"Reason: {reason}"
    )


# =========================
# CLEAR
# =========================

@tree.command(
    name="clear",
    description="Delete up to 100 messages"
)
@app_commands.checks.has_permissions(
    manage_messages=True
)
async def clear(
    interaction,
    amount: int = 10
):

    if not 1 <= amount <= 100:
        return await reply(
            interaction,
            "❌ Amount must be between **1 and 100**.",
            ephemeral=True
        )

    await reply(
        interaction,
        "🧹 Clearing...",
        ephemeral=True
    )

    try:
        deleted = await interaction.channel.purge(
            limit=amount
        )

        await interaction.channel.send(
            f"🧹 Cleared **{len(deleted)}** messages.",
            delete_after=3
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I need **Manage Messages** permission.",
            ephemeral=True
        )

    except Exception as e:
        print("CLEAR ERROR:", repr(e))

        await reply(
            interaction,
            f"❌ Clear failed: `{type(e).__name__}`",
            ephemeral=True
        )


# =========================
# LOCK
# =========================

@tree.command(
    name="lock",
    description="Lock a channel"
)
@app_commands.checks.has_permissions(
    manage_channels=True
)
async def lock(
    interaction,
    channel: discord.TextChannel = None
):

    channel = channel or interaction.channel

    me = interaction.guild.me

    if me is None:
        return await reply(
            interaction,
            "❌ Bot member could not be found.",
            ephemeral=True
        )

    if not channel.permissions_for(
        me
    ).manage_channels:

        return await reply(
            interaction,
            "❌ I need **Manage Channels** permission.",
            ephemeral=True
        )

    try:
        overwrite = channel.overwrites_for(
            interaction.guild.default_role
        )

        overwrite.send_messages = False

        await channel.set_permissions(
            interaction.guild.default_role,
            overwrite=overwrite,
            reason=f"Channel locked by {interaction.user}"
        )

        await reply(
            interaction,
            f"🔒 Locked {channel.mention}"
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ Discord denied this action. "
            "Give the bot **Manage Channels** permission.",
            ephemeral=True
        )

    except Exception as e:
        print("LOCK ERROR:", repr(e))

        await reply(
            interaction,
            f"❌ Lock failed: `{type(e).__name__}`",
            ephemeral=True
        )


# =========================
# UNLOCK
# =========================

@tree.command(
    name="unlock",
    description="Unlock a channel"
)
@app_commands.checks.has_permissions(
    manage_channels=True
)
async def unlock(
    interaction,
    channel: discord.TextChannel = None
):

    channel = channel or interaction.channel

    me = interaction.guild.me

    if me is None:
        return await reply(
            interaction,
            "❌ Bot member could not be found.",
            ephemeral=True
        )

    if not channel.permissions_for(
        me
    ).manage_channels:

        return await reply(
            interaction,
            "❌ I need **Manage Channels** permission.",
            ephemeral=True
        )

    try:
        overwrite = channel.overwrites_for(
            interaction.guild.default_role
        )

        overwrite.send_messages = None

        await channel.set_permissions(
            interaction.guild.default_role,
            overwrite=overwrite,
            reason=f"Channel unlocked by {interaction.user}"
        )

        await reply(
            interaction,
            f"🔓 Unlocked {channel.mention}"
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ Discord denied this action. "
            "Give the bot **Manage Channels** permission.",
            ephemeral=True
        )

    except Exception as e:
        print("UNLOCK ERROR:", repr(e))

        await reply(
            interaction,
            f"❌ Unlock failed: `{type(e).__name__}`",
            ephemeral=True
        )


# =========================
# SLOWMODE
# =========================

@tree.command(
    name="slowmode",
    description="Set slowmode seconds"
)
@app_commands.checks.has_permissions(
    manage_channels=True
)
async def slowmode(
    interaction,
    seconds: int = 0
):

    seconds = max(
        0,
        min(seconds, 21600)
    )

    try:
        await interaction.channel.edit(
            slowmode_delay=seconds
        )

        await reply(
            interaction,
            f"🐢 Slowmode: **{seconds}s**"
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I need **Manage Channels** permission.",
            ephemeral=True
        )


# =========================
# SECURITY SETTINGS
# =========================

@tree.command(
    name="antispam",
    description="Toggle anti spam"
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
async def antispam(
    interaction,
    enabled: bool
):

    D["antispam"][gid(interaction.guild)] = enabled
    save()

    await reply(
        interaction,
        f"🛡️ Anti-spam "
        f"**{'ON' if enabled else 'OFF'}**"
    )


@tree.command(
    name="antilink",
    description="Toggle anti link"
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
async def antilink(
    interaction,
    enabled: bool
):

    D["antilink"][gid(interaction.guild)] = enabled
    save()

    await reply(
        interaction,
        f"🔗 Anti-link "
        f"**{'ON' if enabled else 'OFF'}**"
    )


@tree.command(
    name="badword",
    description="Add a filtered word"
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
async def badword(
    interaction,
    word: str
):

    word = word.strip().lower()

    if not word:
        return await reply(
            interaction,
            "❌ Enter a word.",
            ephemeral=True
        )

    words = D["badwords"].setdefault(
        gid(interaction.guild),
        []
    )

    if word in words:
        return await reply(
            interaction,
            f"⚠️ `{word}` is already filtered.",
            ephemeral=True
        )

    words.append(word)
    save()

    await reply(
        interaction,
        f"🚫 Added `{word}` to bad-word filter."
    )


# =========================
# LOG SETUP
# =========================

@tree.command(
    name="setlog",
    description="Set this channel as log channel"
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
async def setlog(interaction):

    D["logs"][gid(interaction.guild)] = (
        interaction.channel.id
    )

    save()

    await reply(
        interaction,
        "📊 Log channel set."
    )


# =========================
# WELCOME
# =========================

@tree.command(
    name="welcome",
    description="Set welcome channel and message"
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
async def welcome(
    interaction,
    channel: discord.TextChannel,
    message: str = "👋 Welcome {user} to **{server}**!"
):

    D["welcome"][gid(interaction.guild)] = {
        "channel": channel.id,
        "message": message
    }

    save()

    await reply(
        interaction,
        f"👋 Welcome set to {channel.mention}"
    )


# =========================
# ROLES
# =========================

@tree.command(
    name="autorole",
    description="Set auto role"
)
@app_commands.checks.has_permissions(
    manage_roles=True
)
async def autorole(
    interaction,
    role: discord.Role
):

    if role >= interaction.guild.me.top_role:
        return await reply(
            interaction,
            "❌ I cannot assign this role. "
            "The role must be below my highest role.",
            ephemeral=True
        )

    D["autorole"][gid(interaction.guild)] = role.id
    save()

    await reply(
        interaction,
        f"🎭 Auto role: **{role.name}**"
    )


@tree.command(
    name="addrole",
    description="Add role"
)
@app_commands.checks.has_permissions(
    manage_roles=True
)
async def addrole(
    interaction,
    member: discord.Member,
    role: discord.Role
):

    if role >= interaction.guild.me.top_role:
        return await reply(
            interaction,
            "❌ I cannot manage this role.",
            ephemeral=True
        )

    try:
        await member.add_roles(role)

        await reply(
            interaction,
            f"🎭 Added **{role.name}** to {member.mention}"
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I cannot add this role.",
            ephemeral=True
        )


@tree.command(
    name="removerole",
    description="Remove role"
)
@app_commands.checks.has_permissions(
    manage_roles=True
)
async def removerole(
    interaction,
    member: discord.Member,
    role: discord.Role
):

    if role >= interaction.guild.me.top_role:
        return await reply(
            interaction,
            "❌ I cannot manage this role.",
            ephemeral=True
        )

    try:
        await member.remove_roles(role)

        await reply(
            interaction,
            f"🎭 Removed **{role.name}** from {member.mention}"
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I cannot remove this role.",
            ephemeral=True
        )


@tree.command(
    name="createrole",
    description="Create role"
)
@app_commands.checks.has_permissions(
    manage_roles=True
)
async def createrole(
    interaction,
    name: str
):

    try:
        role = await interaction.guild.create_role(
            name=name,
            reason=f"Role created by {interaction.user}"
        )

        await reply(
            interaction,
            f"🎭 Created {role.mention}"
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I need **Manage Roles** permission.",
            ephemeral=True
        )


# =========================
# CHANNEL MANAGEMENT
# =========================

@tree.command(
    name="createchannel",
    description="Create text channel"
)
@app_commands.checks.has_permissions(
    manage_channels=True
)
async def createchannel(
    interaction,
    name: str
):

    try:
        channel = await interaction.guild.create_text_channel(
            name=name,
            reason=f"Channel created by {interaction.user}"
        )

        await reply(
            interaction,
            f"✅ Created {channel.mention}"
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I need **Manage Channels** permission.",
            ephemeral=True
        )


@tree.command(
    name="deletechannel",
    description="Delete text channel"
)
@app_commands.checks.has_permissions(
    manage_channels=True
)
async def deletechannel(
    interaction,
    channel: discord.TextChannel
):

    try:
        await reply(
            interaction,
            f"🗑️ Deleting {channel.mention}"
        )

        await channel.delete(
            reason=f"Deleted by {interaction.user}"
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I cannot delete this channel.",
            ephemeral=True
        )


@tree.command(
    name="renamechannel",
    description="Rename text channel"
)
@app_commands.checks.has_permissions(
    manage_channels=True
)
async def renamechannel(
    interaction,
    channel: discord.TextChannel,
    name: str
):

    try:
        await channel.edit(
            name=name,
            reason=f"Renamed by {interaction.user}"
        )

        await reply(
            interaction,
            f"✏️ Renamed to **{name}**"
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I cannot rename this channel.",
            ephemeral=True
        )


# =========================
# FUN
# =========================

@tree.command(
    name="ping",
    description="Bot latency"
)
async def ping(interaction):

    await reply(
        interaction,
        f"🏓 Pong! **{round(bot.latency * 1000)}ms**"
    )


@tree.command(
    name="avatar",
    description="Show avatar"
)
async def avatar(
    interaction,
    member: discord.Member = None
):

    member = member or interaction.user

    embed = discord.Embed(
        title=f"🖼 {member.display_name}"
    )

    embed.set_image(
        url=member.display_avatar.url
    )

    await reply(
        interaction,
        embed=embed
    )


@tree.command(
    name="userinfo",
    description="User information"
)
async def userinfo(
    interaction,
    member: discord.Member = None
):

    member = member or interaction.user

    embed = discord.Embed(
        title=f"👤 {member}",
        color=member.color
    )

    embed.add_field(
        name="ID",
        value=str(member.id),
        inline=False
    )

    embed.add_field(
        name="Joined",
        value=(
            discord.utils.format_dt(
                member.joined_at,
                "R"
            )
            if member.joined_at
            else "?"
        )
    )

    embed.add_field(
        name="Created",
        value=discord.utils.format_dt(
            member.created_at,
            "R"
        )
    )

    await reply(
        interaction,
        embed=embed
    )


@tree.command(
    name="server",
    description="Server information"
)
async def server(interaction):

    guild = interaction.guild

    embed = discord.Embed(
        title=f"📊 {guild.name}"
    )

    embed.add_field(
        name="Members",
        value=str(guild.member_count)
    )

    embed.add_field(
        name="Channels",
        value=str(len(guild.channels))
    )

    embed.add_field(
        name="Roles",
        value=str(len(guild.roles))
    )

    await reply(
        interaction,
        embed=embed
    )


@tree.command(
    name="coinflip",
    description="Flip coin"
)
async def coinflip(interaction):

    await reply(
        interaction,
        f"🪙 **{random.choice(['Heads', 'Tails'])}**"
    )


@tree.command(
    name="dice",
    description="Roll dice"
)
async def dice(
    interaction,
    sides: int = 6
):

    sides = max(
        2,
        min(sides, 1000)
    )

    await reply(
        interaction,
        f"🎲 **{random.randint(1, sides)}**"
    )


@tree.command(
    name="joke",
    description="Random joke"
)
async def joke(interaction):

    jokes = [
        "Why did the developer go broke? He used all his cache.",
        "I told my bot to behave. It returned 403.",
        "There are 10 types of people: binary readers and everyone else."
    ]

    await reply(
        interaction,
        random.choice(jokes)
    )


@tree.command(
    name="quote",
    description="Random quote"
)
async def quote(interaction):

    quotes = [
        "“Discipline beats motivation.”",
        "“Consistency compounds.”",
        "“Build first, optimize later.”"
    ]

    await reply(
        interaction,
        random.choice(quotes)
    )


# =========================
# CALCULATOR
# =========================

@tree.command(
    name="calculator",
    description="Basic calculator"
)
async def calculator(
    interaction,
    expression: str
):

    # Only basic calculator characters
    if not re.fullmatch(
        r"[0-9+\-*/(). %]+",
        expression
    ):
        return await reply(
            interaction,
            "❌ Invalid expression.",
            ephemeral=True
        )

    try:
        result = eval(
            expression,
            {"__builtins__": {}},
            {}
        )

        await reply(
            interaction,
            f"🧮 `{expression}` = **{result}**"
        )

    except Exception:
        await reply(
            interaction,
            "❌ Calculation failed.",
            ephemeral=True
        )


# =========================
# POLL
# =========================

@tree.command(
    name="poll",
    description="Create yes/no poll"
)
async def poll(
    interaction,
    question: str
):

    await interaction.response.send_message(
        f"📊 **{question}**\n"
        f"👍 Yes\n"
        f"👎 No"
    )

    message = await interaction.original_response()

    try:
        await message.add_reaction("👍")
        await message.add_reaction("👎")
    except Exception as e:
        print("POLL REACTION ERROR:", repr(e))


# =========================
# LEVELS
# =========================

@tree.command(
    name="rank",
    description="Show XP rank"
)
async def rank(
    interaction,
    member: discord.Member = None
):

    member = member or interaction.user

    xp = int(
        D["xp"].get(
            f"{gid(interaction.guild)}:{member.id}",
            0
        )
    )

    await reply(
        interaction,
        f"🏆 {member.mention}\n"
        f"Level **{xp_level(xp)}** • **{xp} XP**"
    )


@tree.command(
    name="leaderboard",
    description="Top XP members"
)
async def leaderboard(interaction):

    prefix = gid(interaction.guild) + ":"

    rows = sorted(
        [
            (key, value)
            for key, value in D["xp"].items()
            if key.startswith(prefix)
        ],
        key=lambda item: int(item[1]),
        reverse=True
    )[:10]

    output = []

    for number, (key, xp) in enumerate(
        rows,
        1
    ):
        user_id = key.split(":")[1]

        output.append(
            f"**{number}.** <@{user_id}> — {xp} XP"
        )

    await reply(
        interaction,
        "\n".join(output)
        if output
        else "No XP yet."
    )


# =========================
# TICKETS
# =========================

class Ticket(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Create Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="og_ticket"
    )
    async def create_ticket(self, interaction, button):

        try:
            guild_id = gid(interaction.guild)
            setup = D["ticket_setup"].get(guild_id)

            if not setup:
                return await reply(
                    interaction,
                    "❌ Ticket system is not configured.\nUse `/setupsupport` first.",
                    ephemeral=True
                )

            category = interaction.guild.get_channel(
                int(setup["category"])
            )

            if not category or not isinstance(
                category,
                discord.CategoryChannel
            ):
                return await reply(
                    interaction,
                    "❌ Ticket category not found.",
                    ephemeral=True
                )

            name = f"ticket-{interaction.user.id}"

            old = discord.utils.get(
                interaction.guild.text_channels,
                name=name
            )

            if old:
                return await reply(
                    interaction,
                    f"🎫 You already have {old.mention}",
                    ephemeral=True
                )

            overwrites = {
                interaction.guild.default_role:
                    discord.PermissionOverwrite(
                        view_channel=False
                    ),

                interaction.user:
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    ),

                interaction.guild.me:
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_channels=True
                    )
            }

            # Allow staff/support roles if configured
            for role in interaction.guild.roles:
                if (
                    role.name.lower() in [
                        "staff",
                        "support",
                        "moderator",
                        "admin"
                    ]
                ):
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )

            channel = await interaction.guild.create_text_channel(
                name=name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket opened by {interaction.user}"
            )

            D["tickets"][str(channel.id)] = {
                "user": interaction.user.id,
                "created": datetime.now(timezone.utc).isoformat()
            }

            save()

            embed = discord.Embed(
                title="🎫 Support Ticket",
                description=(
                    f"Welcome {interaction.user.mention}!\n\n"
                    "Please explain your issue clearly.\n"
                    "A staff member will assist you shortly."
                ),
                color=discord.Color.blurple()
            )

            await channel.send(
                content=interaction.user.mention,
                embed=embed,
                view=CloseTicket()
            )

            await reply(
                interaction,
                f"🎫 Ticket created: {channel.mention}",
                ephemeral=True
            )

        except discord.Forbidden:
            await reply(
                interaction,
                "❌ I need **Manage Channels** permission.",
                ephemeral=True
            )

        except Exception as e:
            print("TICKET ERROR:", repr(e))

            await reply(
                interaction,
                "❌ Could not create ticket.",
                ephemeral=True
            )


class CloseTicket(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="og_close_ticket"
    )
    async def close_ticket(self, interaction, button):

        try:
            channel = interaction.channel

            if not channel.id.__str__() in D["tickets"]:
                return await reply(
                    interaction,
                    "❌ This is not a ticket channel.",
                    ephemeral=True
                )

            if not (
                interaction.user.guild_permissions.manage_channels
                or D["tickets"][str(channel.id)].get("user")
                == interaction.user.id
            ):
                return await reply(
                    interaction,
                    "❌ You cannot close this ticket.",
                    ephemeral=True
                )

            await reply(
                interaction,
                "🔒 Closing ticket...",
                ephemeral=True
            )

            D["tickets"].pop(str(channel.id), None)
            save()

            await channel.delete(
                reason=f"Ticket closed by {interaction.user}"
            )

        except discord.Forbidden:
            await reply(
                interaction,
                "❌ I cannot delete this ticket channel.",
                ephemeral=True
            )

        except Exception as e:
            print("CLOSE TICKET ERROR:", repr(e))


# =========================
# SETUP SUPPORT SYSTEM
# =========================

@tree.command(
    name="setupsupport",
    description="Create complete ticket support system"
)
@app_commands.checks.has_permissions(
    manage_channels=True
)
async def setupsupport(interaction):

    guild = interaction.guild

    try:

        # -------------------------
        # SUPPORT CATEGORY
        # -------------------------

        category = discord.utils.get(
            guild.categories,
            name="🆘 SUPPORT"
        )

        if not category:

            category = await guild.create_category(
                "🆘 SUPPORT",
                reason=f"Support setup by {interaction.user}"
            )

        # -------------------------
        # CREATE TICKET CHANNEL
        # -------------------------

        ticket_channel = discord.utils.get(
            guild.text_channels,
            name="🎫・create-ticket"
        )

        if not ticket_channel:

            ticket_channel = await guild.create_text_channel(
                "🎫・create-ticket",
                category=category,
                reason="Support ticket setup"
            )

        # -------------------------
        # SUPPORT VC
        # -------------------------

        support_vc = discord.utils.get(
            guild.voice_channels,
            name="🔊・Support VC"
        )

        if not support_vc:

            support_vc = await guild.create_voice_channel(
                "🔊・Support VC",
                category=category,
                reason="Support VC setup"
            )

        # -------------------------
        # SAVE SETUP
        # -------------------------

        D["ticket_setup"][gid(guild)] = {
            "category": category.id,
            "ticket_channel": ticket_channel.id,
            "support_vc": support_vc.id
        }

        save()

        # -------------------------
        # PANEL
        # -------------------------

        embed = discord.Embed(
            title="🎫 Support Center",
            description=(
                "**Need help? Open a ticket.**\n\n"
                "Click the button below to create a private "
                "support ticket.\n\n"
                "🎫 **Create Ticket**\n"
                "🔒 Private staff support\n"
                "🔊 Support VC available"
            ),
            color=discord.Color.blurple()
        )

        embed.set_footer(
            text=f"{guild.name} • Support System"
        )

        await ticket_channel.send(
            embed=embed,
            view=Ticket()
        )

        # -------------------------
        # RESPONSE
        # -------------------------

        await reply(
            interaction,
            "✅ Support system setup completed!\n\n"
            f"📁 Category: {category.mention}\n"
            f"🎫 Ticket: {ticket_channel.mention}\n"
            f"🔊 Support VC: {support_vc.mention}",
            ephemeral=True
        )

    except discord.Forbidden:
        await reply(
            interaction,
            "❌ I need **Manage Channels** permission.",
            ephemeral=True
        )

    except Exception as e:
        print("SUPPORT SETUP ERROR:", repr(e))

        await reply(
            interaction,
            f"❌ Setup failed: `{type(e).__name__}`",
            ephemeral=True
        )


# =========================
# VERIFY
# =========================

class Verify(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="og_verify"
    )
    async def verify_button(
        self,
        interaction,
        button
    ):

        try:
            role_id = D["verify"].get(
                gid(interaction.guild)
            )

            if not role_id:
                return await reply(
                    interaction,
                    "❌ Verification role not configured.",
                    ephemeral=True
                )

            role = interaction.guild.get_role(
                int(role_id)
            )

            if not role:
                return await reply(
                    interaction,
                    "❌ Verification role no longer exists.",
                    ephemeral=True
                )

            if role >= interaction.guild.me.top_role:
                return await reply(
                    interaction,
                    "❌ I cannot assign the verification role. "
                    "Move my bot role above it.",
                    ephemeral=True
                )

            await interaction.user.add_roles(
                role,
                reason="Verification"
            )

            await reply(
                interaction,
                "✅ Verified!",
                ephemeral=True
            )

        except discord.Forbidden:
            await reply(
                interaction,
                "❌ I cannot give the verification role.",
                ephemeral=True
            )

        except Exception as e:
            print("VERIFY ERROR:", repr(e))

            await reply(
                interaction,
                "❌ Verification failed.",
                ephemeral=True
            )


@tree.command(
    name="verify",
    description="Set verify role and send panel"
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
async def verify(
    interaction,
    role: discord.Role
):

    if role >= interaction.guild.me.top_role:
        return await reply(
            interaction,
            "❌ Move my bot role above the verification role.",
            ephemeral=True
        )

    D["verify"][gid(interaction.guild)] = role.id

    save()

    embed = discord.Embed(
        title="🔐 Verification",
        description="Click **Verify** to get access.",
        color=discord.Color.green()
    )

    await interaction.channel.send(
        embed=embed,
        view=Verify()
    )

    await reply(
        interaction,
        "Panel sent.",
        ephemeral=True
    )


# =========================
# SUGGESTION
# =========================

@tree.command(
    name="suggest",
    description="Submit suggestion"
)
async def suggest(
    interaction,
    text: str
):

    await log(
        interaction.guild,
        "💡 Suggestion",
        f"{interaction.user.mention}: {text}"
    )

    await reply(
        interaction,
        "💡 Suggestion submitted.",
        ephemeral=True
    )


# =========================
# REPORT
# =========================

@tree.command(
    name="report",
    description="Report a member"
)
async def report(
    interaction,
    member: discord.Member,
    reason: str
):

    await log(
        interaction.guild,
        "🚨 Report",
        f"Reporter: {interaction.user.mention}\n"
        f"Member: {member.mention}\n"
        f"Reason: {reason}",
        discord.Color.red()
    )

    await reply(
        interaction,
        "🚨 Report sent to staff.",
        ephemeral=True
    )


# =========================
# RULES
# =========================

@tree.command(
    name="rules",
    description="Show rules"
)
async def rules(interaction):

    embed = discord.Embed(
        title="📜 Rules",
        description=(
            "1. Respect others.\n"
            "2. No spam.\n"
            "3. No harmful links.\n"
            "4. Follow Discord ToS.\n"
            "5. Follow staff instructions."
        )
    )

    await reply(
        interaction,
        embed=embed
    )


# =========================
# HELP
# =========================

@tree.command(
    name="help",
    description="Show command categories"
)
async def help_command(interaction):

    embed = discord.Embed(
        title="🤖 OG ADHII BOT",
        description=(
            "Use `/` to browse commands.\n\n"

            "🛡️ **Moderation**\n"
            "Ban • Kick • Timeout • Warn • Mute • "
            "Clear • Lock • Unlock • Slowmode\n\n"

            "🛡️ **Security**\n"
            "Anti-link • Anti-spam • Badword\n\n"

            "🎫 **Tickets**\n"
            "Ticket system\n\n"

            "🎭 **Roles**\n"
            "AutoRole • AddRole • RemoveRole • CreateRole\n\n"

            "📊 **Logs**\n"
            "Join • Leave • Edit • Delete • Role changes\n\n"

            "🎮 **Fun**\n"
            "Ping • Avatar • UserInfo • Server • "
            "Coinflip • Dice • Joke • Quote • Calculator • Poll\n\n"

            "📈 **Levels**\n"
            "Rank • Leaderboard\n\n"

            "🔐 **Verify**\n"
            "Verification system\n\n"

            "⚙️ **Server**\n"
            "Welcome • Logs • Channel management"
        ),
        color=discord.Color.blurple()
    )

    await reply(
        interaction,
        embed=embed
    )


# =========================
# PERSISTENT VIEWS
# =========================

@bot.event
async def setup_hook():

    bot.add_view(Ticket())
    bot.add_view(Verify())

    try:
        await tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print("SETUP SYNC ERROR:", repr(e))


# =========================
# COMMAND ERROR HANDLER
# =========================

@tree.error
async def command_error(
    interaction,
    error
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):

        await reply(
            interaction,
            "❌ You do not have permission.",
            ephemeral=True
        )

        return

    if isinstance(
        error,
        app_commands.errors.BotMissingPermissions
    ):

        await reply(
            interaction,
            "❌ Bot is missing a required permission.",
            ephemeral=True
        )

        return

    if isinstance(
        error,
        app_commands.errors.CommandOnCooldown
    ):

        await reply(
            interaction,
            "⏳ Please wait before using this command again.",
            ephemeral=True
        )

        return

    print(
        "COMMAND ERROR:",
        repr(error)
    )

    await reply(
        interaction,
        f"❌ Command failed.\n"
        f"`{type(error).__name__}`",
        ephemeral=True
    )


# =========================
# RUN
# =========================

bot.run(TOKEN)