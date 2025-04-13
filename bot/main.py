import discord
from discord import app_commands
import sqlite3
import datetime
import json
from typing import Optional

TOKEN = 'token_bocika'
DB_PATH = 'bookmarks.db'

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,
        message_content TEXT,
        embed_data TEXT,
        author_name TEXT,
        author_avatar TEXT,
        timestamp TEXT,
        created_at TEXT
    )
    ''')

    cursor = conn.execute("PRAGMA table_info(bookmarks)")
    columns = [column[1] for column in cursor.fetchall()]

    if 'attachments_data' not in columns:
        try:
            c.execute('ALTER TABLE bookmarks ADD COLUMN attachments_data TEXT')
            print("Dodano nową kolumnę 'attachments_data' do tabeli bookmarks")
        except sqlite3.Error as e:
            print(f"Błąd podczas dodawania kolumny: {e}")

    conn.commit()
    conn.close()

def save_bookmark(user_id, message, embed_data=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    author_name = message.author.display_name
    author_avatar = str(message.author.avatar.url) if message.author.avatar else None
    timestamp = message.created_at.isoformat()
    created_at = datetime.datetime.now().isoformat()

    attachments_data = None
    if message.attachments:
        attachments_list = []
        for attachment in message.attachments:
            attachment_info = {
                'id': attachment.id,
                'url': attachment.url,
                'filename': attachment.filename,
                'content_type': attachment.content_type,
                'width': attachment.width if hasattr(attachment, 'width') else None,
                'height': attachment.height if hasattr(attachment, 'height') else None,
                'size': attachment.size,
                'is_image': attachment.content_type and attachment.content_type.startswith('image/')
            }
            attachments_list.append(attachment_info)

        if attachments_list:
            attachments_data = json.dumps(attachments_list)

    c.execute('''
    INSERT INTO bookmarks
    (user_id, message_id, channel_id, guild_id, message_content,
     embed_data, author_name, author_avatar, timestamp, created_at, attachments_data)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, message.id, message.channel.id, message.guild.id, message.content,
        embed_data, author_name, author_avatar, timestamp, created_at, attachments_data
    ))

    bookmark_id = c.lastrowid
    conn.commit()
    conn.close()
    return bookmark_id

def get_user_bookmarks(user_id, page=1, per_page=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    offset = (page - 1) * per_page
    c.execute('''
    SELECT * FROM bookmarks
    WHERE user_id = ?
    ORDER BY created_at DESC
    LIMIT ? OFFSET ?
    ''', (user_id, per_page, offset))

    bookmarks = c.fetchall()

    c.execute('SELECT COUNT(*) FROM bookmarks WHERE user_id = ?', (user_id,))
    total = c.fetchone()[0]

    conn.close()
    return bookmarks, total

def delete_bookmark(bookmark_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('SELECT user_id FROM bookmarks WHERE id = ?', (bookmark_id,))
    result = c.fetchone()

    if not result:
        conn.close()
        return False, "Zakładka nie istnieje."

    if result[0] != user_id:
        conn.close()
        return False, "Nie masz uprawnień do usunięcia tej zakładki."

    c.execute('DELETE FROM bookmarks WHERE id = ?', (bookmark_id,))
    conn.commit()
    conn.close()
    return True, "Zakładka została usunięta."

@bot.event
async def on_ready():
    print(f'Zalogowano jako {bot.user.name}')
    init_db()
    await tree.sync()

@tree.context_menu(name="Save Message")
@app_commands.allowed_installs(guilds=False, users=True)
async def save_message_command(interaction: discord.Interaction, message: discord.Message):
    embed_data = None
    if message.embeds:
        embed_list = []
        for embed in message.embeds:
            embed_dict = embed.to_dict()
            embed_list.append(embed_dict)
        embed_data = json.dumps(embed_list)

    bookmark_id = save_bookmark(interaction.user.id, message, embed_data)

    embed = discord.Embed(
        title="📌 Wiadomość zapisana!",
        description=f"Zapisano wiadomość od {message.author.mention}",
        color=0x00FF00
    )
    embed.add_field(name="ID zakładki", value=bookmark_id)

    if message.attachments:
        attachment_count = len(message.attachments)
        embed.add_field(
            name="📎 Załączniki",
            value=f"Zapisano {attachment_count} {'załącznik' if attachment_count == 1 else 'załączniki' if 1 < attachment_count < 5 else 'załączników'}"
        )

    embed.set_footer(text=f"Użyj /bookmarks aby zobaczyć swoje zakładki")

    await interaction.response.send_message(embed=embed, ephemeral=True)

async def create_bookmarks_page(user_id, page=1):
    if page < 1:
        page = 1

    bookmarks, total = get_user_bookmarks(user_id, page)
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
                    attachment_info += f" 📷 {image_count}"
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

    view = discord.ui.View(timeout=180)

    select_menu = discord.ui.Select(
        placeholder="Wybierz zakładkę do wyświetlenia",
        options=bookmark_options,
        custom_id="bookmark_select"
    )

    async def select_callback(interaction):
        bookmark_id = int(interaction.data["values"][0])

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute('SELECT * FROM bookmarks WHERE id = ? AND user_id = ?', (bookmark_id, interaction.user.id))
        bookmark = c.fetchone()
        conn.close()

        if not bookmark:
            await interaction.response.send_message(
                "Nie znaleziono zakładki o podanym ID lub nie masz do niej dostępu.",
                ephemeral=True
            )
            return

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

        embed = discord.Embed(
            title=f"📝 Zakładka #{bookmark_id}",
            description=message_content or "*Brak treści*",
            color=0x3498db,
            timestamp=datetime.datetime.fromisoformat(bookmark[9])
        )

        if author_avatar:
            embed.set_author(name=author_name, icon_url=author_avatar)
        else:
            embed.set_author(name=author_name)

        embed.add_field(name="Oryginalny kanał", value=f"<#{channel_id}>", inline=True)
        embed.add_field(name="Link do wiadomości", value=f"[Kliknij tutaj](https://discord.com/channels/{guild_id}/{channel_id}/{message_id})", inline=True)

        additional_embeds = []
        image_urls = []
        attachment_count = 0

        if attachments_data:
            try:
                attachments = json.loads(attachments_data)
                attachment_count = len(attachments)

                image_urls = [att["url"] for att in attachments if att.get("is_image")]

                if attachments:
                    file_types = {
                        "image": len(image_urls),
                        "other": len(attachments) - len(image_urls)
                    }

                    attachments_info = []
                    if file_types["image"] > 0:
                        attachments_info.append(f"🖼️ {file_types['image']}")
                    if file_types["other"] > 0:
                        attachments_info.append(f"📎 {file_types['other']}")

                    embed.add_field(
                        name="Załączniki",
                        value=" ".join(attachments_info),
                        inline=False
                    )

            except Exception as e:
                print(f"Błąd przetwarzania załączników: {e}")

        if image_urls:
            embed.set_image(url=image_urls[0])

        for url in image_urls[1:]:
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

        all_embeds = [embed] + additional_embeds

        view = discord.ui.View(timeout=180)

        delete_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            emoji="🗑️"
        )

        async def delete_callback(interaction):
            success, message = delete_bookmark(bookmark_id, interaction.user.id)
            if success:
                await interaction.response.edit_message(
                    content="✅ Zakładka usunięta",
                    embeds=[],
                    view=None
                )
            else:
                await interaction.response.send_message(message, ephemeral=True)

        delete_button.callback = delete_callback
        view.add_item(delete_button)

        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.link,
            emoji="🔗",
            url=f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
        ))

        await interaction.response.send_message(
            embeds=all_embeds,
            view=view,
            ephemeral=True
        )

    select_menu.callback = select_callback
    view.add_item(select_menu)

    prev_button = discord.ui.Button(
        style=discord.ButtonStyle.secondary,
        disabled=page <= 1,
        custom_id=f"prev_page_{page}",
        emoji="◀️"
    )

    next_button = discord.ui.Button(
        style=discord.ButtonStyle.secondary,
        disabled=page >= max_pages,
        custom_id=f"next_page_{page}",
        emoji="▶️"
        
    )

    async def prev_callback(interaction):
        new_page = page - 1
        new_embed, new_view, _, _, _ = await create_bookmarks_page(interaction.user.id, new_page)
        await interaction.response.edit_message(embed=new_embed, view=new_view)

    async def next_callback(interaction):
        new_page = page + 1
        new_embed, new_view, _, _, _ = await create_bookmarks_page(interaction.user.id, new_page)
        await interaction.response.edit_message(embed=new_embed, view=new_view)

    prev_button.callback = prev_callback
    next_button.callback = next_callback

    view.add_item(prev_button)
    view.add_item(next_button)

    return embed, view, bookmarks, total, max_pages

@tree.command(name="bookmarks", description="Wyświetl swoje zapisane wiadomości")
@app_commands.allowed_installs(guilds=False, users=True)
@app_commands.describe(page="Numer strony (domyślnie 1)")
async def bookmarks_command(interaction: discord.Interaction, page: Optional[int] = 1):
    if page < 1:
        page = 1

    embed, view, bookmarks, total, max_pages = await create_bookmarks_page(interaction.user.id, page)

    if not bookmarks:
        empty_embed = discord.Embed(
            title="📚 Twoje zakładki",
            description="Nie masz jeszcze zapisanych wiadomości.",
            color=0x3498db
        )
        await interaction.response.send_message(embed=empty_embed, ephemeral=True)
        return

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@tree.command(name="bookmark", description="Wyświetl szczegóły zapisanej wiadomości")
@app_commands.allowed_installs(guilds=False, users=True)
@app_commands.describe(id="ID zakładki")
async def bookmark_command(interaction: discord.Interaction, id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('SELECT * FROM bookmarks WHERE id = ? AND user_id = ?', (id, interaction.user.id))
    bookmark = c.fetchone()
    conn.close()

    if not bookmark:
        await interaction.response.send_message(
            "Nie znaleziono zakładki o podanym ID lub nie masz do niej dostępu.",
            ephemeral=True
        )
        return

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

    embed = discord.Embed(
        title=f"📝 Zakładka #{bookmark_id}",
        description=message_content or "*Brak treści*",
        color=0x3498db,
        timestamp=datetime.datetime.fromisoformat(bookmark[9])
    )

    if author_avatar:
        embed.set_author(name=author_name, icon_url=author_avatar)
    else:
        embed.set_author(name=author_name)

    embed.add_field(name="Oryginalny kanał", value=f"<#{channel_id}>", inline=True)
    embed.add_field(name="Link do wiadomości", value=f"[Kliknij tutaj](https://discord.com/channels/{guild_id}/{channel_id}/{message_id})", inline=True)

    additional_embeds = []
    image_urls = []
    attachment_count = 0

    if attachments_data:
        try:
            attachments = json.loads(attachments_data)
            attachment_count = len(attachments)

            image_urls = [att["url"] for att in attachments if att.get("is_image")]

            if attachments:
                file_types = {
                    "image": len(image_urls),
                    "other": len(attachments) - len(image_urls)
                }

                attachments_info = []
                if file_types["image"] > 0:
                    attachments_info.append(f"🖼️ {file_types['image']}")
                if file_types["other"] > 0:
                    attachments_info.append(f"📎 {file_types['other']}")

                embed.add_field(
                    name="Załączniki",
                    value=" ".join(attachments_info),
                    inline=False
                )

        except Exception as e:
            print(f"Błąd przetwarzania załączników: {e}")

    if image_urls:
        embed.set_image(url=image_urls[0])

    for url in image_urls[1:]:
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

    all_embeds = [embed] + additional_embeds

    view = discord.ui.View(timeout=180)

    delete_button = discord.ui.Button(
        style=discord.ButtonStyle.danger,
        emoji="🗑️"
    )

    async def delete_callback(interaction):
        success, message = delete_bookmark(bookmark_id, interaction.user.id)
        if success:
            await interaction.response.edit_message(
                content="✅ Zakładka usunięta",
                embeds=[],
                view=None
            )
        else:
            await interaction.response.send_message(message, ephemeral=True)

    delete_button.callback = delete_callback
    view.add_item(delete_button)

    view.add_item(discord.ui.Button(
        style=discord.ButtonStyle.link,
        emoji="🔗",
        url=f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
    ))

    await interaction.response.send_message(
        embeds=all_embeds,
        view=view,
        ephemeral=True
    )

@tree.command(name="delete_bookmark", description="Usuń zakładkę")
@app_commands.allowed_installs(guilds=False, users=True)
@app_commands.describe(id="ID zakładki do usunięcia")
async def delete_bookmark_command(interaction: discord.Interaction, id: int):
    success, message = delete_bookmark(id, interaction.user.id)

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

bot.run(TOKEN)
