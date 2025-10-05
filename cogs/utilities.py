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
        db_latency = config.get_database_ping()
        
        embed = discord.Embed(
            title=f'{config.config_data.bot.name}\'s information',
            description=f'{config.config_data.bot.name} information',
            color=discord.Color.from_str(config.config_data.colors.embeds)
        )
        
        embed.add_field(
            name='Bot Latency',
            value=f'{config.config_data.emojis.info} `{latency}ms`',
            inline=True
        )
        
        if db_latency is not None:
            embed.add_field(
                name='Database Latency',
                value=f'{config.config_data.emojis.info} `{db_latency}ms`',
                inline=True
            )
        else:
            embed.add_field(
                name='Database Latency',
                value=f'{config.config_data.emojis.offline} `Offline`',
                inline=True
            )
        
        embed.set_footer(text=f'Powered by {config.config_data.bot.name}')
        
        await ctx.send(embed=embed)

async def setup(client):
    await client.add_cog(Utilities(client))