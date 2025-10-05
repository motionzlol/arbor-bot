import discord
from discord.ext import commands
from discord import app_commands

import i18n
import config


class Language(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.hybrid_command(name="language", description="Change your language preference")
    @app_commands.describe(
        code="Language code (e.g., en, es). If omitted, shows your current setting.",
        show_all="If true, list all available languages"
    )
    async def language(self, ctx, code: str | None = None, show_all: bool = False):
        user_id = ctx.author.id
        emojis = config.config_data.emojis
        color = discord.Color.from_str(config.config_data.colors.embeds)

        # Show current setting UI
        if code is None:
            current = i18n.get_user_language(user_id)
            embed = discord.Embed(
                title=f"{emojis.menu} " + i18n.t(user_id, "language.embed_title"),
                color=color
            )
            embed.add_field(
                name=f"{emojis.tick} " + i18n.t(user_id, "language.current_field"),
                value=f"`{current}`",
                inline=False
            )

            available_codes = i18n.available_languages()
            if show_all:
                names = i18n.tr(user_id, "language.names")
                lines = []
                for lang_code in available_codes:
                    try:
                        display = names.get(lang_code, lang_code) if isinstance(names, dict) else lang_code
                    except Exception:
                        display = lang_code
                    marker = emojis.tick if lang_code == current else emojis.right
                    lines.append(f"{marker} `{lang_code}` — {display}")
                value = "\n".join(lines) if lines else i18n.t(user_id, "generic.none")
                embed.add_field(
                    name=f"{emojis.info} " + i18n.t(user_id, "language.available_field"),
                    value=value,
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"{emojis.info} " + i18n.t(user_id, "language.available_field"),
                    value=i18n.t(user_id, "language.show_all_hint", count=len(available_codes)),
                    inline=False
                )

            embed.set_footer(text=i18n.t(user_id, "language.change_hint"))
            await ctx.send(embed=embed)
            return

        # Attempt to set language
        code = code.lower()
        available = i18n.available_languages()
        if code not in available:
            embed = discord.Embed(
                title=f"{emojis.error} " + i18n.t(user_id, "language.embed_title"),
                description=i18n.t(user_id, "language.unsupported", available=", ".join(available)),
                color=color
            )
            await ctx.send(embed=embed)
            return
        i18n.set_user_language(user_id, code)
        embed = discord.Embed(
            title=f"{emojis.tick} " + i18n.t(user_id, "language.embed_title"),
            description=i18n.t(user_id, "language.set_success", language=code),
            color=color
        )
        await ctx.send(embed=embed)


async def setup(client):
    await client.add_cog(Language(client))
