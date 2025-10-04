import discord
from discord.ext import commands
from discord import app_commands
import config

class Utilities(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.hybrid_command(name='information', description='Shows bot and system information')
    @app_commands.describe()
    async def information(self, ctx):
        latency = round(self.client.latency * 1000)
        
        embed = discord.Embed(
            title=f'{config.config.bot.name}\'s information',
            description=f'{config.config.bot.name} information',
            color=discord.Color.from_str(config.config.colors.embeds)
        )
        
        embed.add_field(
            name='Bot Latency', 
            value=f'`{latency}ms`', 
            inline=True
        )
        embed.add_field(
            name='Database Latency', 
            value='`N/A`', 
            inline=True
        )
        
        embed.set_footer(text=f'Powered by {config.config.bot.name}')
        
        await ctx.send(embed=embed)

async def setup(client):
    await client.add_cog(Utilities(client))