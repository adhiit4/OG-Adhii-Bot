import os
import json
import random
import re
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN secret is missing")

DATA_FILE = "data.json"
WELCOME_IMAGE = "welcome.png"


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
}


try:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        D = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    D = {}


for key, value in DEFAULT_DATA.items():
    D.setdefault(key, value)


def save():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(D, f, indent=2)
    except Exception as e:
        print("SAVE ERROR:", repr(e))


def gid(guild):
    return str(guild.id)


# =========================================================
# DISCORD SETUP
# =========================================================

intents = discord.Intents.default()

intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.voice_states = True


class OGAhdiBot(commands.Bot):

    async def setup_hook(self):
        try:
            synced = await self.tree.sync()
            print(f"SYNCED COMMANDS: {len(synced)}")
        except Exception as e:
            print("SYNC ERROR:", repr(e))


bot = OGAhdiBot(
    command_prefix="!",
    intents=intents
)

tree = bot.tree


# =========================================================
# HELPERS
# =========================================================

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


async def send_log(
    guild,
    title,
    description,
    color=discord.Color.blurple()
):
    try:
        channel_id = D["logs"].get(gid(guild))

        if not channel_id:
            return

        channel = guild.get_channel(int(channel_id))

        if not channel:
            return

        embed = discord.Embed(
            title=title,
            description=description[:4000],
            color=color
        )

        await channel.send(embed=embed)

    except Exception as e:
        print("LOG ERROR:", repr(e))


def xp_level(xp):
    return int((xp / 100) ** 0.5)


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print("--------------------------------")
    print(f"BOT ONLINE: {bot.user}")
    print(f"BOT ID: {bot.user.id}")
    print(f"SERVERS: {len(bot.guilds)}")
    print("--------------------------------")


# =========================================================
# MEMBER JOIN
# =========================================================

@bot.event
async def on_member_join(member):

    guild_id = gid(member.guild)

    # -----------------------------------------------------
    # AUTO ROLE
    # -----------------------------------------------------

    try:

        role_id = D["autorole"].get(guild_id)

        if role_id:

            role = member.guild.get_role(int(role_id))
            me = member.guild.me

            if role and me and role < me.top_role:

                await member.add_roles(
                    role,
                    reason="OG Adhii Auto Role"
                )

    except Exception as e:
        print("AUTOROLE ERROR:", repr(e))


    # -----------------------------------------------------
    # WELCOME
    # -----------------------------------------------------

    try:

        welcome_data = D["welcome"].get(guild_id)

        if welcome_data:

            channel_id = welcome_data.get("channel")

            channel = member.guild.get_channel(
                int(channel_id)
            ) if channel_id else None

            if channel:

                message = welcome_data.get(
                    "message",
                    "👋 Welcome {user} to **{server}**!"
                )

                message = message.replace(
                    "{user}",
                    member.mention
                )

                message = message.replace(
                    "{server}",
                    member.guild.name
                )

                # -----------------------------------------
                # SEND WELCOME IMAGE
                # -----------------------------------------

                if os.path.exists(WELCOME_IMAGE):

                    file = discord.File(
                        WELCOME_IMAGE,
                        filename="welcome.png"
                    )

                    embed = discord.Embed(
                        description=message,
                        color=discord.Color.blurple()
                    )

                    embed.set_image(
                        url="attachment://welcome.png"
                    )

                    embed.set_footer(
                        text=f"Member #{member.guild.member_count}"
                    )

                    await channel.send(
                        embed=embed,
                        file=file
                    )

                else:

                    await channel.send(message)

    except Exception as e:
        print("WELCOME ERROR:", repr(e))


    await send_log(
        member.guild,
        "📥 Member Joined",
        f"{member.mention} joined the server."
    )


# =========================================================
# MEMBER LEAVE
# =========================================================

@bot.event
async def on_member_remove(member):

    await send_log(
        member.guild,
        "📤 Member Left",
        f"**{member}** left the server."
    )


# =========================================================
# MEMBER UPDATE
# =========================================================

@bot.event
async def on_member_update(before, after):

    try:

        if before.nick != after.nick:

            await send_log(
                after.guild,
                "✏️ Nickname Changed",
                f"{after.mention}\n"
                f"Before: `{before.nick}`\n"
                f"After: `{after.nick}`"
            )

    except Exception as e:
        print("NICK ERROR:", repr(e))


# =========================================================
# MESSAGE DELETE
# =========================================================

@bot.event
async def on_message_delete(message):

    if not message.guild:
        return

    if message.author.bot:
        return

    await send_log(
        message.guild,
        "🗑️ Message Deleted",
        f"{message.author.mention} in "
        f"{message.channel.mention}\n\n"
        f"`{message.content[:1500] or '[No text]'}`"
    )


# =========================================================
# MESSAGE EDIT
# =========================================================

@bot.event
async def on_message_edit(before, after):

    if not after.guild:
        return

    if after.author.bot:
        return

    if before.content == after.content:
        return

    await send_log(
        after.guild,
        "✏️ Message Edited",
        f"{after.author.mention} in "
        f"{after.channel.mention}\n\n"
        f"Before:\n`{before.content[:700]}`\n\n"
        f"After:\n`{after.content[:700]}`"
    )


# =========================================================
# SPAM STORAGE
# =========================================================

spam_tracker = {}


# =========================================================
# MESSAGE EVENT
# =========================================================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if not message.guild:
        return

    guild_id = gid(message.guild)

    content = message.content.lower()


    # =====================================================
    # ANTI LINK
    # =====================================================

    if D["antilink"].get(guild_id):

        has_link = re.search(
            r"https?://|www\.",
            message.content,
            re.IGNORECASE
        )

        if (
            has_link
            and not message.author.guild_permissions.manage_messages
        ):

            try:

                await message.delete()

                await message.channel.send(
                    f"🚫 {message.author.mention} "
                    f"links are disabled.",
                    delete_after=3
                )

            except Exception as e:
                print("ANTILINK ERROR:", repr(e))

            return


    # =====================================================
    # BAD WORDS
    # =====================================================

    bad_words = D["badwords"].get(
        guild_id,
        []
    )

    found_badword = False

    for word in bad_words:

        if re.search(
            r"\b" + re.escape(word) + r"\b",
            content
        ):
            found_badword = True
            break


    if (
        found_badword
        and not message.author.guild_permissions.manage_messages
    ):

        try:

            await message.delete()

            await message.channel.send(
                f"🚫 {message.author.mention} "
                f"that word is not allowed.",
                delete_after=3
            )

        except Exception as e:
            print("BADWORD ERROR:", repr(e))

        return


    # =====================================================
    # ANTI SPAM
    # =====================================================

    if (
        D["antispam"].get(guild_id)
        and not message.author.guild_permissions.manage_messages
    ):

        key = (
            message.guild.id,
            message.author.id
        )

        now = discord.utils.utcnow().timestamp()

        queue = spam_tracker.setdefault(
            key,
            []
        )

        queue[:] = [
            t for t in queue
            if now - t < 5
        ]

        queue.append(now)

        if len(queue) >= 6:

            try:

                await message.author.timeout(
                    timedelta(minutes=1),
                    reason="OG Adhii Anti-Spam"
                )

                await message.delete()

                await message.channel.send(
                    f"🛡️ {message.author.mention} "
                    f"was timed out for spam.",
                    delete_after=3
                )

            except Exception as e:
                print("ANTISPAM ERROR:", repr(e))

            queue.clear()

            return


    # =====================================================
    # XP
    # =====================================================

    xp_key = (
        f"{guild_id}:"
        f"{message.author.id}"
    )

    old_xp = int(
        D["xp"].get(
            xp_key,
            0
        )
    )

    new_xp = (
        old_xp +
        random.randint(5, 15)
    )

    D["xp"][xp_key] = new_xp


    old_level = xp_level(old_xp)
    new_level = xp_level(new_xp)


    if new_level > old_level:

        try:

            await message.channel.send(
                f"🎉 {message.author.mention} "
                f"reached **Level {new_level}**!"
            )

        except Exception:
            pass


    if new_xp % 100 < 20:
        save()


    await bot.process_commands(message)


# =========================================================
# BAN
# =========================================================

@tree.command(
    name="ban",
    description="Ban a member"
)
@app_commands.checks.has_permissions(
    ban_members=True
)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):

    try:

        await member.ban(
            reason=reason
        )

        await reply(
            interaction,
            f"🔨 Banned {member.mention}"
        )

        await send_log(
            interaction.guild,
            "🔨 Member Banned",
            f"{member}\n"
            f"By: {interaction.user.mention}\n"
            f"Reason: {reason}",
            discord.Color.red()
        )

    except discord.Forbidden:

        await reply(
            interaction,
            "❌ I cannot ban this member.",
            ephemeral=True
        )


# =========================================================
# KICK
# =========================================================

@tree.command(
    name="kick",
    description="Kick a member"
)
@app_commands.checks.has_permissions(
    kick_members=True
)
async def kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):

    try:

        await member.kick(
            reason=reason
        )

        await reply(
            interaction,
            f"👢 Kicked {member.mention}"
        )

    except discord.Forbidden:

        await reply(
            interaction,
            "❌ I cannot kick this member.",
            ephemeral=True
        )


# =========================================================
# TIMEOUT
# =========================================================

@tree.command(
    name="timeout",
    description="Timeout a member"
)
@app_commands.checks.has_permissions(
    moderate_members=True
)
async def timeout(
    interaction: discord.Interaction,
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
            f"⏳ {member.mention} timed out "
            f"for **{minutes} minutes**."
        )

    except discord.Forbidden:

        await reply(
            interaction,
            "❌ I cannot timeout this member.",
            ephemeral=True
        )


# =========================================================
# UNMUTE
# =========================================================

@tree.command(
    name="unmute",
    description="Remove timeout"
)
@app_commands.checks.has_permissions(
    moderate_members=True
)
async def unmute(
    interaction: discord.Interaction,
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
            "❌ I cannot unmute this member.",
            ephemeral=True
        )


# =========================================================
# WARN
# =========================================================

@tree.command(
    name="warn",
    description="Warn a member"
)
@app_commands.checks.has_permissions(
    moderate_members=True
)
async def warn(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):

    key = (
        f"{gid(interaction.guild)}:"
        f"{member.id}"
    )

    D["warns"][key] = (
        D["warns"].get(
            key,
            0
        ) + 1
    )

    save()

    total = D["warns"][key]

    await reply(
        interaction,
        f"⚠️ {member.mention} warned.\n"
        f"Warnings: **{total}**\n"
        f"Reason: {reason}"
    )


# =========================================================
# CLEAR
# =========================================================

@tree.command(
    name="clear",
    description="Delete messages"
)
@app_commands.checks.has_permissions(
    manage_messages=True
)
async def clear(
    interaction: discord.Interaction,
    amount: int = 10
):

    if amount < 1 or amount > 100:

        return await reply(
            interaction,
            "❌ Amount must be between 1 and 100.",
            ephemeral=True
        )


    await interaction.response.defer(
        ephemeral=True
    )


    try:

        deleted = await interaction.channel.purge(
            limit=amount
        )

        await interaction.followup.send(
            f"🧹 Cleared **{len(deleted)}** messages.",
            ephemeral=True
        )

    except Exception as e:

        await interaction.followup.send(
            f"❌ Clear failed: `{type(e).__name__}`",
            ephemeral=True
        )


# =========================================================
# LOCK
# =========================================================

@tree.command(
    name="lock",
    description="Lock a channel"
)
@app_commands.checks.has_permissions(
    manage_channels=True
)
async def lock(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None
):

    channel = channel or interaction.channel

    try:

        overwrite = channel.overwrites_for(
            interaction.guild.default_role
        )

        overwrite.send_messages = False

        await channel.set_permissions(
            interaction.guild.default_role,
            overwrite=overwrite,
            reason=f"Locked by {interaction.user}"
        )

        await reply(
            interaction,
            f"🔒 Locked {channel.mention}"
        )

    except Exception as e:

        await reply(
            interaction,
            f"❌ Lock failed: `{type(e).__name__}`",
            ephemeral=True
        )


# =========================================================
# UNLOCK
# =========================================================

@tree.command(
    name="unlock",
    description="Unlock a channel"
)
@app_commands.checks.has_permissions(
    manage_channels=True
)
async def unlock(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None
):

    channel = channel or interaction.channel

    try:

        overwrite = channel.overwrites_for(
            interaction.guild.default_role
        )

        overwrite.send_messages = None

        await channel.set_permissions(
            interaction.guild.default_role,
            overwrite=overwrite,
            reason=f"Unlocked by {interaction.user}"
        )

        await reply(
            interaction,
            f"🔓 Unlocked {channel.mention}"
        )

    except Exception as e:

        await reply(
            interaction,
            f"❌ Unlock failed: `{type(e).__name__}`",
            ephemeral=True
        )


# =========================================================
# SLOWMODE
# =========================================================

@tree.command(
    name="slowmode",
    description="Set channel slowmode"
)
@app_commands.checks.has_permissions(
    manage_channels=True
)
async def slowmode(
    interaction: discord.Interaction,
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
            f"🐢 Slowmode set to **{seconds}s**."
        )

    except Exception as e:

    await reply(
        interaction,
        f"❌ Failed: `{type(e).__name__}`",
        ephemeral=True
    )