import discord
import datetime
import json
from typing import List, Tuple, Optional, Dict, Any, Union
from database.manager import DatabaseManager

class BookmarksView:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def is_gif_url(self, url: str) -> bool:
        if not url:
            return False

        if url.lower().endswith('.gif'):
            return True

        gif_domains = [
            'tenor.com',
            'giphy.com',
            'gfycat.com',
            'imgur.com',
            'media.discordapp.net',
            'cdn.discordapp.com'
        ]

        for domain in gif_domains:
            if domain in url.lower():
                return True

        return False

    async def create_bookmarks_page(self, user_id: int, page: int = 1) -> Tuple[Optional[discord.Embed], Optional[discord.ui.View], List, int, int]:
        if page < 1:
            page = 1

        bookmarks, total = self.db_manager.get_user_bookmarks(user_id, page)
        max_pages = (total + 9) // 10

        if not bookmarks:
            return None, None, bookmarks, total, max_pages

        embed = discord.Embed(
            title="📚 Twoje zakładki",
            description=f"Strona {page}/{max_pages} (łącznie {total} zakładek)",
            color=0x3498db
        )

        bookmark_options = []

        for bookmark in bookmarks:
            bookmark_id = bookmark[0]
            message_content = bookmark[5] or "(brak treści)"
            author_name = bookmark[7]
            timestamp = datetime.datetime.fromisoformat(bookmark[9]).strftime("%d.%m.%Y %H:%M")
            attachments_data = bookmark[11]

            attachment_info = ""
            if attachments_data:
                try:
                    attachments = json.loads(attachments_data)
                    image_count = sum(1 for att in attachments if att.get('is_image'))
                    file_count = len(attachments) - image_count

                    if image_count > 0:
                        attachment_info += f" 🖼️ {image_count}"
                    if file_count > 0:
                        attachment_info += f" 📎 {file_count}"
                except:
                    pass

            short_content = message_content
            if len(message_content) > 100:
                short_content = message_content[:97] + "..."

            field_name = f"ID: {bookmark_id} | {author_name} | {timestamp}"
            if attachment_info:
                field_name += f" | {attachment_info}"

            embed.add_field(
                name=field_name,
                value=short_content,
                inline=False
            )

            option_label = message_content
            if len(option_label) > 80:
                option_label = option_label[:77] + "..."
            elif option_label == "":
                option_label = "(brak treści)"

            bookmark_options.append(
                discord.SelectOption(
                    label=f"ID: {bookmark_id}",
                    description=option_label,
                    value=str(bookmark_id)
                )
            )

        view = BookmarksPageView(self.db_manager, bookmark_options, page, max_pages)
        return embed, view, bookmarks, total, max_pages

    def _extract_components_v2_content(self, components: List[discord.Component]) -> Tuple[str, List[str], Dict[str, Any]]:
        content_parts = []
        image_urls = []
        metadata = {
            'has_buttons': False,
            'has_select_menus': False,
            'has_text_displays': False,
            'has_media_galleries': False,
            'has_files': False,
            'component_types': [],
            'layout_structure': []
        }

        def process_component(component: discord.Component, depth: int = 0) -> None:
            indent = "  " * depth
            comp_type = type(component).__name__
            metadata['component_types'].append(comp_type)

            if isinstance(component, discord.ui.Button):
                metadata['has_buttons'] = True
                metadata['layout_structure'].append(f"{indent}🔘 Button: {component.label or 'No label'}")
                if hasattr(component, 'url') and component.url:
                    metadata['layout_structure'].append(f"{indent}  🔗 URL: {component.url}")

            elif isinstance(component, discord.ui.Select):
                metadata['has_select_menus'] = True
                metadata['layout_structure'].append(f"{indent}📋 Select Menu: {component.placeholder or 'No placeholder'}")
                if hasattr(component, 'options'):
                    for i, option in enumerate(component.options[:3]):
                        metadata['layout_structure'].append(f"{indent}  • {option.label}")
                    if len(component.options) > 3:
                        metadata['layout_structure'].append(f"{indent}  ... i {len(component.options) - 3} więcej")

            elif hasattr(discord.ui, 'TextDisplay') and isinstance(component, discord.ui.TextDisplay):
                metadata['has_text_displays'] = True
                text_content = getattr(component, 'content', '') or getattr(component, 'text', '')
                if text_content:
                    content_parts.append(text_content)
                    metadata['layout_structure'].append(f"{indent}📝 Text Display: {text_content[:50]}{'...' if len(text_content) > 50 else ''}")

            elif hasattr(discord.ui, 'MediaGallery') and isinstance(component, discord.ui.MediaGallery):
                metadata['has_media_galleries'] = True
                metadata['layout_structure'].append(f"{indent}🖼️ Media Gallery")
                if hasattr(component, 'items'):
                    for item in component.items:
                        if hasattr(item, 'url'):
                            image_urls.append(item.url)
                            metadata['layout_structure'].append(f"{indent}  📎 Media: {item.url}")

            elif hasattr(discord.ui, 'File') and isinstance(component, discord.ui.File):
                metadata['has_files'] = True
                metadata['layout_structure'].append(f"{indent}📁 File Component")
                if hasattr(component, 'url'):
                    metadata['layout_structure'].append(f"{indent}  📎 File: {component.url}")

            elif hasattr(discord.ui, 'Container') and isinstance(component, discord.ui.Container):
                metadata['layout_structure'].append(f"{indent}📦 Container")
                if hasattr(component, 'children'):
                    for child in component.children:
                        process_component(child, depth + 1)

            elif hasattr(discord.ui, 'Section') and isinstance(component, discord.ui.Section):
                metadata['layout_structure'].append(f"{indent}📑 Section")
                if hasattr(component, 'children'):
                    for child in component.children:
                        process_component(child, depth + 1)

            elif isinstance(component, discord.ActionRow):
                metadata['layout_structure'].append(f"{indent}📏 Action Row")
                for child in component.children:
                    process_component(child, depth + 1)

            else:
                metadata['layout_structure'].append(f"{indent}❓ Unknown Component: {comp_type}")

        for component in components:
            process_component(component)

        return '\n'.join(content_parts), image_urls, metadata

    def create_bookmark_detail_embed(self, bookmark: Tuple) -> Tuple[discord.Embed, List[discord.Embed], List[str]]:
        bookmark_id = bookmark[0]
        message_id = bookmark[2]
        channel_id = bookmark[3]
        guild_id = bookmark[4]
        message_content = bookmark[5]
        embed_data = bookmark[6]
        author_name = bookmark[7]
        author_avatar = bookmark[8]
        timestamp = datetime.datetime.fromisoformat(bookmark[9]).strftime("%d.%m.%Y %H:%M")
        attachments_data = bookmark[11]
        components_data = bookmark[12] if len(bookmark) > 12 else None
        message_flags = bookmark[13] if len(bookmark) > 13 else 0

        is_components_v2 = message_flags & 32768 == 32768

        final_content = message_content
        additional_embeds = []
        image_urls = []
        components_metadata = {}

        if is_components_v2 and components_data:
            try:
                if isinstance(components_data, str):
                    raw_components = json.loads(components_data)
                else:
                    raw_components = components_data

                components_content, components_images, components_metadata = self._process_raw_components_v2(raw_components)

                if components_content:
                    if final_content:
                        final_content += "\n\n" + components_content
                    else:
                        final_content = components_content

                image_urls.extend(components_images)
            except Exception as e:
                print(f"Błąd przetwarzania Components v2: {e}")
                components_content, components_images = self._extract_components_v2_content_legacy(components_data)
                if components_content:
                    if final_content:
                        final_content += "\n\n" + components_content
                    else:
                        final_content = components_content
                image_urls.extend(components_images)

        embed = discord.Embed(
            title=f"📖 Zakładka #{bookmark_id}",
            description=final_content or "*Brak treści*",
            color=0x3498db,
            timestamp=datetime.datetime.fromisoformat(bookmark[9])
        )

        if author_avatar:
            embed.set_author(name=author_name, icon_url=author_avatar)
        else:
            embed.set_author(name=author_name)

        embed.add_field(name="Oryginalny kanał", value=f"<#{channel_id}>", inline=True)
        embed.add_field(name="Link do wiadomości", value=f"[Kliknij tutaj](https://discord.com/channels/{guild_id}/{channel_id}/{message_id})", inline=True)

        if is_components_v2:
            embed.add_field(name="Typ wiadomości", value="🔧 Interaktywna (Components v2)", inline=True)

            if components_metadata:
                comp_info = []
                if components_metadata.get('has_buttons'):
                    comp_info.append("🔘 Przyciski")
                if components_metadata.get('has_select_menus'):
                    comp_info.append("📋 Menu wyboru")
                if components_metadata.get('has_text_displays'):
                    comp_info.append("📝 Wyświetlacz tekstu")
                if components_metadata.get('has_media_galleries'):
                    comp_info.append("🖼️ Galeria mediów")
                if components_metadata.get('has_files'):
                    comp_info.append("📁 Pliki")

                if comp_info:
                    embed.add_field(
                        name="🔧 Komponenty v2",
                        value="\n".join(comp_info),
                        inline=False
                    )

                if components_metadata.get('layout_structure'):
                    layout_preview = "\n".join(components_metadata['layout_structure'][:5])
                    if len(components_metadata['layout_structure']) > 5:
                        layout_preview += f"\n... i {len(components_metadata['layout_structure']) - 5} więcej"

                    embed.add_field(
                        name="📐 Struktura layoutu",
                        value=f"```\n{layout_preview}\n```",
                        inline=False
                    )

        if attachments_data:
            try:
                attachments = json.loads(attachments_data)
                attachment_image_urls = [att["url"] for att in attachments if att.get("is_image")]
                video_urls = []
                for att in attachments:
                    filename = att.get("filename", "").lower()
                    if any(filename.endswith(ext) for ext in ['.mp4', '.mov', '.webm', '.avi', '.mkv']):
                        video_urls.append(att["url"])

                image_urls.extend(attachment_image_urls)

                if attachments:
                    file_types = {
                        "image": len(attachment_image_urls),
                        "video": len(video_urls),
                        "other": len(attachments) - len(attachment_image_urls) - len(video_urls)
                    }

                    attachments_info = []
                    if file_types["image"] > 0:
                        attachments_info.append(f"🖼️ {file_types['image']}")
                    if file_types["video"] > 0:
                        attachments_info.append(f"🎬 {file_types['video']}")
                    if file_types["other"] > 0:
                        attachments_info.append(f"📎 {file_types['other']}")

                    embed.add_field(
                        name="Załączniki",
                        value=" ".join(attachments_info),
                        inline=False
                    )

                if video_urls:
                    video_links = "\n".join([f"[Wideo {i+1}]({url})" for i, url in enumerate(video_urls)])
                    embed.add_field(
                        name="🎬 Wideo",
                        value=video_links,
                        inline=False
                    )

            except Exception as e:
                print(f"Błąd przetwarzania załączników: {e}")

        gif_url = None
        for url in image_urls:
            if self.is_gif_url(url):
                gif_url = url
                break

        if gif_url:
            embed.set_image(url=gif_url)
            image_urls = [url for url in image_urls if url != gif_url]
            embed.add_field(
                name="🎬 GIF",
                value="Wyświetlono w powiększonym rozmiarze",
                inline=False
            )
        elif image_urls:
            embed.set_image(url=image_urls[0])
            image_urls = image_urls[1:]
        else:
            if embed_data:
                try:
                    original_embeds = json.loads(embed_data)
                    for embed_dict in original_embeds:
                        if 'image' in embed_dict and embed_dict['image'].get('url'):
                            url = embed_dict['image']['url']
                            if self.is_gif_url(url):
                                embed.set_image(url=url)
                                embed.add_field(
                                    name="🎬 GIF",
                                    value="Wyświetlono w powiększonym rozmiarze",
                                    inline=False
                                )
                                break

                        if 'thumbnail' in embed_dict and embed_dict['thumbnail'].get('url'):
                            url = embed_dict['thumbnail']['url']
                            if self.is_gif_url(url):
                                embed.set_image(url=url)
                                embed.add_field(
                                    name="🎬 GIF",
                                    value="Wyświetlono w powiększonym rozmiarze",
                                    inline=False
                                )
                                break
                except Exception as e:
                    print(f"Błąd przetwarzania embedów pod kątem GIF-ów: {e}")

        for url in image_urls:
            image_embed = discord.Embed(color=0x3498db)
            image_embed.set_image(url=url)
            additional_embeds.append(image_embed)

        if embed_data:
            try:
                original_embeds = json.loads(embed_data)
                for embed_dict in original_embeds:
                    additional_embeds.append(discord.Embed.from_dict(embed_dict))
            except Exception as e:
                print(f"Błąd przetwarzania embedów: {e}")

        return embed, additional_embeds, [guild_id, channel_id, message_id]

    def _process_raw_components_v2(self, raw_components: List[Dict]) -> Tuple[str, List[str], Dict[str, Any]]:
        content_parts = []
        image_urls = []
        metadata = {
            'has_buttons': False,
            'has_select_menus': False,
            'has_text_displays': False,
            'has_media_galleries': False,
            'has_files': False,
            'component_types': [],
            'layout_structure': []
        }

        def process_raw_component(component: Dict, depth: int = 0) -> None:
            indent = "  " * depth
            comp_type = component.get('type', 0)

            type_names = {
                1: "ActionRow",
                2: "Button",
                3: "SelectMenu",
                4: "TextInput",
                10: "TextDisplay",
                11: "MediaGallery",
                12: "File",
                13: "Separator",
                14: "Container",
                15: "Section",
                16: "Thumbnail",
                17: "ComponentsV2Root"
            }

            type_name = type_names.get(comp_type, f"Unknown({comp_type})")
            metadata['component_types'].append(type_name)

            if comp_type == 2:
                metadata['has_buttons'] = True
                label = component.get('label', 'No label')
                metadata['layout_structure'].append(f"{indent}🔘 Button: {label}")
                if component.get('url'):
                    metadata['layout_structure'].append(f"{indent}  🔗 URL: {component['url']}")

            elif comp_type == 3:
                metadata['has_select_menus'] = True
                placeholder = component.get('placeholder', 'No placeholder')
                metadata['layout_structure'].append(f"{indent}📋 Select Menu: {placeholder}")

            elif comp_type == 10:
                metadata['has_text_displays'] = True
                text_content = component.get('content', '') or component.get('text', '')
                if text_content:
                    content_parts.append(text_content)
                    metadata['layout_structure'].append(f"{indent}📝 Text Display: {text_content[:50]}{'...' if len(text_content) > 50 else ''}")

            elif comp_type == 11:
                metadata['has_media_galleries'] = True
                metadata['layout_structure'].append(f"{indent}🖼️ Media Gallery")
                for item in component.get('items', []):
                    media = item.get('media', {})
                    if media.get('url'):
                        image_urls.append(media['url'])
                        metadata['layout_structure'].append(f"{indent}  📎 Media: {media['url']}")

            elif comp_type == 12:
                metadata['has_files'] = True
                metadata['layout_structure'].append(f"{indent}📁 File Component")

            elif comp_type in [1, 14, 15, 17]:
                container_name = type_name
                metadata['layout_structure'].append(f"{indent}📦 {container_name}")
                for child in component.get('components', []):
                    process_raw_component(child, depth + 1)

            else:
                metadata['layout_structure'].append(f"{indent}❓ {type_name}")

        for component in raw_components:
            process_raw_component(component)

        return '\n'.join(content_parts), image_urls, metadata

    def _extract_components_v2_content_legacy(self, components_data: Union[str, List]) -> Tuple[str, List[str]]:
        content_parts = []
        image_urls = []

        if isinstance(components_data, str):
            try:
                components = json.loads(components_data)
            except:
                return "", []
        else:
            components = components_data

        def process_component(component):
            if component.get('type') == 17:
                for sub_component in component.get('components', []):
                    process_component(sub_component)
            elif component.get('type') == 10:
                text_content = component.get('content', '')
                if text_content:
                    content_parts.append(text_content)
            elif component.get('type') == 12:
                for item in component.get('items', []):
                    media = item.get('media', {})
                    if media.get('url'):
                        image_urls.append(media['url'])
            elif component.get('type') == 9:
                for sub_comp in component.get('components', []):
                    process_component(sub_comp)

        for component in components:
            process_component(component)

        return '\n'.join(content_parts), image_urls


class BookmarksPageView(discord.ui.View):
    def __init__(self, db_manager: DatabaseManager, bookmark_options: List[discord.SelectOption], page: int, max_pages: int):
        super().__init__(timeout=180)
        self.db_manager = db_manager
        self.page = page
        self.max_pages = max_pages

        if bookmark_options:
            select_menu = BookmarkSelectMenu(db_manager, bookmark_options)
            self.add_item(select_menu)

        prev_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            disabled=page <= 1,
            emoji="◀️"
        )
        prev_button.callback = self.prev_callback
        self.add_item(prev_button)

        next_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            disabled=page >= max_pages,
            emoji="▶️"
        )
        next_button.callback = self.next_callback
        self.add_item(next_button)

    async def prev_callback(self, interaction: discord.Interaction):
        new_page = self.page - 1
        bookmarks_view = BookmarksView(self.db_manager)
        new_embed, new_view, _, _, _ = await bookmarks_view.create_bookmarks_page(interaction.user.id, new_page)
        await interaction.response.edit_message(embed=new_embed, view=new_view)

    async def next_callback(self, interaction: discord.Interaction):
        new_page = self.page + 1
        bookmarks_view = BookmarksView(self.db_manager)
        new_embed, new_view, _, _, _ = await bookmarks_view.create_bookmarks_page(interaction.user.id, new_page)
        await interaction.response.edit_message(embed=new_embed, view=new_view)


class BookmarkSelectMenu(discord.ui.Select):
    def __init__(self, db_manager: DatabaseManager, options: List[discord.SelectOption]):
        super().__init__(
            placeholder="Wybierz zakładkę do wyświetlenia",
            options=options,
            custom_id="bookmark_select"
        )
        self.db_manager = db_manager

    async def callback(self, interaction: discord.Interaction):
        bookmark_id = int(self.values[0])
        bookmark = self.db_manager.get_bookmark_by_id(bookmark_id, interaction.user.id)

        if not bookmark:
            await interaction.response.send_message(
                "Nie znaleziono zakładki o podanym ID lub nie masz do niej dostępu.",
                ephemeral=True
            )
            return

        bookmarks_view = BookmarksView(self.db_manager)
        embed, additional_embeds, link_data = bookmarks_view.create_bookmark_detail_embed(bookmark)
        all_embeds = [embed] + additional_embeds

        view = BookmarkDetailView(self.db_manager, bookmark_id, link_data)
        await interaction.response.send_message(
            embeds=all_embeds,
            view=view,
            ephemeral=True
        )


class BookmarkDetailView(discord.ui.View):
    def __init__(self, db_manager: DatabaseManager, bookmark_id: int, link_data: List[str]):
        super().__init__(timeout=180)
        self.db_manager = db_manager
        self.bookmark_id = bookmark_id
        self.guild_id, self.channel_id, self.message_id = link_data

        delete_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            emoji="🗑️"
        )
        delete_button.callback = self.delete_callback
        self.add_item(delete_button)

        link_button = discord.ui.Button(
            style=discord.ButtonStyle.link,
            emoji="🔗",
            url=f"https://discord.com/channels/{self.guild_id}/{self.channel_id}/{self.message_id}"
        )
        self.add_item(link_button)

    async def delete_callback(self, interaction: discord.Interaction):
        success, message = self.db_manager.delete_bookmark(self.bookmark_id, interaction.user.id)
        if success:
            await interaction.response.edit_message(
                content="✅ Zakładka usunięta",
                embeds=[],
                view=None
            )
        else:
            await interaction.response.send_message(message, ephemeral=True)
