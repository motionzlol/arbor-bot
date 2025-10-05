import discord
from discord.ext import commands
import random
from typing import Optional
import aiohttp  # Import the aiohttp library for async web requests

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

    @commands.hybrid_command(name="8ball", description="Ask the magic 8-ball a yes/no question")
    async def eight_ball(self, ctx, *, question: str):
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes - definitely.",
            "You may rely on it.", "As I see it, yes.", "Most likely.", "Outlook good.",
            "Yes.", "Signs point to yes.", "Reply hazy, try again.", "Ask again later.",
            "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.",
            "Outlook not so good.", "Very doubtful."
        ]
        await ctx.send(f"**Question:** {question}\n**Answer:** {random.choice(responses)}")

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
                            await ctx.send("Could not parse the meme URL. Please try again.")
                    else:
                        await ctx.send(f"Could not fetch a meme. API returned status: {response.status}")
        except aiohttp.ClientError:
            await ctx.send("An error occurred while trying to connect to the meme API. Please try again later.")
        except Exception as e:
            print(f"An unexpected error occurred in the meme command: {e}")
            await ctx.send("An unexpected error occurred. Please try again later.")


async def setup(client):
    await client.add_cog(FunCog(client))