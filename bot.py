import os
import discord
from discord.ext import commands

intents = discord.Intents.all()

bot = commands.Bot(
    command_prefix="/",
    intents=intents
)
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 10):
    if amount < 1:
        await ctx.send("❌ Enter a valid number.")
        return

    deleted = await ctx.channel.purge(limit=amount + 1)

    msg = await ctx.send(f"🧹 Cleared {len(deleted) - 1} messages.")
    await msg.delete(delay=3)
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN:
    bot.run(TOKEN)
else:
    print("DISCORD_TOKEN is not set.")