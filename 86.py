import discord
import aiohttp
import json
import os
import asyncio
import re
from discord.ext import commands, tasks
from discord import app_commands

# === 1. CONFIG ===
YOUR_BOT_TOKEN = os.environ.get('YOUR_BOT_TOKEN')
YOUR_GUILD_ID_STR = os.environ.get('YOUR_GUILD_ID')
TARGET_CHANNEL_ID_STR = os.environ.get('TARGET_CHANNEL_ID')

# (ตรวจสอบ Config)
if not YOUR_BOT_TOKEN: raise ValueError("!!! ไม่พบ YOUR_BOT_TOKEN !!!")
if not YOUR_GUILD_ID_STR: raise ValueError("!!! ไม่พบ YOUR_GUILD_ID !!!")
if not TARGET_CHANNEL_ID_STR: raise ValueError("!!! ไม่พบ TARGET_CHANNEL_ID !!!")
try:
    YOUR_GUILD_ID = int(YOUR_GUILD_ID_STR)
    TARGET_CHANNEL_ID = int(TARGET_CHANNEL_ID_STR)
except ValueError:
    raise ValueError("!!! GUILD_ID หรือ TARGET_CHANNEL_ID ต้องเป็นตัวเลข !!!")

# (ค่าตั้งค่าอื่นๆ)
LOOP_TIMER_MINUTES = 30
MAX_SLOTS = 30
SERVER_URL = "http://one-city.myddns.me:30120/players.json"

# (ตั้งค่า Path สำหรับ Railway หรือ Render)
# (ถ้าใช้ Render ให้เปลี่ยน /data เป็น /var/data)
PERSISTENT_DATA_PATH = os.environ.get('RENDER_DISK_MOUNT_PATH', '/data') 
WATCHLIST_FILE = os.path.join(PERSISTENT_DATA_PATH, "watchlist.json")
MESSAGE_ID_FILE = os.path.join(PERSISTENT_DATA_PATH, "message_id.json")


# === 2. Watchlist & Message ID Handlers ===
def get_watchlist():
    if not os.path.exists(WATCHLIST_FILE): return []
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError: return []

def save_watchlist(watchlist_data):
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist_data, f, indent=4, ensure_ascii=False)

def get_last_message_id():
    if not os.path.exists(MESSAGE_ID_FILE): return None
    try:
        with open(MESSAGE_ID_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("last_message_id")
    except (json.JSONDecodeError, AttributeError): return None

def save_last_message_id(message_id: int):
    os.makedirs(os.path.dirname(MESSAGE_ID_FILE), exist_ok=True)
    with open(MESSAGE_ID_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_message_id": message_id}, f)


# === 3. Discord Bot Setup ===
intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)


# === 4. ฟังก์ชัน "ทำความสะอาด" ชื่อ ===
def normalize_name(name: str):
    if not isinstance(name, str): return ""
    return " ".join(name.lower().split()).strip()

# === 5. Fetch Player Data ===
async def fetch_fivem_players():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(SERVER_URL, timeout=10) as resp:
                if resp.status == 200:
                    try: data = await resp.json()
                    except aiohttp.ContentTypeError: data = json.loads(await resp.text())
                    online_names = [p['name'] for p in data if "name" in p]
                    print(f"✅ ดึงข้อมูลสำเร็จ: {len(online_names)} คนออนไลน์")
                    return online_names
                else:
                    print(f"❌ Server responded with status {resp.status}")
                    return None
    except Exception as e:
        print(f"⚠️ Error fetching players: {e}")
        return None

# === 6. Create Embed ===
async def create_status_embed(bot_client: commands.Bot):
    WATCHED_PLAYERS = get_watchlist()
    if not WATCHED_PLAYERS: return discord.Embed(title="ℹ️ รายชื่อว่างเปล่า", description="ยังไม่มีรายชื่อผู้เล่น กรุณาใช้คำสั่ง `/addplayer` เพื่อเพิ่มก่อน", color=discord.Color.orange())
    online_players = await fetch_fivem_players()
    if online_players is None: return discord.Embed(title="❌ เกิดข้อผิดพลาด", description=f"ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์เกมได้", color=discord.Color.red())
    
    # (ตรรกะ Fuzzy Matching)
    full_name_online_set = {normalize_name(name) for name in online_players}
    base_name_online_set = set()
    for name in online_players:
        base_name = re.sub(r'\[.*?\]', '', name).strip()
        normalized_base = normalize_name(base_name)
        if normalized_base: base_name_online_set.add(normalized_base)
    online_list_in_watch, offline_list_in_watch = [], []
    for player_name in WATCHED_PLAYERS:
        normalized_watchlist_full = normalize_name(player_name)
        watchlist_base = re.sub(r'\[.*?\]', '', player_name).strip()
        normalized_watchlist_base = normalize_name(watchlist_base)
        found_full = normalized_watchlist_full in full_name_online_set
        found_base = False
        if normalized_watchlist_base: found_base = normalized_watchlist_base in base_name_online_set
        if found_full or found_base: online_list_in_watch.append(player_name)
        else: offline_list_in_watch.append(player_name)

    # (สร้าง Embed)
    embed = discord.Embed(title="รายงานสถานะผู้เล่น (One City)", description="ข้อมูลสถานะของผู้เล่นที่เฝ้าดู", color=discord.Color.blue())
    if bot_client.user and bot_client.user.avatar: embed.set_author(name="สถานะผู้เล่น", icon_url=bot_client.user.avatar.url)
    embed.add_field(name="⏰ เวลา", value=f"<t:{int(discord.utils.utcnow().timestamp())}:R>", inline=False)
    embed.add_field(name="📋 รายชื่อที่เฝ้าดู", value=f"{len(WATCHED_PLAYERS)} / {MAX_SLOTS} คน", inline=False)
    embed.add_field(name="✅ ผู้เล่นออนไลน์", value=f"{len(online_list_in_watch)} คน", inline=False)
    embed.add_field(name="❌ ผู้เล่นไม่ออนไลน์", value=f"{len(offline_list_in_watch)} คน", inline=False)
    if online_list_in_watch:
        online_text = "\n".join([f"• {name}" for name in online_list_in_watch])
        if len(online_text) > 1020: online_text = online_text[:1020] + "..."
        embed.add_field(name="🟢 รายชื่อผู้เล่นออนไลน์", value=online_text, inline=False)
    else: embed.add_field(name="🟢 รายชื่อผู้เล่นออนไลน์", value="ไม่มีผู้เล่นที่เฝ้าดูออนไลน์ในขณะนี้", inline=False)
    if offline_list_in_watch:
        offline_text = "\n".join([f"• {name}" for name in offline_list_in_watch])
        if len(offline_text) > 1020: offline_text = offline_text[:1020] + "..."
        embed.add_field(name="🔴 รายชื่อผู้เล่นไม่ออนไลน์", value=offline_text, inline=False)
    else: embed.add_field(name="🔴 รายชื่อผู้เล่นไม่ออนไลน์", value="ทุกคนออนไลน์ครบ!", inline=False)
    embed.set_footer(text="One City x Your System (Auto-Check)")
    return embed

# === 7. Slash Commands (นี่คือส่วนที่แก้ไขแล้ว) ===
@bot.tree.command(name="check", description="ตรวจสอบสถานะผู้เล่น (Manual)", guild=discord.Object(id=YOUR_GUILD_ID))
async def check_status(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = await create_status_embed(interaction.client)
    embed.title = "ระบบตรวจสอบรายชื่อ (One City)"
    embed.description = "ข้อมูลสถานะของผู้เล่น (ตรวจสอบด้วยตนเอง)"
    embed.set_footer(text="One City x Your System (Manual Check)")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="addplayer", description="เพิ่มผู้เล่นเข้าสู่ watchlist (Admin)", guild=discord.Object(id=YOUR_GUILD_ID))
@app_commands.describe(player_name="ชื่อผู้เล่น เช่น [86] John Doe")
@app_commands.default_permissions(manage_messages=True) 
async def add_player(interaction: discord.Interaction, player_name: str):
    watchlist = get_watchlist()
    if len(watchlist) >= MAX_SLOTS:
        await interaction.response.send_message(f"❌ รายชื่อเต็มแล้ว ({MAX_SLOTS} slots)", ephemeral=True)
        return
    normalized_new_name_full = normalize_name(player_name)
    new_base = re.sub(r'\[.*?\]', '', player_name).strip()
    normalized_new_name_base = normalize_name(new_base)
    for existing_name in watchlist:
        normalized_existing_full = normalize_name(existing_name)
        existing_base = re.sub(r'\[.*?\]', '', existing_name).strip()
        normalized_existing_base = normalize_name(existing_base)
        if (normalized_new_name_full == normalized_existing_full) or \
           (normalized_new_name_base and (normalized_new_name_base == normalized_existing_base)):
            await interaction.response.send_message(f"❌ ผู้เล่น `{player_name}` อยู่ในรายชื่อแล้ว (หรือชื่อซ้ำซ้อนกับ `{existing_name}`)", ephemeral=True)
            return
    watchlist.append(player_name)
    save_watchlist(watchlist)
    await interaction.response.send_message(f"✅ เพิ่ม `{player_name}` สำเร็จ ({len(watchlist)}/{MAX_SLOTS})", ephemeral=True)

async def player_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    watchlist = get_watchlist()
    choices = [app_commands.Choice(name=p, value=p) for p in watchlist if current.lower() in p.lower()]
    return choices[:25]

@bot.tree.command(name="removeplayer", description="ลบผู้เล่นออกจาก watchlist (Admin)", guild=discord.Object(id=YOUR_GUILD_ID))
@app_commands.describe(player_name="ชื่อผู้เล่นที่ต้องการลบ (พิมพ์เพื่อค้นหา)")
@app_commands.autocomplete(player_name=player_autocomplete)
@app_commands.default_permissions(manage_messages=True)
async def remove_player(interaction: discord.Interaction, player_name: str):
    watchlist = get_watchlist()
    found = False
    name_to_remove = None
    normalized_name_to_remove = normalize_name(player_name)
    base_name_to_remove = normalize_name(re.sub(r'\[.*?\]', '', player_name).strip())
    for name in watchlist:
        normalized_existing = normalize_name(name)
        normalized_existing_base = normalize_name(re.sub(r'\[.*?\]', '', name).strip())
        if (name == player_name) or (normalized_existing == normalized_name_to_remove) or \
           (normalized_existing_base and (normalized_existing_base == base_name_to_remove)):
            name_to_remove = name
            found = True
            break
    if not found:
        await interaction.response.send_message(f"❌ ไม่พบผู้เล่น `{player_name}` ในรายชื่อ", ephemeral=True)
        return
    watchlist.remove(name_to_remove)
    save_watchlist(watchlist)
    await interaction.response.send_message(f"🗑️ ลบ `{name_to_remove}` สำเร็จ ({len(watchlist)}/{MAX_SLOTS})", ephemeral=True)

@bot.tree.command(name="listplayers", description="แสดงรายชื่อผู้เล่นทั้งหมดใน watchlist", guild=discord.Object(id=YOUR_GUILD_ID))
async def list_players(interaction: discord.Interaction):
    watchlist = get_watchlist()
    if not watchlist:
        await interaction.response.send_message("ℹ️ รายชื่อว่างเปล่า", ephemeral=True)
        return
    embed = discord.Embed(title=f"รายชื่อผู้เล่น ({len(watchlist)}/{MAX_SLOTS})", color=discord.Color.green())
    description = "\n".join(f"{i+1}. {name}" for i, name in enumerate(watchlist))
    if len(description) > 4000: description = description[:4000] + "..."
    embed.description = description
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- (นี่คือฟังก์ชันที่ error หายไป) ---
async def post_or_edit_status(bot_instance: commands.Bot, is_first_post: bool = False):
    """
    ฟังก์ชันกลางสำหรับสร้างและส่ง/แก้ไข Embed
    is_first_post: ถ้าเป็น True จะแสดงข้อความตอนเริ่มบอท
    """
    channel = bot_instance.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        print(f"!!! Error: ไม่พบช่อง ID {TARGET_CHANNEL_ID} !!!")
        return

    print("กำลังสร้าง Embed...")
    embed = await create_status_embed(bot_instance)
    if is_first_post:
        embed.add_field(name="🚀 Bot Status", value="บอทเริ่มทำงาน / รีสตาร์ทสำเร็จ", inline=False)

    last_message_id = get_last_message_id()

    try:
        if last_message_id:
            message = await channel.fetch_message(last_message_id)
            await message.edit(embed=embed)
            print(f"แก้ไขข้อความ #{last_message_id} สำเร็จ")
        else:
            message = await channel.send(embed=embed)
            save_last_message_id(message.id)
            print(f"ส่งรายงานใหม่ #{message.id} สำเร็จ")
    except discord.errors.NotFound:
        print(f"ข้อความ #{last_message_id} ไม่พบ, กำลังส่งใหม่...")
        message = await channel.send(embed=embed)
        save_last_message_id(message.id)
    except discord.errors.Forbidden:
        print(f"!!! Error: ไม่มีสิทธิ์ในช่อง {channel.name} (อาจจะไม่มีสิทธิ์ 'Read Message History')")
        save_last_message_id(None) # รีเซ็ต ID
    except Exception as e:
        print(f"!!! เกิดข้อผิดพลาดไม่คาดคิด: {e}")
        save_last_message_id(None)


# === 8. Task Loop & on_ready ===
@bot.event
async def on_ready():
    print(f"✅ Bot {bot.user} ล็อกอินสำเร็จ!")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=YOUR_GUILD_ID))
        print(f"Synced {len(synced)} command(s) to guild {YOUR_GUILD_ID}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    
    print("_Boot: กำลังส่งสถานะครั้งแรก...")
    await post_or_edit_status(bot, is_first_post=True)


class StatusCheckLoop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status_check_task.start()

    def cog_unload(self):
        self.status_check_task.cancel()

    @tasks.loop(minutes=LOOP_TIMER_MINUTES)
    async def status_check_task(self):
        print("[Task Loop] กำลังตรวจสอบสถานะ...")
        await post_or_edit_status(self.bot)

    @status_check_task.before_loop
    async def before_status_check_task(self):
        print("Waiting for bot to be ready...")
        await self.bot.wait_until_ready()
        print("Bot ready, starting loop.")


# === 9. Run Bot ===
async def main():
    async with bot:
        await bot.add_cog(StatusCheckLoop(bot))
        await bot.start(YOUR_BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
