import discord
from discord.ext import commands
import random
from typing import Optional
import aiohttp
import i18n

class FunCog(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.hybrid_command(name="coinflip", description="Flip a coin - heads or tails!")
    async def coinflip(self, ctx):
        label = random.choice([
            i18n.t(ctx.author.id, "fun.coin_heads"),
            i18n.t(ctx.author.id, "fun.coin_tails"),
        ])
        await ctx.send(i18n.t(ctx.author.id, "fun.coinflip_result", result=label))

    @commands.hybrid_command(name="dice", description="Roll a dice - 1-6!")
    async def dice(self, ctx):
        result = random.randint(1, 6)
        await ctx.send(i18n.t(ctx.author.id, "fun.dice_result", result=result))

    @commands.hybrid_command(name="8ball", description="Ask the magic 8-ball a yes/no question")
    async def eight_ball(self, ctx, *, question: str):
        responses = i18n.tr(ctx.author.id, "fun.8ball_responses")
        if not isinstance(responses, list) or not responses:
            responses = ["Yes.", "No."]
        answer = random.choice(responses)
        await ctx.send(i18n.t(ctx.author.id, "fun.8ball_format", question=question, answer=answer))

    @commands.hybrid_command(name="meme", description="Get a random meme from the internet")
    async def meme(self, ctx):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://meme-api.com/gimme") as response:
                    if response.status == 200:
                        data = await response.json()
                        meme_url = data.get("url")
                        if meme_url:
                            await ctx.send(meme_url)
                        else:
                            await ctx.send(i18n.t(ctx.author.id, "fun.meme_parse_fail"))
                    else:
                        await ctx.send(i18n.t(ctx.author.id, "fun.meme_api_status", status=response.status))
        except aiohttp.ClientError:
            await ctx.send(i18n.t(ctx.author.id, "fun.meme_client_error"))
        except Exception as e:
            print(f"An unexpected error occurred in the meme command: {e}")
            await ctx.send(i18n.t(ctx.author.id, "fun.unexpected_error"))


async def setup(client):
    await client.add_cog(FunCog(client))