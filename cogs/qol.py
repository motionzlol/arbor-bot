import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import asyncio
import re
import config
import database
import i18n
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

        abs_date_match = re.search(r'^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})$', time_str.strip())
        if abs_date_match:
            try:
                dt = datetime.datetime(
                    int(abs_date_match.group(3)),
                    int(abs_date_match.group(1)),
                    int(abs_date_match.group(2)),
                    int(abs_date_match.group(4)),
                    int(abs_date_match.group(5)),
                    tzinfo=datetime.timezone.utc,
                )
                return dt
            except ValueError:
                return None

        abs_time_match = re.search(r'^(\d{1,2}):(\d{2})$', time_str.strip())
        if abs_time_match:
            try:
                target = now.replace(hour=int(abs_time_match.group(1)), minute=int(abs_time_match.group(2)), second=0, microsecond=0)
                if target <= now:
                    target += datetime.timedelta(days=1)
                return target
            except ValueError:
                return None

        matches = re.findall(r'(\d+)\s*([smhd])', time_str.lower())
        if matches:
            total = datetime.timedelta()
            for amount, unit in matches:
                n = int(amount)
                if unit == 's':
                    total += datetime.timedelta(seconds=n)
                elif unit == 'm':
                    total += datetime.timedelta(minutes=n)
                elif unit == 'h':
                    total += datetime.timedelta(hours=n)
                elif unit == 'd':
                    total += datetime.timedelta(days=n)
            return now + total if total.total_seconds() > 0 else None

        return None

    @commands.hybrid_command(name="remind", description="Set a reminder")
    async def remind(self, ctx, when: str, *, what: str):
        reminder_time = self.parse_time(when, ctx.author)

        if not reminder_time:
            await ctx.send(i18n.t(ctx.author.id, "errors.invalid_time_format"))
            return

        if isinstance(reminder_time, datetime.timedelta):
            reminder_time = datetime.datetime.now(datetime.timezone.utc) + reminder_time

        if reminder_time <= datetime.datetime.now(datetime.timezone.utc):
            await ctx.send(i18n.t(ctx.author.id, "errors.time_must_be_future"))
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

            reminders_collection.insert_one(reminder_data)

            time_diff = reminder_time - datetime.datetime.now(datetime.timezone.utc)
            total_secs = int(time_diff.total_seconds())
            hours, remainder = divmod(max(total_secs, 0), 3600)
            minutes, seconds = divmod(remainder, 60)

            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "reminders.set_title"),
                description=i18n.t(ctx.author.id, "reminders.set_description", what=what),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.when"), value=f"<t:{int(reminder_time.timestamp())}:R>", inline=True)
            pretty_remaining = (
                f"{hours}h {minutes}m {seconds}s" if hours else (f"{minutes}m {seconds}s" if minutes else f"{seconds}s")
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.time_remaining"), value=pretty_remaining, inline=True)

            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(i18n.t(ctx.author.id, "errors.failed_set_reminder", error=str(e)))


    @commands.hybrid_command(name="schedule", description="Create a scheduled event")
    async def schedule(self, ctx, title: str, time: str, channel: discord.TextChannel = None):
        schedule_time = self.parse_time(time, ctx.author)

        if not schedule_time:
            await ctx.send(i18n.t(ctx.author.id, "errors.invalid_time_format"))
            return

        if isinstance(schedule_time, datetime.timedelta):
            schedule_time = datetime.datetime.now(datetime.timezone.utc) + schedule_time

        if schedule_time <= datetime.datetime.now(datetime.timezone.utc):
            await ctx.send(i18n.t(ctx.author.id, "errors.schedule_time_must_be_future"))
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
                title=i18n.t(ctx.author.id, "schedules.scheduled_title"),
                description=i18n.t(ctx.author.id, "schedules.scheduled_description", title=title),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.channel"), value=target_channel.mention, inline=True)
            embed.add_field(name=i18n.t(ctx.author.id, "generic.when"), value=f"<t:{int(schedule_time.timestamp())}:R>", inline=True)
            embed.add_field(name=i18n.t(ctx.author.id, "generic.time_remaining"), value=f"{hours}h {minutes}m", inline=True)

            await ctx.send(embed=embed)

            task_id = f"schedule_{result.inserted_id}"
            task = asyncio.create_task(self.send_schedule(task_id, target_channel.id, title, schedule_time))
            self.schedule_tasks[task_id] = task

        except Exception as e:
            await ctx.send(i18n.t(ctx.author.id, "errors.failed_create_schedule", error=str(e)))

    async def send_schedule(self, task_id, channel_id, title, schedule_time):
        await asyncio.sleep((schedule_time - datetime.datetime.now(datetime.timezone.utc)).total_seconds())

        try:
            channel = self.client.get_channel(channel_id)
            if channel:
                embed = discord.Embed(
                    title=i18n.t(None, "schedules.scheduled_title"),
                    description=i18n.t(None, "schedules.starting_now", title=title),
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
            title=i18n.t(ctx.author.id, "avatar.title", name=target_user.display_name),
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
            await ctx.send(i18n.t(ctx.author.id, "errors.invalid_color_format"))
            return

        embed = discord.Embed(
            title=i18n.t(ctx.author.id, "color.title"),
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
                await ctx.send(i18n.t(ctx.author.id, "errors.no_messages_found"))
                return
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "firstmessage.title"),
                description=f"[{i18n.t(ctx.author.id, 'firstmessage.jump')}]({first.jump_url})",
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "firstmessage.author"), value=first.author.mention, inline=True)
            embed.timestamp = first.created_at
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send(i18n.t(ctx.author.id, "errors.no_permission_history"))
        except Exception as e:
            await ctx.send(i18n.t(ctx.author.id, "errors.failed_fetch_first_message", error=str(e)))

    @commands.hybrid_command(name="rep", description="Give a reputation point to a user")
    @app_commands.describe(user="The member you want to give a point to", reason="A short message explaining why")
    async def rep(self, ctx, user: discord.Member, *, reason: str = None):
        if user.id == ctx.author.id or user.bot:
            await ctx.send(i18n.t(ctx.author.id, "errors.cannot_give_rep"))
            return
        db = database.get_database()
        cooldowns = db.rep_cooldowns
        reputation = db.reputation
        now = datetime.datetime.now(datetime.timezone.utc)
        cd = cooldowns.find_one({"giver_id": ctx.author.id})
        if cd:
            last = cd.get("last_given_at", None)
            if isinstance(last, datetime.datetime):
                if last.tzinfo is None:
                    last = last.replace(tzinfo=datetime.timezone.utc)
                elapsed = (now - last).total_seconds()
            else:
                elapsed = float("inf")
        else:
            elapsed = float("inf")
        if elapsed < 86400:
            remaining = 86400 - int(elapsed)
            hours, rem = divmod(remaining, 3600)
            minutes, _ = divmod(rem, 60)
            await ctx.send(i18n.t(ctx.author.id, "errors.rep_cooldown", hours=hours, minutes=minutes))
            return
        reputation.update_one({"user_id": user.id}, {"$inc": {"total": 1}}, upsert=True)
        cooldowns.update_one({"giver_id": ctx.author.id}, {"$set": {"last_given_at": now}}, upsert=True)
        embed = discord.Embed(
            title=i18n.t(ctx.author.id, "rep.given_title"),
            description=i18n.t(ctx.author.id, "rep.given_description", giver=ctx.author.mention, user=user.mention, reason_suffix=(f" for: {reason}" if reason else "")),
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
            name=f"{config.config_data.emojis.info} {i18n.t(ctx.author.id, 'userinfo.basic_information')}",
            value=(
                f"**{i18n.t(ctx.author.id, 'userinfo.username')}:** `{user.name}`\n"
                f"**{i18n.t(ctx.author.id, 'userinfo.id')}:** `{user.id}`\n"
                f"**{i18n.t(ctx.author.id, 'userinfo.reputation')}:** `{rep_total}`\n"
                f"**{i18n.t(ctx.author.id, 'userinfo.account_age')}:** `{i18n.t(ctx.author.id, 'userinfo.days', days=created_days)}`\n"
                f"**{i18n.t(ctx.author.id, 'userinfo.created')}:** <t:{int(user.created_at.timestamp())}:R>"
            ),
            inline=False
        )
        if hasattr(user, 'joined_at'):
            embed.add_field(
                name=f"{config.config_data.emojis.home} {i18n.t(ctx.author.id, 'userinfo.server_information')}",
                value=(
                    f"**{i18n.t(ctx.author.id, 'userinfo.nickname')}:** `{user.nick or user.display_name}`\n"
                    f"**{i18n.t(ctx.author.id, 'userinfo.joined')}:** <t:{int(user.joined_at.timestamp())}:R>\n"
                    f"**{i18n.t(ctx.author.id, 'userinfo.server_age')}:** `{i18n.t(ctx.author.id, 'userinfo.days', days=joined_days)}`\n"
                    f"**{i18n.t(ctx.author.id, 'userinfo.top_roles')}:** {', '.join(role.mention for role in top_roles) if top_roles else i18n.t(ctx.author.id, 'generic.none')}"
                ),
                inline=False
            )
        status_text = {
            discord.Status.online: i18n.t(ctx.author.id, 'userinfo.statuses.online'),
            discord.Status.idle: i18n.t(ctx.author.id, 'userinfo.statuses.idle'), 
            discord.Status.dnd: i18n.t(ctx.author.id, 'userinfo.statuses.dnd'),
            discord.Status.offline: i18n.t(ctx.author.id, 'userinfo.statuses.offline')
        }.get(user.status, i18n.t(ctx.author.id, 'userinfo.statuses.unknown'))
        activity_text = i18n.t(ctx.author.id, 'userinfo.activities.none')
        if user.activity:
            if isinstance(user.activity, discord.Game):
                activity_text = i18n.t(ctx.author.id, 'userinfo.activities.playing', name=user.activity.name)
            elif isinstance(user.activity, discord.Streaming):
                activity_text = i18n.t(ctx.author.id, 'userinfo.activities.streaming', name=user.activity.name)
            elif isinstance(user.activity, discord.CustomActivity):
                activity_text = user.activity.name or i18n.t(ctx.author.id, 'userinfo.activities.custom')
        embed.add_field(
            name=f"{config.config_data.emojis.info} {i18n.t(ctx.author.id, 'userinfo.status_activity')}",
            value=(
                f"**{i18n.t(ctx.author.id, 'userinfo.status')}:** {status_text}\n"
                f"**{i18n.t(ctx.author.id, 'userinfo.activity')}:** {activity_text}"
            ),
            inline=True
        )
        key_perms = []
        if user.guild_permissions.administrator:
            key_perms.append(f"{config.config_data.emojis.moderation} {i18n.t(ctx.author.id, 'userinfo.perms.administrator')}")
        if user.guild_permissions.manage_guild:
            key_perms.append(f"{config.config_data.emojis.edit} {i18n.t(ctx.author.id, 'userinfo.perms.manage_server')}")
        if user.guild_permissions.manage_messages:
            key_perms.append(f"{config.config_data.emojis.delete} {i18n.t(ctx.author.id, 'userinfo.perms.manage_messages')}")
        if user.guild_permissions.kick_members:
            key_perms.append(f"{config.config_data.emojis.warning} {i18n.t(ctx.author.id, 'userinfo.perms.kick_members')}")
        if user.guild_permissions.ban_members:
            key_perms.append(f"{config.config_data.emojis.error} {i18n.t(ctx.author.id, 'userinfo.perms.ban_members')}")
        if key_perms:
            embed.add_field(
                name=f"{config.config_data.emojis.tick} {i18n.t(ctx.author.id, 'userinfo.key_permissions')}",
                value='\n'.join(key_perms),
                inline=True
            )
        embed.set_footer(
            text=i18n.t(ctx.author.id, 'generic.requested_by', name=ctx.author.display_name),
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
                title=i18n.t(ctx.author.id, "afk.set_title"),
                description=i18n.t(ctx.author.id, "afk.set_description", message=message),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(i18n.t(ctx.author.id, "errors.failed_set_afk", error=str(e)))

    @afk.command(name="clear", description="Clear your AFK status")
    async def afk_clear(self, ctx):
        try:
            db = database.get_database()
            afk_collection = db.afk
            result = afk_collection.delete_one({"user_id": ctx.author.id})

            if result.deleted_count > 0:
                embed = discord.Embed(
                    title=i18n.t(ctx.author.id, "afk.cleared_title"),
                    description=i18n.t(ctx.author.id, "afk.cleared_description"),
                    color=discord.Color.from_str(config.config_data.colors.embeds)
                )
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    title=i18n.t(ctx.author.id, "afk.none_title"),
                    description=i18n.t(ctx.author.id, "afk.none_description"),
                    color=discord.Color.from_str(config.config_data.colors.embeds)
                )
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(i18n.t(ctx.author.id, "errors.failed_clear_afk", error=str(e)))

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
                    title=i18n.t(message.author.id, "afk.cleared_title"),
                    description=i18n.t(message.author.id, "afk.cleared_back", duration=duration),
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
                        title=i18n.t(message.author.id, "afk.user_is_afk_title", name=user.display_name),
                        description=f"**{mentioned_afk['message']}**",
                        color=discord.Color.from_str(config.config_data.colors.embeds)
                    )
                    embed.set_footer(text=i18n.t(message.author.id, "afk.footer_afk_for", duration=duration))
                    await message.channel.send(embed=embed)
        except Exception as e:
            print(f"Error in AFK on_message listener: {e}")

    @tasks.loop(seconds=5)
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
                        title=i18n.t(reminder.get("user_id"), "reminders.reminder_title"),
                        description=i18n.t(reminder.get("user_id"), "reminders.reminder_description", message=reminder['message']),
                        color=discord.Color.from_str(config.config_data.colors.embeds)
                    )
                    if user:
                        embed.set_footer(text=i18n.t(reminder.get("user_id"), "reminders.footer_for", name=user.display_name))
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
                        title=i18n.t(schedule.get("user_id"), "schedules.scheduled_title"),
                        description=i18n.t(schedule.get("user_id"), "schedules.starting_now", title=schedule['title']),
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