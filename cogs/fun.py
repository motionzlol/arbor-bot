import discord
from discord.ext import commands
import random

class FunCog(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.hybrid_command(name="coinflip", description="Flip a coin - heads or tails!")
    async def coinflip(self, ctx):
        result = random.choice(["heads", "tails"])
        await ctx.send(f"**Coin flip result:** {result.capitalize()}!")

    @commands.hybrid_command(name="dice", description="Roll a dice - 1-6!")
    async def dice(self, ctx):
        result = random.randint(1, 6)
        await ctx.send(f"**Dice roll result:** {result}")

async def setup(client):
    await client.add_cog(FunCog(client))