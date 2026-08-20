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
    "ticket_setup": {},
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

    if not channel.permissions_for(me).manage_channels:
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

    if not channel.permissions_for(me).manage_channels:
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

    D["antispam"][gid(int