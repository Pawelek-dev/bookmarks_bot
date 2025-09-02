import discord
from discord.ext import commands
from discord import app_commands
import json
from typing import Optional
from database.manager import DatabaseManager
from ui.components import BookmarksView, BookmarkDetailView

class ViewBookmarkButton(discord.ui.View):
    def __init__(self, bookmark_id: int, db_manager: DatabaseManager, bookmarks_view: BookmarksView):
        super().__init__(timeout=300)
        self.bookmark_id = bookmark_id
        self.db_manager = db_manager
        self.bookmarks_view = bookmarks_view
    
    @discord.ui.button(label="Wyświetl zakładkę", style=discord.ButtonStyle.gray, emoji="📖")
    async def view_bookmark(self, interaction: discord.Interaction, button: discord.ui.Button):
        bookmark = self.db_manager.get_bookmark_by_id(self.bookmark_id, interaction.user.id)

        if not bookmark:
            await interaction.response.send_message(
                "Nie znaleziono zakładki o podanym ID lub nie masz do niej dostępu.",
                ephemeral=True
            )
            return

        embed, additional_embeds, link_data = self.bookmarks_view.create_bookmark_detail_embed(bookmark)
        all_embeds = [embed] + additional_embeds

        view = BookmarkDetailView(self.db_manager, self.bookmark_id, link_data)

        await interaction.response.send_message(
            embeds=all_embeds,
            view=view,
            ephemeral=True
        )

class BookmarksCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_manager = DatabaseManager()
        self.bookmarks_view = BookmarksView(self.db_manager)
        self.ctx_menu = app_commands.ContextMenu(
            name="Save Message",
            callback=self.save_message_context_menu,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def save_message_context_menu(self, interaction: discord.Interaction, message: discord.Message):
        embed_data = None
        if message.embeds:
            embed_list = []
            for embed in message.embeds:
                embed_dict = embed.to_dict()
                embed_list.append(embed_dict)
            embed_data = json.dumps(embed_list)

        components_data = None
        message_flags = getattr(message, 'flags', 0)
        if hasattr(message_flags, 'value'):
            message_flags = message_flags.value
        elif not isinstance(message_flags, int):
            message_flags = int(message_flags) if message_flags else 0
        
        if hasattr(message, 'components') and message.components:
            try:
                components_data = json.dumps([component.to_dict() for component in message.components])
            except AttributeError:
                components_data = json.dumps(message.components)
        
        guild_id = message.guild.id if message.guild else 0

        bookmark_id = self.db_manager.save_bookmark(
            interaction.user.id, 
            message, 
            embed_data,
            components_data,
            message_flags,
            guild_id
        )

        embed = discord.Embed(
            title="📌 Wiadomość zapisana!",
            description=f"Zapisano wiadomość od {message.author.mention}",
            color=0x00FF00
        )
        embed.add_field(name="ID zakładki", value=bookmark_id)

        if message_flags & 32768:
            embed.add_field(
                name="🔧 Typ wiadomości",
                value="Interaktywna (Components v2)",
                inline=True
            )

        if message.attachments:
            attachment_count = len(message.attachments)
            embed.add_field(
                name="📎 Załączniki",
                value=f"Zapisano {attachment_count} {'załącznik' if attachment_count == 1 else 'załączniki' if 1 < attachment_count < 5 else 'załączników'}"
            )

        embed.set_footer(text=f"Użyj /bookmarks aby zobaczyć swoje zakładki")
        view = ViewBookmarkButton(bookmark_id, self.db_manager, self.bookmarks_view)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="bookmarks", description="Wyświetl swoje zapisane wiadomości")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(page="Numer strony (domyślnie 1)")
    async def bookmarks_command(self, interaction: discord.Interaction, page: Optional[int] = 1):
        if page < 1:
            page = 1

        embed, view, bookmarks, total, max_pages = await self.bookmarks_view.create_bookmarks_page(interaction.user.id, page)

        if not bookmarks:
            empty_embed = discord.Embed(
                title="📚 Twoje zakładki",
                description="Nie masz jeszcze zapisanych wiadomości.",
                color=0x3498db
            )
            await interaction.response.send_message(embed=empty_embed, ephemeral=True)
            return

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="bookmark", description="Wyświetl szczegóły zapisanej wiadomości")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(id="ID zakładki")
    async def bookmark_command(self, interaction: discord.Interaction, id: int):
        bookmark = self.db_manager.get_bookmark_by_id(id, interaction.user.id)

        if not bookmark:
            await interaction.response.send_message(
                "Nie znaleziono zakładki o podanym ID lub nie masz do niej dostępu.",
                ephemeral=True
            )
            return

        embed, additional_embeds, link_data = self.bookmarks_view.create_bookmark_detail_embed(bookmark)
        all_embeds = [embed] + additional_embeds
        view = BookmarkDetailView(self.db_manager, id, link_data)
        await interaction.response.send_message(
            embeds=all_embeds,
            view=view,
            ephemeral=True
        )

    @app_commands.command(name="delete_bookmark", description="Usuń zakładkę")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(id="ID zakładki do usunięcia")
    async def delete_bookmark_command(self, interaction: discord.Interaction, id: int):
        success, message = self.db_manager.delete_bookmark(id, interaction.user.id)

        if success:
            embed = discord.Embed(
                title="🗑️ Zakładka usunięta",
                description=message,
                color=0x00FF00
            )
        else:
            embed = discord.Embed(
                title="❌ Błąd",
                description=message,
                color=0xFF0000
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(BookmarksCog(bot))
