import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import re
import database
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
            except Exception:
                continue

    def cog_unload(self):
        if self.check_expired_locks.is_running():
            self.check_expired_locks.cancel()

async def setup(client):
    await client.add_cog(Moderation(client))
