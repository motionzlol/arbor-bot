import discord
from discord.ext import commands
import random
import config
from .utilities import translation_helper

class FunCog(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.hybrid_command(name="coinflip", description="Flip a coin - heads or tails!")
    async def coinflip(self, ctx):
        user_lang = translation_helper.get_user_language(ctx.author.id)

        result = random.choice(["heads", "tails"])
        result_text = translation_helper.translate_text(f"Coin flip result: {result.capitalize()}!", user_lang)

        await ctx.send(result_text)

    @commands.hybrid_command(name="dice", description="Roll a dice - 1-6!")
    async def dice(self, ctx):
        user_lang = translation_helper.get_user_language(ctx.author.id)

        result = random.randint(1, 6)
        result_text = translation_helper.translate_text(f"Dice roll result: {result}", user_lang)

        await ctx.send(result_text)

async def setup(client):
    await client.add_cog(FunCog(client))