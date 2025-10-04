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

    @commands.hybrid_command(name='userinfo', description='shows user info')
    @app_commands.describe(user='The user to get information about')
    async def userinfo(self, ctx, user: discord.Member = None):
        if user is None:
            user = ctx.author
        
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
        
        embed = discord.Embed(
            title=f'{user.display_name}',
            color=user.color if user.color != discord.Color.default() else discord.Color.from_str(config.config_data.colors.embeds),
            timestamp=discord.utils.utcnow()
        )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        
        embed.add_field(
            name=f'{config.config_data.emojis.info} Basic Information',
            value=(
                f'**Username:** `{user.name}`\n'
                f'**ID:** `{user.id}`\n'
                f'**Account Age:** `{created_days} days`\n'
                f'**Created:** <t:{int(user.created_at.timestamp())}:R>'
            ),
            inline=False
        )
        
        if hasattr(user, 'joined_at'):
            embed.add_field(
                name=f'{config.config_data.emojis.home} Server Information',
                value=(
                    f'**Nickname:** `{user.nick or user.display_name}`\n'
                    f'**Joined:** <t:{int(user.joined_at.timestamp())}:R>\n'
                    f'**Server Age:** `{joined_days} days`\n'
                    f'**Top Roles:** {", ".join(role.mention for role in top_roles) if top_roles else "None"}'
                ),
                inline=False
            )
        
        status_text = {
            discord.Status.online: 'Online',
            discord.Status.idle: 'Idle', 
            discord.Status.dnd: 'Do Not Disturb',
            discord.Status.offline: 'Offline'
        }.get(user.status, 'Unknown')
        
        activity_text = 'No activity'
        if user.activity:
            if isinstance(user.activity, discord.Game):
                activity_text = f'Playing {user.activity.name}'
            elif isinstance(user.activity, discord.Streaming):
                activity_text = f'Streaming {user.activity.name}'
            elif isinstance(user.activity, discord.CustomActivity):
                activity_text = user.activity.name or 'Custom Status'
        
        embed.add_field(
            name=f'{config.config_data.emojis.info} Status & Activity',
            value=(
                f'**Status:** {status_text}\n'
                f'**Activity:** {activity_text}'
            ),
            inline=True
        )
        
        key_perms = []
        if user.guild_permissions.administrator:
            key_perms.append(f'{config.config_data.emojis.moderation} Administrator')
        if user.guild_permissions.manage_guild:
            key_perms.append(f'{config.config_data.emojis.edit} Manage Server')
        if user.guild_permissions.manage_messages:
            key_perms.append(f'{config.config_data.emojis.delete} Manage Messages')
        if user.guild_permissions.kick_members:
            key_perms.append(f'{config.config_data.emojis.warning} Kick Members')
        if user.guild_permissions.ban_members:
            key_perms.append(f'{config.config_data.emojis.error} Ban Members')
        
        if key_perms:
            embed.add_field(
                name=f'{config.config_data.emojis.tick} Key Permissions',
                value='\n'.join(key_perms),
                inline=True
            )
        
        embed.set_footer(
            text=f'Requested by {ctx.author.display_name}',
            icon_url=ctx.author.display_avatar.url
        )
        
        await ctx.send(embed=embed)

async def setup(client):
    await client.add_cog(Utilities(client))