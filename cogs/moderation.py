import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import re
import database
from pymongo import ReturnDocument
import config
import i18n

class Moderation(commands.Cog):
    def __init__(self, client):
        self.client = client
        self._start_tasks()

    def _start_tasks(self):
        if not self.check_expired_locks.is_running():
            self.check_expired_locks.start()

    def parse_time(self, time_str):
        if not time_str:
            return None
        now = datetime.datetime.now(datetime.timezone.utc)
        patterns = [
            (r"^(\d+)s$", lambda m: datetime.timedelta(seconds=int(m.group(1)))),
            (r"^(\d+)m$", lambda m: datetime.timedelta(minutes=int(m.group(1)))),
            (r"^(\d+)h$", lambda m: datetime.timedelta(hours=int(m.group(1)))),
            (r"^(\d+)d$", lambda m: datetime.timedelta(days=int(m.group(1)))),
            (r"^(\d+):(\d+)$", lambda m: datetime.timedelta(hours=int(m.group(1)), minutes=int(m.group(2)))),
        ]
        for pat, conv in patterns:
            m = re.match(pat, time_str.strip())
            if m:
                delta = conv(m)
                return now + delta if isinstance(delta, datetime.timedelta) else delta
        return None

    def _get_db(self):
        return database.get_database()

    def _get_settings(self, guild_id: int) -> dict:
        db = self._get_db()
        doc = db.moderation_settings.find_one({"guild_id": guild_id}) or {}
        default = {
            "guild_id": guild_id,
            "logs_channel_id": None,
            "log_warnings": True,
            "log_locks": True,
            "log_slowmode": True,
            "notify_dm": True,
        }
        default.update({k: doc.get(k, default[k]) for k in default.keys()})
        return default

    def _save_settings(self, guild_id: int, **updates):
        db = self._get_db()
        db.moderation_settings.update_one(
            {"guild_id": guild_id}, {"$set": updates}, upsert=True
        )

    def _get_logs_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        settings = self._get_settings(guild.id)
        ch_id = settings.get("logs_channel_id")
        if ch_id:
            ch = guild.get_channel(int(ch_id))
            if isinstance(ch, discord.TextChannel):
                return ch
        return None

    async def _log(self, guild: discord.Guild, embed: discord.Embed):
        try:
            ch = self._get_logs_channel(guild)
            if ch is None:
                return
            await ch.send(embed=embed)
        except Exception:
            return

    def _next_warning_case(self, guild_id: int) -> int:
        db = self._get_db()
        doc = db.warning_counters.find_one_and_update(
            {"guild_id": guild_id},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(doc.get("seq", 1))

    async def _issue_warning(self, ctx, member: discord.Member, reason: str, evidence: discord.Attachment | None = None):
        if member is None or reason is None or len(reason.strip()) == 0:
            await ctx.send(i18n.t(ctx.author.id, "errors.invalid_duration_format"))
            return
        if member.id == ctx.author.id:
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.cannot_warn_self"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            await ctx.send(embed=embed)
            return
        if member.bot:
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.cannot_warn_bot"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            await ctx.send(embed=embed)
            return
        if ctx.guild.owner_id == member.id:
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.cannot_warn_owner"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            await ctx.send(embed=embed)
            return
        if ctx.author != ctx.guild.owner and member.top_role >= ctx.author.top_role:
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.cannot_warn_higher"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            await ctx.send(embed=embed)
            return
        me = ctx.guild.me
        if isinstance(me, discord.Member) and member.top_role >= me.top_role:
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.bot_cannot_warn_higher"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            await ctx.send(embed=embed)
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        db = self._get_db()
        case_id = self._next_warning_case(ctx.guild.id)
        att = None
        if evidence is not None:
            try:
                att = {"id": evidence.id, "filename": evidence.filename, "url": evidence.url}
            except Exception:
                att = None
        if att is None and getattr(ctx, "message", None) is not None:
            try:
                if ctx.message.attachments:
                    a = ctx.message.attachments[0]
                    att = {"id": a.id, "filename": a.filename, "url": a.url}
            except Exception:
                pass
        doc = {
            "guild_id": ctx.guild.id,
            "user_id": member.id,
            "moderator_id": ctx.author.id,
            "reason": reason,
            "created_at": now,
            "case_id": case_id,
            "attachment": att,
        }
        db.warnings.insert_one(doc)
        total = db.warnings.count_documents({"guild_id": ctx.guild.id, "user_id": member.id})
        color = discord.Color.from_str(config.config_data.colors.embeds)
        try:
            dm = discord.Embed(
                title=f"{config.config_data.emojis.warning} " + i18n.t(member.id, "moderation.warning_dm_title"),
                description=i18n.t(member.id, "moderation.warning_dm_description", server=ctx.guild.name),
                color=color
            )
            dm.add_field(name=i18n.t(member.id, "generic.reason"), value=reason, inline=False)
            dm.add_field(name=i18n.t(member.id, "moderation.total_warnings"), value=str(total), inline=True)
            dm.set_footer(text=f"#{case_id}")
            await member.send(embed=dm)
        except Exception:
            pass
        embed = discord.Embed(
            title=f"{config.config_data.emojis.moderation} " + i18n.t(ctx.author.id, "moderation.warn_success_title"),
            color=color
        )
        embed.add_field(name=i18n.t(ctx.author.id, "generic.user"), value=f"{member.mention} ({member.id})", inline=True)
        embed.add_field(name=i18n.t(ctx.author.id, "generic.moderator"), value=f"{ctx.author.mention}", inline=True)
        embed.add_field(name=i18n.t(ctx.author.id, "generic.when"), value=f"<t:{int(now.timestamp())}:R>", inline=True)
        embed.add_field(name=i18n.t(ctx.author.id, "generic.reason"), value=reason, inline=False)
        if att and att.get("url"):
            embed.add_field(name=i18n.t(ctx.author.id, "generic.attachment"), value=f"[\u200b]({att['url']})", inline=False)
        embed.add_field(name=i18n.t(ctx.author.id, "moderation.total_warnings"), value=str(total), inline=True)
        embed.set_footer(text=f"#{case_id}")
        await ctx.send(embed=embed)
        try:
            settings = self._get_settings(ctx.guild.id)
            if settings.get("log_warnings"):
                log = discord.Embed(
                    title=f"{config.config_data.emojis.moderation} " + i18n.t(ctx.author.id, "moderation.warn_success_title"),
                    color=color
                )
                log.add_field(name=i18n.t(ctx.author.id, "generic.user"), value=f"{member} ({member.id})", inline=True)
                log.add_field(name=i18n.t(ctx.author.id, "generic.moderator"), value=f"{ctx.author}", inline=True)
                log.add_field(name=i18n.t(ctx.author.id, "generic.when"), value=f"<t:{int(now.timestamp())}:R>", inline=True)
                log.add_field(name=i18n.t(ctx.author.id, "generic.reason"), value=reason, inline=False)
                if att and att.get("url"):
                    log.add_field(name=i18n.t(ctx.author.id, "generic.attachment"), value=f"[\u200b]({att['url']})", inline=False)
                log.add_field(name=i18n.t(ctx.author.id, "moderation.total_warnings"), value=str(total), inline=True)
                log.set_footer(text=f"#{case_id}")
                await self._log(ctx.guild, log)
        except Exception:
            pass

    async def _apply_lock(self, channel: discord.TextChannel, reason: str, moderator: discord.Member, expires_at: datetime.datetime | None):
        db = self._get_db()
        coll = db.channel_locks
        roles_to_lock = [r for r in channel.guild.roles if r < moderator.top_role]
        previous_overwrites = []
        for role in roles_to_lock:
            co = channel.overwrites_for(role)
            prev_send = co.send_messages
            previous_overwrites.append({"role_id": role.id, "prev": prev_send})
            await channel.set_permissions(role, send_messages=False, reason=reason or "Channel locked")
        doc = {
            "guild_id": channel.guild.id,
            "channel_id": channel.id,
            "moderator_id": moderator.id,
            "action": "lock",
            "reason": reason,
            "previous_overwrites": previous_overwrites,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "expires_at": expires_at,
            "active": True,
        }
        coll.insert_one(doc)
        return previous_overwrites

    async def _apply_unlock(self, channel: discord.TextChannel, reason: str, moderator: discord.Member):
        db = self._get_db()
        coll = db.channel_locks
        active = coll.find_one({"channel_id": channel.id, "guild_id": channel.guild.id, "active": True})
        restored = False
        if active is not None and active.get("previous_overwrites"):
            for entry in active["previous_overwrites"]:
                role = channel.guild.get_role(entry["role_id"])
                if role is None:
                    continue
                await channel.set_permissions(role, send_messages=entry.get("prev", None), reason=reason or "Channel unlocked")
            restored = True
        if not restored:
            default_role = channel.guild.default_role
            prev = active.get("previous_send_messages", None) if active else None
            await channel.set_permissions(default_role, send_messages=prev, reason=reason or "Channel unlocked")
        if active is not None:
            coll.update_one({"_id": active["_id"]}, {"$set": {"active": False, "released_at": datetime.datetime.now(datetime.timezone.utc)}})
        coll.insert_one({
            "guild_id": channel.guild.id,
            "channel_id": channel.id,
            "moderator_id": moderator.id,
            "action": "unlock",
            "reason": reason,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        })

    @commands.hybrid_command(name="lock", description="Lock the current channel with optional duration and reason")
    @app_commands.describe(duration="e.g. 10m, 2h, 1d", reason="Reason for locking")
    @commands.has_permissions(manage_channels=True, manage_roles=True)
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def lock(self, ctx, duration: str = None, *, reason: str = None):
        target = ctx.channel
        expires_at = self.parse_time(duration) if duration else None
        if duration and not expires_at:
            if reason is None:
                reason = duration
                duration = None
            else:
                await ctx.send(i18n.t(ctx.author.id, "errors.invalid_duration_format"))
                return
        prev = await self._apply_lock(target, reason, ctx.author, expires_at)
        embed = discord.Embed(
            title=i18n.t(ctx.author.id, "moderation.channel_locked"),
            color=discord.Color.from_str(config.config_data.colors.embeds)
        )
        embed.add_field(name=i18n.t(ctx.author.id, "generic.channel"), value=target.mention, inline=True)
        if reason:
            embed.add_field(name=i18n.t(ctx.author.id, "generic.reason"), value=reason, inline=True)
        if expires_at:
            embed.add_field(name=i18n.t(ctx.author.id, "generic.unlocks"), value=f"<t:{int(expires_at.timestamp())}:R>", inline=True)
        await ctx.send(embed=embed)
        try:
            settings = self._get_settings(ctx.guild.id)
            if settings.get("log_locks"):
                log = discord.Embed(
                    title=i18n.t(ctx.author.id, "moderation.channel_locked"),
                    color=discord.Color.from_str(config.config_data.colors.embeds)
                )
                log.add_field(name=i18n.t(ctx.author.id, "generic.channel"), value=target.mention, inline=True)
                if reason:
                    log.add_field(name=i18n.t(ctx.author.id, "generic.reason"), value=reason, inline=True)
                if expires_at:
                    log.add_field(name=i18n.t(ctx.author.id, "generic.unlocks"), value=f"<t:{int(expires_at.timestamp())}:R>", inline=True)
                log.add_field(name=i18n.t(ctx.author.id, "generic.moderator"), value=str(ctx.author), inline=True)
                await self._log(ctx.guild, log)
        except Exception:
            pass

    @commands.hybrid_command(name="unlock", description="Unlock the current channel and optionally state a reason")
    @app_commands.describe(reason="Reason for unlocking")
    @commands.has_permissions(manage_channels=True, manage_roles=True)
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def unlock(self, ctx, *, reason: str = None):
        target = ctx.channel
        await self._apply_unlock(target, reason, ctx.author)
        embed = discord.Embed(
            title=i18n.t(ctx.author.id, "moderation.channel_unlocked"),
            color=discord.Color.from_str(config.config_data.colors.embeds)
        )
        embed.add_field(name=i18n.t(ctx.author.id, "generic.channel"), value=target.mention, inline=True)
        if reason:
            embed.add_field(name=i18n.t(ctx.author.id, "generic.reason"), value=reason, inline=True)
        await ctx.send(embed=embed)
        try:
            note = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.channel_unlocked"),
                description=i18n.t(ctx.author.id, "moderation.unlocked_note"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            await target.send(embed=note)
        except Exception:
            pass
        try:
            settings = self._get_settings(ctx.guild.id)
            if settings.get("log_locks"):
                log = discord.Embed(
                    title=i18n.t(ctx.author.id, "moderation.channel_unlocked"),
                    color=discord.Color.from_str(config.config_data.colors.embeds)
                )
                log.add_field(name=i18n.t(ctx.author.id, "generic.channel"), value=target.mention, inline=True)
                if reason:
                    log.add_field(name=i18n.t(ctx.author.id, "generic.reason"), value=reason, inline=True)
                log.add_field(name=i18n.t(ctx.author.id, "generic.moderator"), value=str(ctx.author), inline=True)
                await self._log(ctx.guild, log)
        except Exception:
            pass

    @commands.hybrid_command(name="slowmode", description="Set the current channel's slowmode duration")
    @app_commands.describe(duration="e.g. off, 0, 10s, 2m, 1h", reason="Reason for changing slowmode")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx, duration: str, *, reason: str = None):
        target: discord.TextChannel = ctx.channel

        def parse_slowmode(s: str) -> int | None:
            if s is None:
                return None
            s = s.strip().lower()
            if s in {"off", "disable", "disabled", "none", "0"}:
                return 0
            if s.isdigit():
                return int(s)
            m = re.match(r"^(\d+)s$", s)
            if m:
                return int(m.group(1))
            m = re.match(r"^(\d+)m$", s)
            if m:
                return int(m.group(1)) * 60
            m = re.match(r"^(\d+)h$", s)
            if m:
                return int(m.group(1)) * 3600
            return None

        seconds = parse_slowmode(duration)
        if seconds is None:
            await ctx.send(i18n.t(ctx.author.id, "errors.invalid_duration_format"))
            return
        if seconds < 0:
            seconds = 0
        if seconds > 21600:
            seconds = 21600

        try:
            await target.edit(slowmode_delay=seconds, reason=reason or "Slowmode updated")
        except Exception:
            await ctx.send(i18n.t(ctx.author.id, "errors.invalid_duration_format"))
            return

        embed = discord.Embed(
            title=i18n.t(ctx.author.id, "moderation.slowmode_set"),
            color=discord.Color.from_str(config.config_data.colors.embeds)
        )
        embed.add_field(name=i18n.t(ctx.author.id, "generic.channel"), value=target.mention, inline=True)
        sm_value = i18n.t(ctx.author.id, "moderation.slowmode_off") if seconds == 0 else f"{seconds}s"
        embed.add_field(name=i18n.t(ctx.author.id, "moderation.slowmode_label"), value=sm_value, inline=True)
        if reason:
            embed.add_field(name=i18n.t(ctx.author.id, "generic.reason"), value=reason, inline=True)
        await ctx.send(embed=embed)
        try:
            settings = self._get_settings(ctx.guild.id)
            if settings.get("log_slowmode"):
                log = discord.Embed(
                    title=i18n.t(ctx.author.id, "moderation.slowmode_set"),
                    color=discord.Color.from_str(config.config_data.colors.embeds)
                )
                log.add_field(name=i18n.t(ctx.author.id, "generic.channel"), value=target.mention, inline=True)
                log.add_field(name=i18n.t(ctx.author.id, "moderation.slowmode_label"), value=sm_value, inline=True)
                if reason:
                    log.add_field(name=i18n.t(ctx.author.id, "generic.reason"), value=reason, inline=True)
                log.add_field(name=i18n.t(ctx.author.id, "generic.moderator"), value=str(ctx.author), inline=True)
                await self._log(ctx.guild, log)
        except Exception:
            pass

    @commands.hybrid_command(name="warn", description="Warn a member with a reason")
    @app_commands.describe(member="Member to warn", reason="Reason for the warning", evidence="Optional attachment evidence")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx, member: discord.Member, reason: str, evidence: discord.Attachment | None = None):
        await self._issue_warning(ctx, member, reason, evidence)

    

    @commands.hybrid_group(name="warnings", description="View warnings", invoke_without_command=True)
    @app_commands.describe(user="User to view warnings for")
    @commands.has_permissions(moderate_members=True)
    async def warnings(self, ctx, user: discord.Member | None = None):
        target = user or ctx.author
        db = self._get_db()
        cursor = db.warnings.find({"guild_id": ctx.guild.id, "user_id": target.id}).sort("created_at", -1)
        items = list(cursor)
        color = discord.Color.from_str(config.config_data.colors.embeds)
        embed = discord.Embed(
            title=f"{config.config_data.emojis.moderation} " + i18n.t(ctx.author.id, "moderation.warnings_for_title", user=str(target)),
            color=color
        )
        if not items:
            embed.description = i18n.t(ctx.author.id, "moderation.warnings_none")
            await ctx.send(embed=embed)
            return
        lines = []
        for idx, w in enumerate(items[:10], start=1):
            ts = int(w["created_at"].timestamp()) if isinstance(w.get("created_at"), datetime.datetime) else int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            mod = ctx.guild.get_member(w.get("moderator_id"))
            mod_name = mod.mention if isinstance(mod, discord.Member) else str(w.get("moderator_id"))
            reason = w.get("reason", "")
            if len(reason) > 128:
                reason = reason[:125] + "..."
            lines.append(f"{config.config_data.emojis.right} `#{w.get('case_id')}` • <t:{ts}:R> • {i18n.t(ctx.author.id, 'generic.moderator')}: {mod_name}\n{i18n.t(ctx.author.id, 'generic.reason')}: {reason}")
        embed.description = "\n\n".join(lines)
        total = len(items)
        embed.add_field(name=i18n.t(ctx.author.id, "moderation.total_warnings"), value=str(total), inline=True)
        embed.set_footer(text=i18n.t(ctx.author.id, "generic.requested_by", name=str(ctx.author)))
        await ctx.send(embed=embed)

    @warnings.command(name="case", description="View a specific warning case")
    @app_commands.describe(case_id="Case number to view")
    @commands.has_permissions(moderate_members=True)
    async def warnings_case(self, ctx, case_id: int):
        db = self._get_db()
        doc = db.warnings.find_one({"guild_id": ctx.guild.id, "case_id": int(case_id)})
        color = discord.Color.from_str(config.config_data.colors.embeds)
        if not doc:
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.warnings_case_not_found"),
                color=color
            )
            await ctx.send(embed=embed)
            return
        user = ctx.guild.get_member(doc.get("user_id"))
        mod = ctx.guild.get_member(doc.get("moderator_id"))
        when = doc.get("created_at")
        ts = int(when.timestamp()) if isinstance(when, datetime.datetime) else int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        embed = discord.Embed(
            title=f"{config.config_data.emojis.moderation} " + i18n.t(ctx.author.id, "moderation.warnings_case_title", case=str(doc.get("case_id"))),
            color=color
        )
        embed.add_field(name=i18n.t(ctx.author.id, "generic.user"), value=f"{user.mention if isinstance(user, discord.Member) else doc.get('user_id')}", inline=True)
        embed.add_field(name=i18n.t(ctx.author.id, "generic.moderator"), value=f"{mod.mention if isinstance(mod, discord.Member) else doc.get('moderator_id')}", inline=True)
        embed.add_field(name=i18n.t(ctx.author.id, "generic.when"), value=f"<t:{ts}:R>", inline=True)
        embed.add_field(name=i18n.t(ctx.author.id, "generic.reason"), value=doc.get("reason", ""), inline=False)
        att = doc.get("attachment")
        if isinstance(att, dict) and att.get("url"):
            embed.add_field(name=i18n.t(ctx.author.id, "generic.attachment"), value=f"[\u200b]({att['url']})", inline=False)
        embed.set_footer(text=f"#{doc.get('case_id')}")
        await ctx.send(embed=embed)

    @warnings.command(name="add", description="Add a warning to a member")
    @app_commands.describe(member="Member to warn", reason="Reason for the warning", evidence="Optional attachment evidence")
    @commands.has_permissions(moderate_members=True)
    async def warnings_add(self, ctx, member: discord.Member, reason: str, evidence: discord.Attachment | None = None):
        await self._issue_warning(ctx, member, reason, evidence)

    @warnings.command(name="list", description="List warnings for a user")
    @app_commands.describe(user="User to list warnings for")
    @commands.has_permissions(moderate_members=True)
    async def warnings_list(self, ctx, user: discord.Member | None = None):
        await self.warnings(ctx, user)

    @warnings.command(name="remove", description="Remove a warning by case ID")
    @app_commands.describe(case_id="Case number to remove")
    @commands.has_permissions(moderate_members=True)
    async def warnings_remove(self, ctx, case_id: int):
        db = self._get_db()
        res = db.warnings.find_one_and_delete({"guild_id": ctx.guild.id, "case_id": int(case_id)})
        color = discord.Color.from_str(config.config_data.colors.embeds)
        if not res:
            embed = discord.Embed(
                title=f"{config.config_data.emojis.warning} " + i18n.t(ctx.author.id, "moderation.warnings_case_not_found"),
                color=color
            )
            await ctx.send(embed=embed)
            return
        embed = discord.Embed(
            title=f"{config.config_data.emojis.moderation} " + i18n.t(ctx.author.id, "moderation.warnings_removed_title"),
            description=i18n.t(ctx.author.id, "moderation.warnings_removed_description", case=str(case_id)),
            color=color
        )
        await ctx.send(embed=embed)
        try:
            settings = self._get_settings(ctx.guild.id)
            if settings.get("log_warnings"):
                log = discord.Embed(
                    title=i18n.t(ctx.author.id, "moderation.warnings_removed_title"),
                    description=i18n.t(ctx.author.id, "moderation.warnings_removed_description", case=str(case_id)),
                    color=color
                )
                log.add_field(name=i18n.t(ctx.author.id, "generic.moderator"), value=str(ctx.author), inline=True)
                await self._log(ctx.guild, log)
        except Exception:
            pass

    @warnings.command(name="clear", description="Clear all warnings for a user")
    @app_commands.describe(user="User to clear warnings for")
    @commands.has_permissions(moderate_members=True)
    async def warnings_clear(self, ctx, user: discord.Member):
        db = self._get_db()
        res = db.warnings.delete_many({"guild_id": ctx.guild.id, "user_id": user.id})
        color = discord.Color.from_str(config.config_data.colors.embeds)
        embed = discord.Embed(
            title=f"{config.config_data.emojis.moderation} " + i18n.t(ctx.author.id, "moderation.warnings_cleared_title"),
            description=i18n.t(ctx.author.id, "moderation.warnings_cleared_description", user=str(user), count=str(res.deleted_count)),
            color=color
        )
        await ctx.send(embed=embed)
        try:
            settings = self._get_settings(ctx.guild.id)
            if settings.get("log_warnings"):
                log = discord.Embed(
                    title=i18n.t(ctx.author.id, "moderation.warnings_cleared_title"),
                    description=i18n.t(ctx.author.id, "moderation.warnings_cleared_description", user=str(user), count=str(res.deleted_count)),
                    color=color
                )
                log.add_field(name=i18n.t(ctx.author.id, "generic.moderator"), value=str(ctx.author), inline=True)
                await self._log(ctx.guild, log)
        except Exception:
            pass

    @warnings.command(name="edit", description="Edit a warning's reason by case ID")
    @app_commands.describe(case_id="Case number", reason="New reason")
    @commands.has_permissions(moderate_members=True)
    async def warnings_edit(self, ctx, case_id: int, *, reason: str):
        db = self._get_db()
        if not reason or not reason.strip():
            await ctx.send(i18n.t(ctx.author.id, "errors.invalid_duration_format"))
            return
        res = db.warnings.find_one_and_update(
            {"guild_id": ctx.guild.id, "case_id": int(case_id)},
            {"$set": {"reason": reason}},
            return_document=ReturnDocument.AFTER
        )
        color = discord.Color.from_str(config.config_data.colors.embeds)
        if not res:
            embed = discord.Embed(
                title=f"{config.config_data.emojis.warning} " + i18n.t(ctx.author.id, "moderation.warnings_case_not_found"),
                color=color
            )
            await ctx.send(embed=embed)
            return
        embed = discord.Embed(
            title=f"{config.config_data.emojis.moderation} " + i18n.t(ctx.author.id, "moderation.warnings_edited_title"),
            description=i18n.t(ctx.author.id, "moderation.warnings_edited_description", case=str(case_id)),
            color=color
        )
        embed.add_field(name=i18n.t(ctx.author.id, "generic.reason"), value=reason, inline=False)
        await ctx.send(embed=embed)
        try:
            settings = self._get_settings(ctx.guild.id)
            if settings.get("log_warnings"):
                log = discord.Embed(
                    title=i18n.t(ctx.author.id, "moderation.warnings_edited_title"),
                    description=i18n.t(ctx.author.id, "moderation.warnings_edited_description", case=str(case_id)),
                    color=color
                )
                log.add_field(name=i18n.t(ctx.author.id, "generic.reason"), value=reason, inline=False)
                log.add_field(name=i18n.t(ctx.author.id, "generic.moderator"), value=str(ctx.author), inline=True)
                await self._log(ctx.guild, log)
        except Exception:
            pass

    @commands.hybrid_group(name="moderation", description="Moderation setup and settings", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def moderation(self, ctx):
        settings = self._get_settings(ctx.guild.id)
        color = discord.Color.from_str(config.config_data.colors.embeds)
        emojis = config.config_data.emojis
        ch = self._get_logs_channel(ctx.guild)
        embed = discord.Embed(
            title=f"{emojis.menu} " + i18n.t(ctx.author.id, "moderation.settings_title"),
            color=color
        )
        embed.add_field(
            name=i18n.t(ctx.author.id, "moderation.logs_channel"),
            value=ch.mention if ch else i18n.t(ctx.author.id, "moderation.not_configured"),
            inline=False
        )
        embed.add_field(name=i18n.t(ctx.author.id, "moderation.log_warnings"), value="On" if settings.get("log_warnings") else "Off", inline=True)
        embed.add_field(name=i18n.t(ctx.author.id, "moderation.log_locks"), value="On" if settings.get("log_locks") else "Off", inline=True)
        embed.add_field(name=i18n.t(ctx.author.id, "moderation.log_slowmode"), value="On" if settings.get("log_slowmode") else "Off", inline=True)
        await ctx.send(embed=embed)

    @moderation.command(name="setup", description="Configure moderation logging and options")
    @app_commands.describe(
        logs_channel="Channel to send moderation logs to",
        create_channel="Create a logs channel if not provided",
        name="Name for the logs channel",
        category="Category to place the new channel in",
        log_warnings="Log warning actions",
        log_locks="Log locks/unlocks",
        log_slowmode="Log slowmode changes"
    )
    @commands.has_permissions(manage_guild=True)
    async def moderation_setup(
        self,
        ctx,
        logs_channel: discord.TextChannel | None = None,
        create_channel: bool = False,
        name: str = "mod-logs",
        category: discord.CategoryChannel | None = None,
        log_warnings: bool | None = None,
        log_locks: bool | None = None,
        log_slowmode: bool | None = None,
    ):
        color = discord.Color.from_str(config.config_data.colors.embeds)
        target_channel = logs_channel
        if target_channel is None and create_channel:
            perms = ctx.guild.me.guild_permissions if isinstance(ctx.guild.me, discord.Member) else None
            if not perms or not perms.manage_channels:
                embed = discord.Embed(
                    title=i18n.t(ctx.author.id, "moderation.bot_missing_permissions"),
                    color=color
                )
                embed.add_field(name=i18n.t(ctx.author.id, "generic.required"), value="`Manage Channels`", inline=False)
                await ctx.send(embed=embed)
                return
            try:
                overwrites = {ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)}
                target_channel = await ctx.guild.create_text_channel(name=name, category=category, overwrites=overwrites, reason="Moderation setup")
            except Exception:
                target_channel = None
        updates = {}
        if target_channel is not None:
            updates["logs_channel_id"] = int(target_channel.id)
        if log_warnings is not None:
            updates["log_warnings"] = bool(log_warnings)
        if log_locks is not None:
            updates["log_locks"] = bool(log_locks)
        if log_slowmode is not None:
            updates["log_slowmode"] = bool(log_slowmode)
        if updates:
            self._save_settings(ctx.guild.id, **updates)
        settings = self._get_settings(ctx.guild.id)
        ch = self._get_logs_channel(ctx.guild)
        embed = discord.Embed(
            title=f"{config.config_data.emojis.tick} " + i18n.t(ctx.author.id, "moderation.setup_success_title"),
            description=i18n.t(ctx.author.id, "moderation.setup_success_desc", channel=(ch.mention if ch else i18n.t(ctx.author.id, "moderation.not_configured"))),
            color=color
        )
        embed.add_field(name=i18n.t(ctx.author.id, "moderation.log_warnings"), value="On" if settings.get("log_warnings") else "Off", inline=True)
        embed.add_field(name=i18n.t(ctx.author.id, "moderation.log_locks"), value="On" if settings.get("log_locks") else "Off", inline=True)
        embed.add_field(name=i18n.t(ctx.author.id, "moderation.log_slowmode"), value="On" if settings.get("log_slowmode") else "Off", inline=True)
        await ctx.send(embed=embed)

    @moderation.command(name="testlog", description="Send a test message to the logs channel")
    @commands.has_permissions(manage_guild=True)
    async def moderation_testlog(self, ctx):
        ch = self._get_logs_channel(ctx.guild)
        color = discord.Color.from_str(config.config_data.colors.embeds)
        if ch is None:
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.no_logs_channel"),
                color=color
            )
            await ctx.send(embed=embed)
            return
        test = discord.Embed(
            title=f"{config.config_data.emojis.info} " + i18n.t(ctx.author.id, "moderation.test_log_title"),
            description=i18n.t(ctx.author.id, "moderation.test_log_description"),
            color=color
        )
        await ch.send(embed=test)
        done = discord.Embed(
            title=f"{config.config_data.emojis.tick} " + i18n.t(ctx.author.id, "moderation.settings_title"),
            description=i18n.t(ctx.author.id, "moderation.test_log_sent", channel=ch.mention),
            color=color
        )
        await ctx.send(embed=done)

    @moderation.error
    async def moderation_error(self, ctx, error):
        from discord.ext.commands import MissingPermissions, BotMissingPermissions
        required = ["Manage Server"]
        if isinstance(error, MissingPermissions):
            missing = [p.replace("_", " ").title() for p in getattr(error, "missing_permissions", [])]
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.missing_permissions"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.required"), value=", ".join(f"`{p}`" for p in required), inline=False)
            embed.add_field(name=i18n.t(ctx.author.id, "generic.missing"), value=", ".join(f"`{p}`" for p in missing) or "None", inline=False)
            await ctx.send(embed=embed)
            return
        if isinstance(error, BotMissingPermissions):
            missing = [p.replace("_", " ").title() for p in getattr(error, "missing_permissions", [])]
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.bot_missing_permissions"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.required"), value=", ".join(f"`{p}`" for p in missing) or "None", inline=False)
            await ctx.send(embed=embed)
            return
        raise error

    @lock.error
    async def lock_error(self, ctx, error):
        from discord.ext.commands import MissingPermissions, BotMissingPermissions
        required = ["Manage Channels", "Manage Roles"]
        if isinstance(error, MissingPermissions):
            missing = [p.replace("_", " ").title() for p in getattr(error, "missing_permissions", [])]
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.missing_permissions"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.required"), value=", ".join(f"`{p}`" for p in required), inline=False)
            embed.add_field(name=i18n.t(ctx.author.id, "generic.missing"), value=", ".join(f"`{p}`" for p in missing) or "None", inline=False)
            await ctx.send(embed=embed)
            return
        if isinstance(error, BotMissingPermissions):
            missing = [p.replace("_", " ").title() for p in getattr(error, "missing_permissions", [])]
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.bot_missing_permissions"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.required"), value=", ".join(f"`{p}`" for p in required), inline=False)
            embed.add_field(name=i18n.t(ctx.author.id, "generic.missing"), value=", ".join(f"`{p}`" for p in missing) or "None", inline=False)
            await ctx.send(embed=embed)
            return
        raise error

    @unlock.error
    async def unlock_error(self, ctx, error):
        from discord.ext.commands import MissingPermissions, BotMissingPermissions
        required = ["Manage Channels", "Manage Roles"]
        if isinstance(error, MissingPermissions):
            missing = [p.replace("_", " ").title() for p in getattr(error, "missing_permissions", [])]
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.missing_permissions"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.required"), value=", ".join(f"`{p}`" for p in required), inline=False)
            embed.add_field(name=i18n.t(ctx.author.id, "generic.missing"), value=", ".join(f"`{p}`" for p in missing) or "None", inline=False)
            await ctx.send(embed=embed)
            return
        if isinstance(error, BotMissingPermissions):
            missing = [p.replace("_", " ").title() for p in getattr(error, "missing_permissions", [])]
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.bot_missing_permissions"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.required"), value=", ".join(f"`{p}`" for p in required), inline=False)
            embed.add_field(name=i18n.t(ctx.author.id, "generic.missing"), value=", ".join(f"`{p}`" for p in missing) or "None", inline=False)
            await ctx.send(embed=embed)
            return
        raise error

    @slowmode.error
    async def slowmode_error(self, ctx, error):
        from discord.ext.commands import MissingPermissions, BotMissingPermissions
        required = ["Manage Channels"]
        if isinstance(error, MissingPermissions):
            missing = [p.replace("_", " ").title() for p in getattr(error, "missing_permissions", [])]
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.missing_permissions"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.required"), value=", ".join(f"`{p}`" for p in required), inline=False)
            embed.add_field(name=i18n.t(ctx.author.id, "generic.missing"), value=", ".join(f"`{p}`" for p in missing) or "None", inline=False)
            await ctx.send(embed=embed)
            return
        if isinstance(error, BotMissingPermissions):
            missing = [p.replace("_", " ").title() for p in getattr(error, "missing_permissions", [])]
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.bot_missing_permissions"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.required"), value=", ".join(f"`{p}`" for p in required), inline=False)
            embed.add_field(name=i18n.t(ctx.author.id, "generic.missing"), value=", ".join(f"`{p}`" for p in missing) or "None", inline=False)
            await ctx.send(embed=embed)
            return
        raise error

    @warn.error
    async def warn_error(self, ctx, error):
        from discord.ext.commands import MissingPermissions
        required = ["Moderate Members"]
        if isinstance(error, MissingPermissions):
            missing = [p.replace("_", " ").title() for p in getattr(error, "missing_permissions", [])]
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.missing_permissions"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.required"), value=", ".join(f"`{p}`" for p in required), inline=False)
            embed.add_field(name=i18n.t(ctx.author.id, "generic.missing"), value=", ".join(f"`{p}`" for p in missing) or "None", inline=False)
            await ctx.send(embed=embed)
            return
        raise error

    @warnings.error
    async def warnings_error(self, ctx, error):
        from discord.ext.commands import MissingPermissions
        required = ["Moderate Members"]
        if isinstance(error, MissingPermissions):
            missing = [p.replace("_", " ").title() for p in getattr(error, "missing_permissions", [])]
            embed = discord.Embed(
                title=i18n.t(ctx.author.id, "moderation.missing_permissions"),
                color=discord.Color.from_str(config.config_data.colors.embeds)
            )
            embed.add_field(name=i18n.t(ctx.author.id, "generic.required"), value=", ".join(f"`{p}`" for p in required), inline=False)
            embed.add_field(name=i18n.t(ctx.author.id, "generic.missing"), value=", ".join(f"`{p}`" for p in missing) or "None", inline=False)
            await ctx.send(embed=embed)
            return
        raise error

    @tasks.loop(minutes=1)
    async def check_expired_locks(self):
        db = self._get_db()
        coll = db.channel_locks
        now = datetime.datetime.now(datetime.timezone.utc)
        for doc in coll.find({"active": True, "expires_at": {"$ne": None, "$lte": now}}):
            guild = self.client.get_guild(doc["guild_id"])
            if not guild:
                continue
            channel = guild.get_channel(doc["channel_id"])
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                if doc.get("previous_overwrites"):
                    for entry in doc["previous_overwrites"]:
                        role = guild.get_role(entry["role_id"])
                        if role is None:
                            continue
                        await channel.set_permissions(role, send_messages=entry.get("prev", None), reason="Auto unlock: duration expired")
                else:
                    default_role = guild.default_role
                    await channel.set_permissions(default_role, send_messages=doc.get("previous_send_messages", None), reason="Auto unlock: duration expired")
                coll.update_one({"_id": doc["_id"]}, {"$set": {"active": False, "released_at": now, "auto": True}})
                coll.insert_one({
                    "guild_id": guild.id,
                    "channel_id": channel.id,
                    "moderator_id": None,
                    "action": "unlock",
                    "reason": "Auto unlock",
                    "created_at": now,
                })
                try:
                    note = discord.Embed(
                        title=i18n.t(None, "moderation.channel_unlocked"),
                        description=i18n.t(None, "moderation.auto_unlocked_note"),
                        color=discord.Color.from_str(config.config_data.colors.embeds)
                    )
                    await channel.send(embed=note)
                except Exception:
                    pass
                try:
                    settings = self._get_settings(guild.id)
                    if settings.get("log_locks"):
                        log = discord.Embed(
                            title=i18n.t(None, "moderation.channel_unlocked"),
                            color=discord.Color.from_str(config.config_data.colors.embeds)
                        )
                        log.add_field(name=i18n.t(None, "generic.channel"), value=channel.mention, inline=True)
                        log.add_field(name=i18n.t(None, "generic.reason"), value=i18n.t(None, "moderation.auto_unlocked_note"), inline=True)
                        await self._log(guild, log)
                except Exception:
                    pass
            except Exception:
                continue

    def cog_unload(self):
        if self.check_expired_locks.is_running():
            self.check_expired_locks.cancel()

async def setup(client):
    await client.add_cog(Moderation(client))
