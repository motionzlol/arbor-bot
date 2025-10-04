import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import config

load_dotenv()

token = os.getenv('prodtoken')

if token:
    client = commands.Bot(command_prefix='o.', intents=discord.Intents.all())
    
    async def load_cogs():
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await client.load_extension(f'cogs.{filename[:-3]}')
    
    @client.event
    async def on_ready():
        await load_cogs()
        try:
            synced = await client.tree.sync()
            print(f'Synced {len(synced)} command(s)')
        except Exception as e:
            print(f'Failed to sync commands: {e}')
        print(f'{config.config.bot.name} has got a connection to discord')
        print(f'bot id is: {client.user.id}')
        print(f'connected to {len(client.guilds)} servers')
    
    client.run(token)
else:
    print('set token in .env lol')
