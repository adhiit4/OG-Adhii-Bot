import os,json,random,re,asyncio
from datetime import datetime,timedelta,timezone
import discord
from discord import app_commands
from discord.ext import commands

TOKEN=os.getenv('DISCORD_TOKEN')
if not TOKEN: raise RuntimeError('DISCORD_TOKEN secret is missing')
DATA='data.json'
try:
    with open(DATA,'r',encoding='utf8') as f: D=json.load(f)
except: D={}
for k,v in {'warns':{},'xp':{},'welcome':{},'autorole':{},'logs':{},'badwords':{},'antilink':{},'antispam':{},'verify':{},'tickets':{}}.items(): D.setdefault(k,v)
def save():
    with open(DATA,'w',encoding='utf8') as f: json.dump(D,f,indent=2)

I=discord.Intents.default(); I.guilds=True; I.members=True; I.messages=True; I.message_content=True; I.voice_states=True
bot=commands.Bot(command_prefix='!',intents=I)
tree=bot.tree

def gid(g): return str(g.id)
async def log(g,title,text,color=discord.Color.blurple()):
    cid=D['logs'].get(gid(g)); ch=g.get_channel(int(cid)) if cid else None
    if ch:
        try: await ch.send(embed=discord.Embed(title=title,description=text,color=color,timestamp=datetime.now(timezone.utc)))
        except: pass
async def reply(i,text=None,embed=None,ephemeral=False):
    if i.response.is_done(): await i.followup.send(text,embed=embed,ephemeral=ephemeral)
    else: await i.response.send_message(text,embed=embed,ephemeral=ephemeral)

def xp_level(x): return int((x/100)**0.5)

@bot.event
async def on_ready():
    await tree.sync(); print(f'ONLINE: {bot.user} | {len(tree.get_commands())} commands')

@bot.event
async def on_member_join(m):
    r=D['autorole'].get(gid(m.guild)); role=m.guild.get_role(int(r)) if r else None
    if role:
        try: await m.add_roles(role,reason='OG ADHII Auto Role')
        except: pass
    w=D['welcome'].get(gid(m.guild)); ch=m.guild.get_channel(int(w['channel'])) if w else None
    if ch:
        msg=w.get('message','👋 Welcome {user} to **{server}**!').replace('{user}',m.mention).replace('{server}',m.guild.name)
        await ch.send(msg)
    await log(m.guild,'📥 Member Joined',f'{m.mention} joined.')

@bot.event
async def on_member_remove(m): await log(m.guild,'📤 Member Left',f'**{m}** left.')
@bot.event
async def on_member_update(a,b):
    if a.nick!=b.nick: await log(b.guild,'✏️ Nickname Changed',f'{b.mention}: `{a.nick}` → `{b.nick}`')
    ar={x.id for x in a.roles}; br={x.id for x in b.roles}
    if ar!=br: await log(b.guild,'🎭 Role Change',f'{b.mention}\nAdded: {", ".join(x.name for x in b.roles if x.id not in ar) or "None"}\nRemoved: {", ".join(x.name for x in a.roles if x.id not in br) or "None"}')
@bot.event
async def on_message_delete(m):
    if m.guild and not m.author.bot: await log(m.guild,'🗑️ Message Deleted',f'{m.author.mention} in {m.channel.mention}\n`{m.content[:1200] or "[no text]"}`')
@bot.event
async def on_message_edit(a,b):
    if b.guild and not b.author.bot and a.content!=b.content: await log(b.guild,'✏️ Message Edited',f'{b.author.mention} in {b.channel.mention}\nBefore: `{a.content[:600]}`\nAfter: `{b.content[:600]}`')

spam={}
@bot.event
async def on_message(m):
    if m.author.bot or not m.guild: return
    g=gid(m.guild); low=m.content.lower()
    if D['antilink'].get(g) and re.search(r'https?://|www\\.',m.content,re.I) and not m.author.guild_permissions.manage_messages:
        try: await m.delete(); await m.channel.send(f'🚫 {m.author.mention} links are disabled.',delete_after=3)
        except: pass
        return
    words=D['badwords'].get(g,[])
    if any(re.search(r'\\b'+re.escape(w)+r'\\b',low) for w in words) and not m.author.guild_permissions.manage_messages:
        try: await m.delete(); await m.channel.send(f'🚫 {m.author.mention} that word is not allowed.',delete_after=3)
        except: pass
        return
    if D['antispam'].get(g) and not m.author.guild_permissions.manage_messages:
        key=(m.guild.id,m.author.id); now=datetime.now(timezone.utc).timestamp(); q=spam.setdefault(key,[]); q[:]=[x for x in q if now-x<5]; q.append(now)
        if len(q)>=6:
            try: await m.author.timeout(timedelta(minutes=1),reason='Anti-spam'); await m.delete()
            except: pass
            return
    key=f'{g}:{m.author.id}'; old=int(D['xp'].get(key,0)); new=old+random.randint(5,15); D['xp'][key]=new
    if xp_level(new)>xp_level(old): await m.channel.send(f'🎉 {m.author.mention} reached **Level {xp_level(new)}**!')
    if new%100<20: save()
    await bot.process_commands(m)

# moderation
@tree.command(name='ban',description='Ban a member')
@app_commands.checks.has_permissions(ban_members=True)
async def ban(i,m:discord.Member,reason:str='No reason provided'):
    await m.ban(reason=reason); await reply(i,f'🔨 Banned {m.mention}'); await log(i.guild,'🔨 Ban',f'{m} by {i.user.mention}\n{reason}',discord.Color.red())
@tree.command(name='kick',description='Kick a member')
@app_commands.checks.has_permissions(kick_members=True)
async def kick(i,m:discord.Member,reason:str='No reason provided'):
    await m.kick(reason=reason); await reply(i,f'👢 Kicked {m.mention}')
@tree.command(name='timeout',description='Timeout a member')
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(i,m:discord.Member,minutes:int=10,reason:str='No reason provided'):
    await m.timeout(timedelta(minutes=max(1,min(minutes,40320))),reason=reason); await reply(i,f'⏳ {m.mention} timed out.')
@tree.command(name='mute',description='Mute a member using Discord timeout')
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(i,m:discord.Member,minutes:int=10): await m.timeout(timedelta(minutes=max(1,minutes)),reason='Mute'); await reply(i,f'🔇 Muted {m.mention}.')
@tree.command(name='unmute',description='Remove timeout')
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute(i,m:discord.Member): await m.timeout(None,reason='Unmute'); await reply(i,f'🔊 Unmuted {m.mention}.')
@tree.command(name='warn',description='Warn a member')
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(i,m:discord.Member,reason:str='No reason provided'):
    k=str(m.id); D['warns'][k]=D['warns'].get(k,0)+1; save(); await reply(i,f'⚠️ {m.mention} warned. Total: **{D["warns"][k]}**')
@tree.command(name='clear',description='Delete up to 100 messages')
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(i,amount:int=10):
    if not 1<=amount<=100: return await reply(i,'❌ Amount must be 1-100.',True)
    await reply(i,'🧹 Clearing...',ephemeral=True); x=await i.channel.purge(limit=amount); await i.channel.send(f'🧹 Cleared **{len(x)}** messages.',delete_after=3)
@tree.command(name='lock',description='Lock a channel')
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(i,channel:discord.TextChannel=None):
    channel=channel or i.channel; o=channel.overwrites_for(i.guild.default_role); o.send_messages=False; await channel.set_permissions(i.guild.default_role,overwrite=o); await reply(i,f'🔒 Locked {channel.mention}')
@tree.command(name='unlock',description='Unlock a channel')
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(i,channel:discord.TextChannel=None):
    channel=channel or i.channel; o=channel.overwrites_for(i.guild.default_role); o.send_messages=None; await channel.set_permissions(i.guild.default_role,overwrite=o); await reply(i,f'🔓 Unlocked {channel.mention}')
@tree.command(name='slowmode',description='Set slowmode seconds')
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(i,seconds:int=0): await i.channel.edit(slowmode_delay=max(0,min(seconds,21600))); await reply(i,f'🐢 Slowmode: **{seconds}s**')

@tree.command(name='antispam',description='Toggle anti spam')
@app_commands.checks.has_permissions(manage_guild=True)
async def antispam(i,enabled:bool): D['antispam'][gid(i.guild)]=enabled; save(); await reply(i,f'🛡 Anti-spam **{"ON" if enabled else "OFF"}**')
@tree.command(name='antilink',description='Toggle anti link')
@app_commands.checks.has_permissions(manage_guild=True)
async def antilink(i,enabled:bool): D['antilink'][gid(i.guild)]=enabled; save(); await reply(i,f'🔗 Anti-link **{"ON" if enabled else "OFF"}**')
@tree.command(name='badword',description='Add a filtered word')
@app_commands.checks.has_permissions(manage_guild=True)
async def badword(i,word:str): D['badwords'].setdefault(gid(i.guild),[]).append(word.lower()); save(); await reply(i,f'🚫 Added `{word}`')

# setup / roles / logs
@tree.command(name='setlog',description='Set this channel as log channel')
@app_commands.checks.has_permissions(manage_guild=True)
async def setlog(i): D['logs'][gid(i.guild)]=i.channel.id; save(); await reply(i,'📊 Log channel set.')
@tree.command(name='welcome',description='Set welcome channel and message')
@app_commands.checks.has_permissions(manage_guild=True)
async def welcome(i,channel:discord.TextChannel,message:str='👋 Welcome {user} to **{server}**!'): D['welcome'][gid(i.guild)]={'channel':channel.id,'message':message}; save(); await reply(i,f'👋 Welcome set to {channel.mention}')
@tree.command(name='autorole',description='Set auto role')
@app_commands.checks.has_permissions(manage_roles=True)
async def autorole(i,role:discord.Role): D['autorole'][gid(i.guild)]=role.id; save(); await reply(i,f'🎭 Auto role: **{role.name}**')
@tree.command(name='addrole',description='Add role')
@app_commands.checks.has_permissions(manage_roles=True)
async def addrole(i,m:discord.Member,role:discord.Role): await m.add_roles(role); await reply(i,f'🎭 Added {role.name} to {m.mention}')
@tree.command(name='removerole',description='Remove role')
@app_commands.checks.has_permissions(manage_roles=True)
async def removerole(i,m:discord.Member,role:discord.Role): await m.remove_roles(role); await reply(i,f'🎭 Removed {role.name} from {m.mention}')
@tree.command(name='createrole',description='Create role')
@app_commands.checks.has_permissions(manage_roles=True)
async def createrole(i,name:str): r=await i.guild.create_role(name=name); await reply(i,f'🎭 Created {r.mention}')
@tree.command(name='createchannel',description='Create text channel')
@app_commands.checks.has_permissions(manage_channels=True)
async def createchannel(i,name:str): c=await i.guild.create_text_channel(name); await reply(i,f'✅ Created {c.mention}')
@tree.command(name='deletechannel',description='Delete text channel')
@app_commands.checks.has_permissions(manage_channels=True)
async def deletechannel(i,channel:discord.TextChannel): await reply(i,f'🗑 Deleting {channel.mention}'); await channel.delete()
@tree.command(name='renamechannel',description='Rename text channel')
@app_commands.checks.has_permissions(manage_channels=True)
async def renamechannel(i,channel:discord.TextChannel,name:str): await channel.edit(name=name); await reply(i,f'✏️ Renamed to **{name}**')

# fun
@tree.command(name='ping',description='Bot latency')
async def ping(i): await reply(i,f'🏓 Pong! **{round(bot.latency*1000)}ms**')
@tree.command(name='avatar',description='Show avatar')
async def avatar(i,m:discord.Member=None): m=m or i.user; e=discord.Embed(title=f'🖼 {m.display_name}'); e.set_image(url=m.display_avatar.url); await reply(i,embed=e)
@tree.command(name='userinfo',description='User information')
async def userinfo(i,m:discord.Member=None):
    m=m or i.user; e=discord.Embed(title=f'👤 {m}',color=m.color); e.add_field(name='ID',value=m.id); e.add_field(name='Joined',value=discord.utils.format_dt(m.joined_at,'R') if m.joined_at else '?'); e.add_field(name='Created',value=discord.utils.format_dt(m.created_at,'R')); await reply(i,embed=e)
@tree.command(name='server',description='Server information')
async def server(i):
    g=i.guild; e=discord.Embed(title=f'📊 {g.name}'); e.add_field(name='Members',value=g.member_count); e.add_field(name='Channels',value=len(g.channels)); e.add_field(name='Roles',value=len(g.roles)); await reply(i,embed=e)
@tree.command(name='coinflip',description='Flip coin')
async def coinflip(i): await reply(i,f'🪙 **{random.choice(["Heads","Tails"])}**')
@tree.command(name='dice',description='Roll dice')
async def dice(i,sides:int=6): await reply(i,f'🎲 **{random.randint(1,max(2,min(sides,1000)))}**')
@tree.command(name='joke',description='Random joke')
async def joke(i): await reply(i,random.choice(['Why did the developer go broke? He used all his cache.','I told my bot to behave. It returned 403.','There are 10 types of people: binary readers and everyone else.']))
@tree.command(name='quote',description='Random quote')
async def quote(i): await reply(i,random.choice(['“Discipline beats motivation.”','“Consistency compounds.”','“Build first, optimize later.”']))
@tree.command(name='calculator',description='Basic calculator')
async def calculator(i,expression:str):
    if not re.fullmatch(r'[0-9+\\-*/(). %]+',expression): return await reply(i,'❌ Invalid expression.',ephemeral=True)
    try: await reply(i,f'🧮 `{expression}` = **{eval(expression,{"__builtins__":{}},{})}**')
    except: await reply(i,'❌ Calculation failed.',ephemeral=True)
@tree.command(name='poll',description='Create yes/no poll')
async def poll(i,question:str):
    await i.response.send_message(f'📊 **{question}**\n👍 Yes\n👎 No'); m=await i.original_response(); await m.add_reaction('👍'); await m.add_reaction('👎')

# levels
@tree.command(name='rank',description='Show XP rank')
async def rank(i,m:discord.Member=None):
    m=m or i.user; x=int(D['xp'].get(f'{gid(i.guild)}:{m.id}',0)); await reply(i,f'🏆 {m.mention}\nLevel **{xp_level(x)}** • **{x} XP**')
@tree.command(name='leaderboard',description='Top XP members')
async def leaderboard(i):
    p=gid(i.guild)+':'; rows=sorted([(k,v) for k,v in D['xp'].items() if k.startswith(p)],key=lambda x:int(x[1]),reverse=True)[:10]; out=[]
    for n,(k,x) in enumerate(rows,1): out.append(f'**{n}.** <@{k.split(":")[1]}> — {x} XP')
    await reply(i,'\n'.join(out) if out else 'No XP yet.')

# tickets + verify
class Ticket(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label='Create Ticket',style=discord.ButtonStyle.primary,emoji='🎫',custom_id='og_ticket')
    async def create(self,i,b):
        name=f'ticket-{i.user.id}'; old=discord.utils.get(i.guild.text_channels,name=name)
        if old: return await reply(i,f'🎫 {old.mention}',ephemeral=True)
        ow={i.guild.default_role:discord.PermissionOverwrite(view_channel=False),i.user:discord.PermissionOverwrite(view_channel=True,send_messages=True),i.guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,manage_channels=True)}
        c=await i.guild.create_text_channel(name,overwrites=ow); D['tickets'][str(c.id)]=i.user.id; save(); await c.send(f'🎫 {i.user.mention} ticket opened.'); await reply(i,f'Created {c.mention}',ephemeral=True)
@tree.command(name='ticket',description='Send ticket panel')
@app_commands.checks.has_permissions(manage_channels=True)
async def ticket(i): await i.channel.send(embed=discord.Embed(title='🎫 Support',description='Click below to open a private ticket.'),view=Ticket()); await reply(i,'Panel sent.',ephemeral=True)
class Verify(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label='Verify',style=discord.ButtonStyle.success,emoji='✅',custom_id='og_verify')
    async def v(self,i,b):
        r=i.guild.get_role(int(D['verify'].get(gid(i.guild),0))) if D['verify'].get(gid(i.guild)) else None
        if not r: return await reply(i,'❌ Verification role not configured.',ephemeral=True)
        await i.user.add_roles(r,reason='Verification'); await reply(i,'✅ Verified!',ephemeral=True)
@tree.command(name='verify',description='Set verify role and send panel')
@app_commands.checks.has_permissions(manage_guild=True)
async def verify(i,role:discord.Role): D['verify'][gid(i.guild)]=role.id; save(); await i.channel.send(embed=discord.Embed(title='🔐 Verification',description='Click Verify.'),view=Verify()); await reply(i,'Panel sent.',ephemeral=True)

@tree.command(name='suggest',description='Submit suggestion')
async def suggest(i,text:str): await log(i.guild,'💡 Suggestion',f'{i.user.mention}: {text}'); await reply(i,'💡 Suggestion submitted.',ephemeral=True)
@tree.command(name='report',description='Report a member')
async def report(i,m:discord.Member,reason:str): await log(i.guild,'🚨 Report',f'Reporter: {i.user.mention}\nMember: {m.mention}\nReason: {reason}',discord.Color.red()); await reply(i,'🚨 Report sent to staff.',ephemeral=True)
@tree.command(name='rules',description='Show rules')
async def rules(i): await reply(i,embed=discord.Embed(title='📜 Rules',description='1. Respect others.\n2. No spam.\n3. No harmful links.\n4. Follow Discord ToS.\n5. Follow staff instructions.'))
@tree.command(name='help',description='Show command categories')
async def help_cmd(i): await reply(i,embed=discord.Embed(title='🤖 OG ADHII BOT',description='Use `/` to browse commands.\n\n🛡 Moderation\nBan • Kick • Timeout • Warn • Mute • Clear • Lock • Unlock • Slowmode\n\n🎫 Tickets • 🎭 Roles • 📊 Logs • 🎮 Fun • 📈 Levels • 🔐 Verify • ⚙️ Server'))

@bot.event
async def setup_hook(): bot.add_view(Ticket()); bot.add_view(Verify())
@tree.error
async def errors(i,e):
    if isinstance(e,app_commands.errors.MissingPermissions): await reply(i,'❌ You do not have permission.',ephemeral=True)
    elif isinstance(e,app_commands.errors.BotMissingPermissions): await reply(i,'❌ Bot is missing a required permission.',ephemeral=True)
    else: print('ERROR:',repr(e)); await reply(i,'❌ Command failed.',ephemeral=True)

bot.run(TOKEN)
 