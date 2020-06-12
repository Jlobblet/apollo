import asyncio
import re

import discord
from discord.ext import commands
from discord.ext.commands import Bot, Context

from models import db_session, RoleMessage

link_regex = re.compile(
    r"^https?://(?:(ptb|canary)\.)?discordapp\.com/channels/"
    r"(?:([0-9]{15,21})|(@me))"
    r"/(?P<channel_id>[0-9]{15,21})/(?P<message_id>[0-9]{15,21})/?$"
)

header = "__Role Reaction Menu__"

link_stage = "Please reply with a link to the menu message."
ping_stage = "Please ping role role(s) you want to add to the menu."
emoji_stage = "Please react with the emoji (in order) you want for each role."
completion_message = "Please say `complete` to finish setup."

link_message = "Message start: {message}\nChannel name: {channel}"
role_emoji_line = "{role}: {emoji}"


class Roles(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.messages = db_session.query(RoleMessage).with_entities(
            RoleMessage.message_id
        )

    @commands.command()
    async def add_role_menu(self, ctx: Context):
        if not ctx.author.bot:
            embed = discord.Embed(title=header, description=link_stage)
            master_message = await ctx.send(embed=embed)

            def check(message):
                return (
                    message.author == ctx.author
                    and message.channel == ctx.channel
                    and link_regex.match(message.content)
                )

            message = await self.bot.wait_for("message", check=check)
            match = link_regex.match(message.content)
            channel_id = int(match.group("channel_id"))
            channel = self.bot.get_channel(channel_id)
            message_id = int(match.group("message_id"))
            message = await channel.fetch_message(message_id)
            message_text = message.content[: max(len(message.content), 20)]
            guild_id = channel.guild.id

            embed = discord.Embed(
                title=header,
                description="\n".join(
                    (
                        link_message.format(
                            message=message_text, channel=channel.mention
                        ),
                        ping_stage,
                    )
                ),
            )
            await master_message.edit(embed=embed)

            def check(message):
                return (
                    message.author == ctx.author
                    and message.channel == ctx.channel
                    and len(message.role_mentions) >= 1
                )

            message = await self.bot.wait_for("message", check=check)
            role_ids = [role.id for role in message.role_mentions]
            role_mentions = [role.mention for role in message.role_mentions]

            embed = discord.Embed(
                title=header,
                description="\n".join(
                    [
                        link_message.format(
                            message=message_text, channel=channel.mention
                        ),
                    ]
                    + [
                        role_emoji_line.format(role=role.mention, emoji=" ")
                        for role in message.role_mentions
                    ]
                    + [emoji_stage]
                ),
            )
            await master_message.edit(embed=embed)

            def check(reaction, user):
                return (
                    reaction.message.id == master_message.id
                    and user.id == ctx.author.id
                )

            not_completed = True
            emoji_names = []

            while not_completed:
                done, pending = await asyncio.wait(
                    [
                        self.bot.wait_for("reaction_add"),
                        self.bot.wait_for("reaction_remove"),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                reaction, user = done.pop().result()
                print("before")
                emoji_names = reaction.message.reactions
                print("after")
                emoji_names += [" "] * (len(role_ids) - len(emoji_names))
                embed = discord.Embed(
                    title=header,
                    description="\n".join(
                        [
                            link_message.format(
                                message=message_text, channel=channel.mention
                            ),
                        ]
                        + [
                            role_emoji_line.format(
                                role=role_mentions[i], emoji=emoji_names[i]
                            )
                            for i, _ in enumerate(role_mentions)
                        ]
                        + [emoji_stage]
                    ),
                )
                await master_message.edit(embed=embed)
                for future in pending:
                    future.cancel()

            newRoleMessage = RoleMessage(
                message_id=message_id,
                channel_id=channel_id,
                guild_id=guild_id,
                reaction_name=reaction_name,
                role_id=role_id,
            )
            db_session.add(newRoleMessage)
            db_session.commit()
            db_session.flush()
            self.messages.append(message_id)
            await ctx.send("all sorted fam")

    @commands.Cog.listener(name="on_raw_reaction_add")
    async def on_reaction_add(self, payload):
        print(f"payload: {payload}")
        if payload.message_id in self.messages:
            message_id = payload.message_id
            channel_id = payload.channel_id
            guild_id = payload.guild_id
            reaction_name = str(payload.emoji)
            member = payload.member

            role_message = (
                db_session.query(RoleMessage)
                .filter(
                    RoleMessage.message_id == message_id
                    and RoleMessage.channel_id == channel_id
                    and RoleMessage.guild_id == guild_id
                    and RoleMessage.reaction_name == reaction_name
                )
                .first()
            )

            if role_message:
                role = member.guild.get_role(role_message.role_id)
                await member.add_roles(role)

    @commands.Cog.listener(name="on_raw_reaction_remove")
    async def on_reaction_remove(self, payload):
        print(f"payload: {payload}")
        message_id = payload.message_id
        channel_id = payload.channel_id
        guild_id = payload.guild_id
        reaction_name = str(payload.emoji)
        member = self.bot.get_guild(guild_id).get_member(payload.user_id)

        role_message = (
            db_session.query(RoleMessage)
            .filter(
                RoleMessage.message_id == message_id
                and RoleMessage.channel_id == channel_id
                and RoleMessage.guild_id == guild_id
                and RoleMessage.reaction_name == reaction_name
            )
            .first()
        )

        if role_message:
            role = member.guild.get_role(role_message.role_id)
            await member.remove_roles(role)


def setup(bot: Bot):
    bot.add_cog(Roles(bot))
