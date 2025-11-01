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
LOOP_TIMER_MINUTES = 15
MAX_SLOTS = 20
SERVER_URL = "http://one-city.myddns.me:30120/players.json"
PERSISTENT_DATA_PATH = "/data" # (สำหรับ Railway) หรือ "/var/data" (สำหรับ Render)
WATCHLIST_FILE = os.path.join(PERSISTENT_DATA_PATH, "watchlist.json")

# ---!! [ใหม่] 1.2 เพิ่ม Config สำหรับ Message ID !! ---
MESSAGE_ID_FILE = os.path.join(PERSISTENT_DATA_PATH, "message_id.json")
# ---!! จบส่วนใหม่ !! ---


# === 2. Watchlist Handler (เหมือนเดิม) ===
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

# ---!! [ใหม่] 2.1 เพิ่ม Helper Functions สำหรับ Message ID !! ---
def get_last_message_id():
    """อ่าน Message ID จากไฟล์"""
    if not os.path.exists(MESSAGE_ID_FILE): return None
    try:
        with open(MESSAGE_ID_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("last_message_id")
    except (json.JSONDecodeError, AttributeError): return None

def save_last_message_id(message_id: int):
    """บันทึก Message ID ลงไฟล์"""
    os.makedirs(os.path.dirname(MESSAGE_ID_FILE), exist_ok=True)
    with open(MESSAGE_ID_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_message_id": message_id}, f)
# ---!! จบส่วนใหม่ !! ---


# === 3. Discord Bot Setup (เหมือนเดิม) ===
intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# (โค้ดส่วน 4, 5, 6, 7 เหมือนเดิมเป๊ะๆ)
# ... (ผมย่อโค้ดส่วนนี้ไว้เพื่อความกระชับ แต่ในไฟล์จริงของคุณต้องมีครบนะครับ) ...
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
# === 7. Slash Commands ===
@bot.tree.command(name="check", description="ตรวจสอบสถานะผู้เล่น (Manual)", guild=discord.Object(id=YOUR_GUILD_ID))
async def check_status(interaction: discord.Interaction):
    # ... (โค้ดเหมือนเดิม) ...
# (และคำสั่ง add/remove/list อื่นๆ)
# ...


# ---!! [ใหม่] ฟังก์ชันสำหรับโพสต์/แก้ไขสถานะ !! ---
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


# ---!! [แก้ไข] on_ready event !! ---
@bot.event
async def on_ready():
    print(f"✅ Bot {bot.user} ล็อกอินสำเร็จ!")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=YOUR_GUILD_ID))
        print(f"Synced {len(synced)} command(s) to guild {YOUR_GUILD_ID}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    
    # ---!! สั่งให้ทำงานทันทีหลังรีสตาร์ท !! ---
    print("_Boot: กำลังส่งสถานะครั้งแรก...")
    await post_or_edit_status(bot, is_first_post=True)


# ---!! [แก้ไข] 8. Task Loop !! ---
class StatusCheckLoop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status_check_task.start()

    def cog_unload(self):
        self.status_check_task.cancel()

    @tasks.loop(minutes=LOOP_TIMER_MINUTES)
    async def status_check_task(self):
        print("[Task Loop] กำลังตรวจสอบสถานะ...")
        # ---!! เรียกใช้ฟังก์ชันกลางที่เราสร้างขึ้น !! ---
        await post_or_edit_status(self.bot)

    @status_check_task.before_loop
    async def before_status_check_task(self):
        print("Waiting for bot to be ready...")
        await self.bot.wait_until_ready()
        print("Bot ready, starting loop.")


# === 9. Run Bot (เหมือนเดิม) ===
async def main():
    async with bot:
        await bot.add_cog(StatusCheckLoop(bot))
        await bot.start(YOUR_BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
