import discord
from discord.ext import commands
from discord import app_commands
import config
import database
from deep_translator import GoogleTranslator

LANGUAGES = {
    'en': 'English',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'it': 'Italian',
    'pt': 'Portuguese',
    'ru': 'Russian',
    'ja': 'Japanese',
    'ko': 'Korean',
    'zh-cn': 'Chinese (Simplified)',
    'zh-tw': 'Chinese (Traditional)',
    'ar': 'Arabic',
    'hi': 'Hindi',
    'nl': 'Dutch',
    'sv': 'Swedish',
    'da': 'Danish',
    'no': 'Norwegian',
    'fi': 'Finnish',
    'pl': 'Polish',
    'tr': 'Turkish',
    'he': 'Hebrew',
    'th': 'Thai',
    'vi': 'Vietnamese',
    'cs': 'Czech',
    'hu': 'Hungarian',
    'ro': 'Romanian',
    'bg': 'Bulgarian',
    'hr': 'Croatian',
    'sk': 'Slovak',
    'sl': 'Slovenian',
    'et': 'Estonian',
    'lv': 'Latvian',
    'lt': 'Lithuanian',
    'mt': 'Maltese',
    'ga': 'Irish',
    'cy': 'Welsh',
    'eu': 'Basque',
    'ca': 'Catalan',
    'gl': 'Galician',
    'uk': 'Ukrainian',
    'be': 'Belarusian',
    'sr': 'Serbian',
    'mk': 'Macedonian',
    'bs': 'Bosnian',
    'sq': 'Albanian',
    'hy': 'Armenian',
    'ka': 'Georgian',
    'az': 'Azerbaijani',
    'kk': 'Kazakh',
    'uz': 'Uzbek',
    'ky': 'Kyrgyz',
    'tg': 'Tajik',
    'tk': 'Turkmen',
    'mn': 'Mongolian',
    'ne': 'Nepali',
    'si': 'Sinhala',
    'ta': 'Tamil',
    'te': 'Telugu',
    'kn': 'Kannada',
    'ml': 'Malayalam',
    'mr': 'Marathi',
    'gu': 'Gujarati',
    'pa': 'Punjabi',
    'bn': 'Bengali',
    'or': 'Odia',
    'as': 'Assamese',
    'ur': 'Urdu',
    'fa': 'Persian',
    'ps': 'Pashto',
    'ku': 'Kurdish',
    'sd': 'Sindhi',
    'dv': 'Divehi',
    'am': 'Amharic',
    'ti': 'Tigrinya',
    'om': 'Oromo',
    'so': 'Somali',
    'sw': 'Swahili',
    'rw': 'Kinyarwanda',
    'rn': 'Kirundi',
    'lg': 'Ganda',
    'ak': 'Akan',
    'tw': 'Twi',
    'ee': 'Ewe',
    'ha': 'Hausa',
    'yo': 'Yoruba',
    'ig': 'Igbo',
    'zu': 'Zulu',
    'xh': 'Xhosa',
    'af': 'Afrikaans',
    'st': 'Southern Sotho',
    'tn': 'Tswana',
    'ts': 'Tsonga',
    've': 'Venda',
    'nr': 'South Ndebele',
    'ss': 'Swati',
    'ny': 'Chichewa',
    'ch': 'Chamorro',
    'mi': 'Maori',
    'sm': 'Samoan',
    'to': 'Tongan',
    'fj': 'Fijian',
    'id': 'Indonesian',
    'ms': 'Malay',
    'jv': 'Javanese',
    'su': 'Sundanese',
    'mg': 'Malagasy',
    'la': 'Latin',
    'el': 'Greek',
    'is': 'Icelandic',
    'kl': 'Greenlandic',
    'fo': 'Faroese',
    'lb': 'Luxembourgish'
}

class TranslationHelper:
    def __init__(self):
        self.cache = {}

    def get_user_language(self, user_id: int) -> str:
        return database.get_user_language_preference(user_id) or 'en'

    def translate_text(self, text: str, target_lang: str) -> str:
        if target_lang == 'en':
            return text

        cache_key = f"{text}:{target_lang}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            if len(text) > 500:
                chunks = [text[i:i+500] for i in range(0, len(text), 500)]
                translated_chunks = []

                for chunk in chunks:
                    if chunk.strip():
                        translator = GoogleTranslator(source='auto', target=target_lang)
                        translated_chunks.append(translator.translate(chunk))
                    else:
                        translated_chunks.append(chunk)

                result = ''.join(translated_chunks)
            else:
                translator = GoogleTranslator(source='auto', target=target_lang)
                result = translator.translate(text)

            self.cache[cache_key] = result
            return result

        except Exception as e:
            print(f"Translation error: {e}")
            return text

    def get_translated_embed_field(self, name: str, value: str, user_id: int):
        target_lang = self.get_user_language(user_id)

        translated_name = self.translate_text(name, target_lang)
        translated_value = self.translate_text(value, target_lang)

        return translated_name, translated_value

translation_helper = TranslationHelper()

class Utilities(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.hybrid_command(name='information', description='Shows bot and system information')
    @app_commands.describe()
    async def information(self, ctx):
        user_lang = translation_helper.get_user_language(ctx.author.id)
        latency = round(self.client.latency * 1000)
        db_latency = config.get_database_ping()

        title = translation_helper.translate_text(f"{config.config_data.bot.name}'s information", user_lang)
        description = translation_helper.translate_text(f"{config.config_data.bot.name} information", user_lang)
        bot_latency_label = translation_helper.translate_text("Bot Latency", user_lang)
        db_latency_label = translation_helper.translate_text("Database Latency", user_lang)
        powered_by = translation_helper.translate_text(f"Powered by {config.config_data.bot.name}", user_lang)

        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.from_str(config.config_data.colors.embeds)
        )

        embed.add_field(
            name=bot_latency_label,
            value=f'{config.config_data.emojis.info} `{latency}ms`',
            inline=True
        )

        if db_latency is not None:
            embed.add_field(
                name=db_latency_label,
                value=f'{config.config_data.emojis.info} `{db_latency}ms`',
                inline=True
            )
        else:
            offline_text = translation_helper.translate_text("Offline", user_lang)
            embed.add_field(
                name=db_latency_label,
                value=f'{config.config_data.emojis.offline} `{offline_text}`',
                inline=True
            )

        embed.set_footer(text=powered_by)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='userinfo', description='shows user info')
    @app_commands.describe(user='The user to get information about')
    async def userinfo(self, ctx, user: discord.Member = None):
        if user is None:
            user = ctx.author

        user_lang = translation_helper.get_user_language(ctx.author.id)
        created_days = (discord.utils.utcnow() - user.created_at).days
        joined_days = (discord.utils.utcnow() - user.joined_at).days if hasattr(user, 'joined_at') else 0

        status_emoji = {
            discord.Status.online: config.config_data.emojis.online,
            discord.Status.idle: config.config_data.emojis.warning,
            discord.Status.dnd: config.config_data.emojis.error,
            discord.Status.offline: config.config_data.emojis.offline
        }.get(user.status, config.config_data.emojis.offline)

        roles = [role for role in user.roles if role != ctx.guild.default_role]
        top_roles = roles[:3]

        basic_info_label = translation_helper.translate_text("Basic Information", user_lang)
        server_info_label = translation_helper.translate_text("Server Information", user_lang)
        status_activity_label = translation_helper.translate_text("Status & Activity", user_lang)
        key_permissions_label = translation_helper.translate_text("Key Permissions", user_lang)
        requested_by = translation_helper.translate_text("Requested by", user_lang)

        username_label = translation_helper.translate_text("Username:", user_lang)
        id_label = translation_helper.translate_text("ID:", user_lang)
        account_age_label = translation_helper.translate_text("Account Age:", user_lang)
        created_label = translation_helper.translate_text("Created:", user_lang)

        basic_info_value = (
            f'**{username_label}** `{user.name}`\n'
            f'**{id_label}** `{user.id}`\n'
            f'**{account_age_label}** `{created_days} {translation_helper.translate_text("days", user_lang)}`\n'
            f'**{created_label}** <t:{int(user.created_at.timestamp())}:R>'
        )

        embed = discord.Embed(
            title=user.display_name,
            color=user.color if user.color != discord.Color.default() else discord.Color.from_str(config.config_data.colors.embeds),
            timestamp=discord.utils.utcnow()
        )

        embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(
            name=f'{config.config_data.emojis.info} {basic_info_label}',
            value=basic_info_value,
            inline=False
        )

        if hasattr(user, 'joined_at'):
            nickname_label = translation_helper.translate_text("Nickname:", user_lang)
            joined_label = translation_helper.translate_text("Joined:", user_lang)
            server_age_label = translation_helper.translate_text("Server Age:", user_lang)
            top_roles_label = translation_helper.translate_text("Top Roles:", user_lang)

            server_info_value = (
                f'**{nickname_label}** `{user.nick or user.display_name}`\n'
                f'**{joined_label}** <t:{int(user.joined_at.timestamp())}:R>\n'
                f'**{server_age_label}** `{joined_days} {translation_helper.translate_text("days", user_lang)}`\n'
                f'**{top_roles_label}** {", ".join(role.mention for role in top_roles) if top_roles else translation_helper.translate_text("None", user_lang)}'
            )

            embed.add_field(
                name=f'{config.config_data.emojis.home} {server_info_label}',
                value=server_info_value,
                inline=False
            )

        status_text = {
            discord.Status.online: translation_helper.translate_text('Online', user_lang),
            discord.Status.idle: translation_helper.translate_text('Idle', user_lang),
            discord.Status.dnd: translation_helper.translate_text('Do Not Disturb', user_lang),
            discord.Status.offline: translation_helper.translate_text('Offline', user_lang)
        }.get(user.status, translation_helper.translate_text('Unknown', user_lang))

        activity_text = translation_helper.translate_text('No activity', user_lang)
        if user.activity:
            if isinstance(user.activity, discord.Game):
                activity_text = translation_helper.translate_text(f'Playing {user.activity.name}', user_lang)
            elif isinstance(user.activity, discord.Streaming):
                activity_text = translation_helper.translate_text(f'Streaming {user.activity.name}', user_lang)
            elif isinstance(user.activity, discord.CustomActivity):
                activity_text = user.activity.name or translation_helper.translate_text('Custom Status', user_lang)

        status_activity_value = (
            f'**{translation_helper.translate_text("Status:", user_lang)}** {status_text}\n'
            f'**{translation_helper.translate_text("Activity:", user_lang)}** {activity_text}'
        )

        embed.add_field(
            name=f'{config.config_data.emojis.info} {status_activity_label}',
            value=status_activity_value,
            inline=True
        )

        key_perms = []
        if user.guild_permissions.administrator:
            key_perms.append(f'{config.config_data.emojis.moderation} {translation_helper.translate_text("Administrator", user_lang)}')
        if user.guild_permissions.manage_guild:
            key_perms.append(f'{config.config_data.emojis.edit} {translation_helper.translate_text("Manage Server", user_lang)}')
        if user.guild_permissions.manage_messages:
            key_perms.append(f'{config.config_data.emojis.delete} {translation_helper.translate_text("Manage Messages", user_lang)}')
        if user.guild_permissions.kick_members:
            key_perms.append(f'{config.config_data.emojis.warning} {translation_helper.translate_text("Kick Members", user_lang)}')
        if user.guild_permissions.ban_members:
            key_perms.append(f'{config.config_data.emojis.error} {translation_helper.translate_text("Ban Members", user_lang)}')

        if key_perms:
            embed.add_field(
                name=f'{config.config_data.emojis.tick} {key_permissions_label}',
                value='\n'.join(key_perms),
                inline=True
            )

        embed.set_footer(
            text=f'{requested_by} {ctx.author.display_name}',
            icon_url=ctx.author.display_avatar.url
        )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='language', description='Set your preferred language for bot responses')
    @app_commands.describe(language='The language you want to use (e.g., en, es, fr, de, it, pt, ru, ja, ko, zh-cn)')
    async def language(self, ctx, language: str = None):
        user_lang = translation_helper.get_user_language(ctx.author.id)

        if language is None:
            current_lang_code = database.get_user_language_preference(ctx.author.id)
            current_lang_name = LANGUAGES.get(current_lang_code, "Unknown") if current_lang_code else "English"

            title = translation_helper.translate_text("Language Settings", user_lang)
            description = translation_helper.translate_text("Set your preferred language for bot responses.", user_lang)
            current_label = translation_helper.translate_text("Current Language", user_lang)
            usage_label = translation_helper.translate_text("Usage", user_lang)
            common_label = translation_helper.translate_text("Common Languages", user_lang)
            powered_by = translation_helper.translate_text(f"Powered by {config.config_data.bot.name}", user_lang)

            embed = discord.Embed(
                title=f'{config.config_data.emojis.info} {title}',
                description=description,
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )

            if current_lang_code:
                current_value = translation_helper.translate_text(f"`{current_lang_code}` - {current_lang_name}", user_lang)
                embed.add_field(
                    name=current_label,
                    value=f'{config.config_data.emojis.tick} {current_value}',
                    inline=False
                )
            else:
                no_lang_text = translation_helper.translate_text("No language set (using English)", user_lang)
                embed.add_field(
                    name=current_label,
                    value=f'{config.config_data.emojis.warning} {no_lang_text}',
                    inline=False
                )

            usage_value = translation_helper.translate_text("`/language <language_code>`\nExample: `/language es` for Spanish", user_lang)
            embed.add_field(
                name=usage_label,
                value=usage_value,
                inline=False
            )

            common_languages_text = (
                '🇺🇸 `en` - English\n'
                '🇪🇸 `es` - Spanish\n'
                '🇫🇷 `fr` - French\n'
                '🇩🇪 `de` - German\n'
                '🇮🇹 `it` - Italian\n'
                '🇵🇹 `pt` - Portuguese\n'
                '🇷🇺 `ru` - Russian\n'
                '🇯🇵 `ja` - Japanese\n'
                '🇰🇷 `ko` - Korean\n'
                '🇨🇳 `zh-cn` - Chinese (Simplified)'
            )
            common_value = translation_helper.translate_text(common_languages_text, user_lang)
            embed.add_field(
                name=common_label,
                value=common_value,
                inline=False
            )

            embed.set_footer(text=powered_by)
            await ctx.send(embed=embed)
            return

        if language.lower() not in LANGUAGES:
            invalid_text = translation_helper.translate_text("Invalid Language", user_lang)
            invalid_desc = translation_helper.translate_text(f"`{language}` is not a valid language code.", user_lang)
            usage_text = translation_helper.translate_text("Use `/language` without arguments to see available languages.", user_lang)

            embed = discord.Embed(
                title=f'{config.config_data.emojis.error} {invalid_text}',
                description=invalid_desc,
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )

            embed.add_field(
                name=translation_helper.translate_text("Usage", user_lang),
                value=usage_text,
                inline=False
            )

            await ctx.send(embed=embed)
            return

        try:
            database.save_user_language_preference(ctx.author.id, language.lower())

            test_translation = GoogleTranslator(source='auto', target=language.lower()).translate("Hello!")

            success_title = translation_helper.translate_text("Language Updated", user_lang)
            success_desc = translation_helper.translate_text(f"Your language preference has been set to `{language.lower()}` - {LANGUAGES.get(language.lower(), 'Unknown')}", user_lang)
            test_label = translation_helper.translate_text("Test Translation", user_lang)

            embed = discord.Embed(
                title=f'{config.config_data.emojis.tick} {success_title}',
                description=success_desc,
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )

            test_value = translation_helper.translate_text(f'English: "Hello!" → {language.lower()}: "{test_translation}"', user_lang)
            embed.add_field(
                name=test_label,
                value=test_value,
                inline=False
            )

            embed.set_footer(text=translation_helper.translate_text(f"Powered by {config.config_data.bot.name}", user_lang))

        except Exception as e:
            error_title = translation_helper.translate_text("Error", user_lang)
            error_desc = translation_helper.translate_text(f"Failed to set language preference: {str(e)}", user_lang)

            embed = discord.Embed(
                title=f'{config.config_data.emojis.error} {error_title}',
                description=error_desc,
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )

        await ctx.send(embed=embed)

async def setup(client):
    await client.add_cog(Utilities(client))