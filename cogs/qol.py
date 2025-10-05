import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import asyncio
import re
import config
import database
from PIL import Image, ImageDraw, ImageFont
import io

class QoL(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.reminder_tasks = {}
        self.schedule_tasks = {}
        self.check_reminders.start()
        self.check_schedules.start()

    def _get_afk_duration(self, set_at_time):
        if set_at_time.tzinfo is None:
            set_at_time = set_at_time.replace(tzinfo=datetime.timezone.utc)
        time_diff = datetime.datetime.now(datetime.timezone.utc) - set_at_time
        hours, remainder = divmod(int(time_diff.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h {minutes}m"

    def parse_time(self, time_str, user):
        now = datetime.datetime.now(datetime.timezone.utc)

        time_patterns = {
            r'(\d+)s': lambda m: datetime.timedelta(seconds=int(m.group(1))),
            r'(\d+)m': lambda m: datetime.timedelta(minutes=int(m.group(1))),
            r'(\d+)h': lambda m: datetime.timedelta(hours=int(m.group(1))),
            r'(\d+)d': lambda m: datetime.timedelta(days=int(m.group(1))),
            r'(\d+):(\d+)': lambda m: datetime.timedelta(hours=int(m.group(1)), minutes=int(m.group(2))),
            r'(\d+)/(\d+)/(\d+)\s+(\d+):(\d+)': lambda m: datetime.datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), int(m.group(4)), int(m.group(5)), tzinfo=datetime.timezone.utc) - now,
        }

        for pattern, converter in time_patterns.items():
            match = re.search(pattern, time_str)
            if match:
                try:
                    delta = converter(match)
                    if isinstance(delta, datetime.timedelta):
                        return now + delta
                    return delta
                except ValueError:
                    continue

        return None

    @commands.hybrid_command(name="remind", description="Set a reminder")
    async def remind(self, ctx, when: str, what: str):
        reminder_time = self.parse_time(when, ctx.author)

        if not reminder_time:
            await ctx.send(f"Invalid time format. Use formats like: 1h30m, 2d, 14:30, 25/12/2024 15:00")
            return

        if isinstance(reminder_time, datetime.timedelta):
            reminder_time = datetime.datetime.now(datetime.timezone.utc) + reminder_time

        if reminder_time <= datetime.datetime.now(datetime.timezone.utc):
            await ctx.send("Reminder time must be in the future")
            return

        try:
            db = database.get_database()
            reminders_collection = db.reminders

            reminder_data = {
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "message": what,
                "remind_at": reminder_time,
                "recurring": None,
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            }

            result = reminders_collection.insert_one(reminder_data)

            time_diff = reminder_time - datetime.datetime.now(datetime.timezone.utc)
            hours, remainder = divmod(int(time_diff.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)

            embed = discord.Embed(
                title="Reminder Set",
                description=f"I'll remind you: **{what}**",
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name="When", value=f"<t:{int(reminder_time.timestamp())}:R>", inline=True)
            embed.add_field(name="Time Remaining", value=f"{hours}h {minutes}m", inline=True)

            await ctx.send(embed=embed)

            task_id = f"reminder_{result.inserted_id}"
            task = asyncio.create_task(self.send_reminder(task_id, ctx.author.id, ctx.channel.id, what, reminder_time))
            self.reminder_tasks[task_id] = task

        except Exception as e:
            await ctx.send(f"Failed to set reminder: {str(e)}")

    async def send_reminder(self, task_id, user_id, channel_id, message, remind_time):
        await asyncio.sleep((remind_time - datetime.datetime.now(datetime.timezone.utc)).total_seconds())

        try:
            channel = self.client.get_channel(channel_id)
            if channel:
                user = self.client.get_user(user_id)
                embed = discord.Embed(
                    title="Reminder",
                    description=f"**{message}**",
                    color=discord.Color.from_str(config.config_data.colors.embeds)
                )
                if user:
                    embed.set_footer(text=f"Reminder for {user.display_name}")
                await channel.send(f"<@{user_id}>", embed=embed)
        except Exception as e:
            print(f"Failed to send reminder: {e}")

        if task_id in self.reminder_tasks:
            del self.reminder_tasks[task_id]

    @commands.hybrid_command(name="schedule", description="Create a scheduled event")
    async def schedule(self, ctx, title: str, time: str, channel: discord.TextChannel = None):
        schedule_time = self.parse_time(time, ctx.author)

        if not schedule_time:
            await ctx.send("Invalid time format. Use formats like: 1h30m, 2d, 14:30, 25/12/2024 15:00")
            return

        if isinstance(schedule_time, datetime.timedelta):
            schedule_time = datetime.datetime.now(datetime.timezone.utc) + schedule_time

        if schedule_time <= datetime.datetime.now(datetime.timezone.utc):
            await ctx.send("Schedule time must be in the future")
            return

        target_channel = channel or ctx.channel

        try:
            db = database.get_database()
            schedules_collection = db.schedules

            schedule_data = {
                "user_id": ctx.author.id,
                "channel_id": target_channel.id,
                "title": title,
                "scheduled_at": schedule_time,
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            }

            result = schedules_collection.insert_one(schedule_data)

            time_diff = schedule_time - datetime.datetime.now(datetime.timezone.utc)
            hours, remainder = divmod(int(time_diff.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)

            embed = discord.Embed(
                title="Scheduled Event",
                description=f"**{title}**",
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name="Channel", value=target_channel.mention, inline=True)
            embed.add_field(name="When", value=f"<t:{int(schedule_time.timestamp())}:R>", inline=True)
            embed.add_field(name="Time Remaining", value=f"{hours}h {minutes}m", inline=True)

            await ctx.send(embed=embed)

            task_id = f"schedule_{result.inserted_id}"
            task = asyncio.create_task(self.send_schedule(task_id, target_channel.id, title, schedule_time))
            self.schedule_tasks[task_id] = task

        except Exception as e:
            await ctx.send(f"Failed to create schedule: {str(e)}")

    async def send_schedule(self, task_id, channel_id, title, schedule_time):
        await asyncio.sleep((schedule_time - datetime.datetime.now(datetime.timezone.utc)).total_seconds())

        try:
            channel = self.client.get_channel(channel_id)
            if channel:
                embed = discord.Embed(
                    title="Scheduled Event",
                    description=f"**{title}** is starting now!",
                    color=discord.Color.from_str(config.config_data.colors.embeds)
                )
                await channel.send("@everyone", embed=embed)
        except Exception as e:
            print(f"Failed to send schedule: {e}")

        if task_id in self.schedule_tasks:
            del self.schedule_tasks[task_id]

    @commands.hybrid_command(name="avatar", description="Fetches and displays a high-resolution version of a user's profile picture")
    async def avatar(self, ctx, user: discord.Member = None):
        target_user = user or ctx.author

        embed = discord.Embed(
            title=f"{target_user.display_name}'s Avatar",
            color=discord.Color.from_str(config.config_data.colors.embeds)
        )
        embed.set_image(url=target_user.display_avatar.url)

        await ctx.send(embed=embed)
        return None

    def create_color_image(self, hex_code):
        try:
            if hex_code.startswith('#'):
                hex_code = hex_code[1:]

            if len(hex_code) == 6:
                color_value = int(hex_code, 16)
            else:
                rgb_values = hex_code.split()
                if len(rgb_values) == 3:
                    r, g, b = map(int, rgb_values)
                    color_value = (r << 16) + (g << 8) + b
                else:
                    return None

            r = (color_value >> 16) & 255
            g = (color_value >> 8) & 255
            b = color_value & 255

            img = Image.new('RGB', (200, 200), color=(r, g, b))
            draw = ImageDraw.Draw(img)

            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
            except:
                font = ImageFont.load_default()

            text = f"#{hex_code.upper()}"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            x = (200 - text_width) // 2
            y = (200 - text_height) // 2

            draw.text((x, y), text, fill='white', font=font, stroke_width=1, stroke_fill='black')

            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            return img_bytes

        except:
            return None

    @commands.hybrid_command(name="color", description="Displays a color swatch for a given hex code or RGB value")
    async def color(self, ctx, hex_code: str):
        color_image = self.create_color_image(hex_code)

        if not color_image:
            await ctx.send("Invalid color format. Use hex code like #FF5733 or RGB values like '255 87 51'")
            return

        embed = discord.Embed(
            title="Color Swatch",
            color=discord.Color.from_str(config.config_data.colors.embeds)
        )
        embed.set_image(url="attachment://color.png")

        await ctx.send(embed=embed, file=discord.File(fp=color_image, filename="color.png"))

    @commands.hybrid_command(name="firstmessage", description="Fetches and links to the very first message ever sent in the current channel")
    @app_commands.describe(channel="Optional channel to check")
    async def firstmessage(self, ctx, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        try:
            first = None
            async for m in target.history(limit=1, oldest_first=True):
                first = m
                break
            if not first:
                await ctx.send("No messages found in that channel.")
                return
            embed = discord.Embed(
                title="First Message",
                description=f"[Jump to message]({first.jump_url})",
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name="Author", value=first.author.mention, inline=True)
            embed.timestamp = first.created_at
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I don't have permission to view that channel's history.")
        except Exception as e:
            await ctx.send(f"Failed to fetch first message: {str(e)}")

    @commands.hybrid_command(name="rep", description="Give a reputation point to a user")
    @app_commands.describe(user="The member you want to give a point to", reason="A short message explaining why")
    async def rep(self, ctx, user: discord.Member, *, reason: str = None):
        if user.id == ctx.author.id or user.bot:
            await ctx.send("You cannot give reputation to that user")
            return
        db = database.get_database()
        cooldowns = db.rep_cooldowns
        reputation = db.reputation
        now = datetime.datetime.now(datetime.timezone.utc)
        cd = cooldowns.find_one({"giver_id": ctx.author.id})
        if cd and (now - cd.get("last_given_at", now)).total_seconds() < 86400:
            remaining = 86400 - int((now - cd["last_given_at"]).total_seconds())
            hours, rem = divmod(remaining, 3600)
            minutes, _ = divmod(rem, 60)
            await ctx.send(f"You can give reputation again in {hours}h {minutes}m")
            return
        reputation.update_one({"user_id": user.id}, {"$inc": {"total": 1}}, upsert=True)
        cooldowns.update_one({"giver_id": ctx.author.id}, {"$set": {"last_given_at": now}}, upsert=True)
        embed = discord.Embed(
            title="Reputation Given",
            description=f"{ctx.author.mention} gave a reputation point to {user.mention}" + (f" for: {reason}" if reason else ""),
            color=discord.Color.from_str(config.config_data.colors.embeds)
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='userinfo', description='shows user info')
    @app_commands.describe(user='The user to get information about')
    async def userinfo(self, ctx, user: discord.Member = None):
        if user is None:
            user = ctx.author
        db = database.get_database()
        rep_doc = db.reputation.find_one({"user_id": user.id})
        rep_total = rep_doc.get("total", 0) if rep_doc else 0
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
                f'**Reputation:** `{rep_total}`\n'
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

    @commands.hybrid_group(name="afk", description="Set or clear your AFK status", invoke_without_command=True)
    async def afk(self, ctx):
        await ctx.send_help(ctx.command)

    @afk.command(name="set", description="Set your AFK status with a message")
    async def afk_set(self, ctx, *, message: str):
        try:
            db = database.get_database()
            afk_collection = db.afk
            afk_data = {
                "user_id": ctx.author.id,
                "message": message,
                "set_at": datetime.datetime.now(datetime.timezone.utc)
            }
            afk_collection.replace_one(
                {"user_id": ctx.author.id},
                afk_data,
                upsert=True
            )
            embed = discord.Embed(
                title="AFK Status Set",
                description=f"I'll let others know you're AFK: **{message}**",
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Failed to set AFK status: {str(e)}")

    @afk.command(name="clear", description="Clear your AFK status")
    async def afk_clear(self, ctx):
        try:
            db = database.get_database()
            afk_collection = db.afk
            result = afk_collection.delete_one({"user_id": ctx.author.id})

            if result.deleted_count > 0:
                embed = discord.Embed(
                    title="AFK Status Cleared",
                    description="Welcome back!",
                    color=discord.Color.from_str(config.config_data.colors.embeds)
                )
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="No AFK Status",
                    description="You weren't AFK to begin with!",
                    color=discord.Color.from_str(config.config_data.colors.embeds)
                )
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Failed to clear AFK status: {str(e)}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild or message.interaction_metadata or message.content.startswith('a.'):
            return

        try:
            db = database.get_database()
            afk_collection = db.afk

            author_afk = afk_collection.find_one_and_delete({
                "user_id": message.author.id
            })

            if author_afk:
                duration = self._get_afk_duration(author_afk["set_at"])
                embed = discord.Embed(
                    title="AFK Status Cleared",
                    description=f"Welcome back! You were AFK for {duration}",
                    color=discord.Color.from_str(config.config_data.colors.embeds)
                )
                await message.channel.send(embed=embed, delete_after=10)

            if not message.mentions:
                return

            for user in message.mentions:
                if user.id == message.author.id:
                    continue

                mentioned_afk = afk_collection.find_one({
                    "user_id": user.id
                })

                if mentioned_afk:
                    duration = self._get_afk_duration(mentioned_afk["set_at"])
                    embed = discord.Embed(
                        title=f"{user.display_name} is AFK",
                        description=f"**{mentioned_afk['message']}**",
                        color=discord.Color.from_str(config.config_data.colors.embeds)
                    )
                    embed.set_footer(text=f"AFK for {duration}")
                    await message.channel.send(embed=embed)
        except Exception as e:
            print(f"Error in AFK on_message listener: {e}")

    @tasks.loop(minutes=1)
    async def check_reminders(self):
        db = database.get_database()
        reminders_collection = db.reminders

        now = datetime.datetime.now(datetime.timezone.utc)
        due_reminders = reminders_collection.find({
            "remind_at": {"$lte": now},
            "recurring": None
        })

        for reminder in due_reminders:
            try:
                channel = self.client.get_channel(reminder["channel_id"])
                if channel:
                    user = self.client.get_user(reminder["user_id"])
                    embed = discord.Embed(
                        title="Reminder",
                        description=f"**{reminder['message']}**",
                        color=discord.Color.from_str(config.config_data.colors.embeds)
                    )
                    if user:
                        embed.set_footer(text=f"Reminder for {user.display_name}")
                    await channel.send(f"<@{reminder['user_id']}>", embed=embed)
            except Exception as e:
                print(f"Failed to send reminder: {e}")

            reminders_collection.delete_one({"_id": reminder["_id"]})

    @tasks.loop(minutes=1)
    async def check_schedules(self):
        db = database.get_database()
        schedules_collection = db.schedules

        now = datetime.datetime.now(datetime.timezone.utc)
        due_schedules = schedules_collection.find({
            "scheduled_at": {"$lte": now}
        })

        for schedule in due_schedules:
            try:
                channel = self.client.get_channel(schedule["channel_id"])
                if channel:
                    embed = discord.Embed(
                        title="Scheduled Event",
                        description=f"**{schedule['title']}** is starting now!",
                        color=discord.Color.from_str(config.config_data.colors.embeds)
                    )
                    await channel.send("@everyone", embed=embed)
            except Exception as e:
                print(f"Failed to send schedule: {e}")

            schedules_collection.delete_one({"_id": schedule["_id"]})

    def cog_unload(self):
        for task in self.reminder_tasks.values():
            task.cancel()
        for task in self.schedule_tasks.values():
            task.cancel()
        self.check_reminders.cancel()
        self.check_schedules.cancel()

async def setup(client):
    await client.add_cog(QoL(client))