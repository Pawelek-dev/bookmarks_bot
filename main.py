import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('token')

intents = discord.Intents.all()

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Zalogowano jako {bot.user.name}')
    
    try:
        await bot.load_extension('cogs.bookmarks')
        print("Załadowano cog: bookmarks")
    except Exception as e:
        print(f"Błąd podczas ładowania cog bookmarks: {e}")
    
    try:
        synced = await bot.tree.sync()
        print(f"Zsynchronizowano {len(synced)} komend")
    except Exception as e:
        print(f"Błąd podczas synchronizacji komend: {e}")

if __name__ == "__main__":
    bot.run(TOKEN)
