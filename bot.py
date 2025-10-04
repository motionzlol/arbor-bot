import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import config

load_dotenv()

token = os.getenv('prodtoken')

if token:
    client = commands.Bot(command_prefix='o.', intents=discord.Intents.all())
    
    @client.event
    async def on_ready():
        print(f'{config.bot.name} has got a connection to discord')
        print(f'bot id is: {client.user.id}')
        print(f'connected to {len(client.guilds)} servers')
    
    client.run(token)
else:
    print('set token in .env lol')
