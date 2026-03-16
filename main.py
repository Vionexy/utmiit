import asyncio
import httpx
from io import BytesIO
import fitz
import hashlib
import os
from PIL import Image
from datetime import datetime, timezone, timedelta
import aiosqlite
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, LabeledPrice, PreCheckoutQuery, \
    Message
from collections import defaultdict
import time
import random

# токен бота
API_TOKEN = os.getenv("BOT_TOKEN")

bot = AsyncTeleBot(API_TOKEN)
ADMIN_ID = 6986627524


# кастомная кнопка с цветом (API 9.4)
class MyButton(InlineKeyboardButton):
    def __init__(self, text, callback_data=None, style=None, **kwargs):
        super().__init__(text, callback_data=callback_data, **kwargs)
        self.style = style

    def to_dict(self):
        d = super().to_dict()
        if self.style:
            d['style'] = self.style
        return d


# расписания с гугла
SCHEDULE_FILES = {
    "monday": {"id": "1d7xrNLd8qpde_5jLvBdJjG9e3eOsjohK", "name": "понедельник",
               "link": "https://drive.google.com/file/d/1d7xrNLd8qpde_5jLvBdJjG9e3eOsjohK/view"},
    "tuesday": {"id": "1qHNHC7uwXdECuEMfDoPiuv5bX0Ip0OpQ", "name": "вторник",
                "link": "https://drive.google.com/file/d/1qHNHC7uwXdECuEMfDoPiuv5bX0Ip0OpQ/view"},
    "wednesday": {"id": "1hWMqMdeU2rcrNMx4jbOCr5ofGixsIJwA", "name": "среду",
                  "link": "https://drive.google.com/file/d/1hWMqMdeU2rcrNMx4jbOCr5ofGixsIJwA/view"},
    "thursday": {"id": "1O649rLM_VuBO31VF49noXfp1Evr-XfCN", "name": "четверг",
                 "link": "https://drive.google.com/file/d/1O649rLM_VuBO31VF49noXfp1Evr-XfCN/view"},
    "friday": {"id": "1YmQGiirdBryJlI3tx0SdU-g1gGm-6AaW", "name": "пятницу",
               "link": "https://drive.google.com/file/d/1YmQGiirdBryJlI3tx0SdU-g1gGm-6AaW/view"},
    "saturday": {"id": "1hkXSDN-Dz86QGeyjhLZ7jlvSd9sMwmex", "name": "субботу",
                 "link": "https://drive.google.com/file/d/1hkXSDN-Dz86QGeyjhLZ7jlvSd9sMwmex/view"},
}

# звонки
CALLS = {
    "monday_calls": """<b>Понедельник</b>

<b>1⃣</b> 8:30–9:15 | 9:20–10:05

<b>2⃣</b> 10:15–11:00
🍴 <b>Обед:</b> 11:00–11:15
<b>2⃣</b> 11:15–12:00

🍴 <b>Обед:</b> 12:00–12:30

🕐 <b>Классные часы:</b> 12:30–13:00

<b>3⃣</b> 13:05–13:50 | 13:55–14:40

<b>4⃣</b> 14:45–15:30 | 15:35–16:20""",

    "thursday_calls": """<b>Четверг</b>

<b>1⃣</b> 8:30–9:15 | 9:20–10:05

<b>2⃣</b> 10:15–11:00
🍴 <b>Обед:</b> 11:00–11:15
<b>2⃣</b> 11:15–12:00

🍴 <b>Обед:</b> 12:00–12:30

<b>3⃣</b> 12:30–13:15 | 13:20–14:05

<b>4⃣</b> 14:10–14:55 | 15:00–15:45

🕐 <b>Классные часы (1 курс):</b> 15:50–16:20""",

    "other_calls": """<b>Другие дни</b>

<b>1⃣</b> 8:30–9:15 | 9:20–10:05

<b>2⃣</b> 10:15–11:00
🍴 <b>Обед:</b> 11:00–11:15
<b>2⃣</b> 11:15–12:00

🍴 <b>Обед:</b> 12:00–12:40

<b>3⃣</b> 12:40–13:25 | 13:30–14:15

<b>4⃣</b> 14:25–15:10 | 15:15–16:00

<b>5⃣</b> 16:05–16:50 | 16:55–17:40"""
}

# кэш и состояния
cache = {}
locks = defaultdict(asyncio.Lock)
states = {}
send_limit = asyncio.Semaphore(25)
view_count = defaultdict(int)  # счётчик просмотров расписания на юзера

PAGE_SIZE = 50
CACHE_TTL = 3600
DONATE_EVERY = 4  # показывать донат каждые N просмотров

db_conn = None


# === БД ===

async def get_db():
    global db_conn
    if db_conn is None:
        db_conn = await aiosqlite.connect("subscribers.db")
    return db_conn


async def init_db():
    db = await get_db()
    await db.execute("""CREATE TABLE IF NOT EXISTS subscribers
                        (chat_id INTEGER PRIMARY KEY, joined_date TEXT)""")
    await db.execute("""CREATE TABLE IF NOT EXISTS schedule_updates
                        (day TEXT PRIMARY KEY, last_hash TEXT, last_sent_date TEXT)""")
    await db.execute("""CREATE TABLE IF NOT EXISTS all_users
                        (chat_id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT,
                         username TEXT, first_interaction_date TEXT)""")
    await db.execute("""CREATE TABLE IF NOT EXISTS interactions
                        (chat_id INTEGER, interaction_date TEXT)""")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_sub ON subscribers(chat_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_day ON schedule_updates(day)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_int ON interactions(interaction_date)")

    try:
        cur = await db.execute("PRAGMA table_info(all_users)")
        cols = [r[1] for r in await cur.fetchall()]
        if "username" not in cols:
            await db.execute("ALTER TABLE all_users ADD COLUMN username TEXT")
    except:
        pass

    try:
        cur = await db.execute("PRAGMA table_info(schedule_updates)")
        cols = [r[1] for r in await cur.fetchall()]
        if "last_sent_date" not in cols:
            await db.execute("ALTER TABLE schedule_updates ADD COLUMN last_sent_date TEXT")
    except:
        pass

    await db.commit()


async def track_user(chat_id, fname, lname, uname):
    db = await get_db()
    cur = await db.execute("SELECT 1 FROM all_users WHERE chat_id=?", (chat_id,))
    if not await cur.fetchone():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute("INSERT INTO all_users VALUES (?,?,?,?,?)",
                         (chat_id, fname or "", lname or "", uname or "", now))
        await db.commit()

    today = datetime.now().strftime("%Y-%m-%d")
    await db.execute("INSERT INTO interactions VALUES (?,?)", (chat_id, today))
    await db.commit()


async def check_sub(chat_id):
    db = await get_db()
    cur = await db.execute("SELECT 1 FROM subscribers WHERE chat_id=?", (chat_id,))
    return await cur.fetchone() is not None


async def add_sub(chat_id):
    db = await get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await db.execute("INSERT OR IGNORE INTO subscribers VALUES (?,?)", (chat_id, now))
    await db.commit()


async def del_sub(chat_id):
    db = await get_db()
    await db.execute("DELETE FROM subscribers WHERE chat_id=?", (chat_id,))
    await db.commit()


async def get_ids(table):
    db = await get_db()
    cur = await db.execute(f"SELECT chat_id FROM {table}")
    return [r[0] for r in await cur.fetchall()]


async def get_hash_db(day):
    db = await get_db()
    cur = await db.execute("SELECT last_hash, last_sent_date FROM schedule_updates WHERE day=?", (day,))
    res = await cur.fetchone()
    return (res[0], res[1]) if res else (None, None)


async def save_hash(day, h, date):
    db = await get_db()
    await db.execute("INSERT OR REPLACE INTO schedule_updates VALUES (?,?,?)", (day, h, date))
    await db.commit()


async def get_stats():
    db = await get_db()
    cur = await db.execute("SELECT COUNT(*) FROM all_users")
    total = (await cur.fetchone())[0]
    cur = await db.execute("SELECT COUNT(*) FROM subscribers")
    subs = (await cur.fetchone())[0]
    today = datetime.now().strftime("%Y-%m-%d")
    cur = await db.execute(
        "SELECT COUNT(DISTINCT chat_id) FROM interactions WHERE interaction_date=?", (today,))
    daily = (await cur.fetchone())[0]
    return total, subs, daily


async def get_list(table_query):
    db = await get_db()
    cur = await db.execute(table_query)
    return [f"@{r[0]} ({r[1]} {r[2]})" for r in await cur.fetchall()]


# === PDF ===

async def download_pdf(fid):
    url = f"https://drive.google.com/uc?export=download&id={fid}"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/pdf"}
    for i in range(3):
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
                r = await c.get(url, headers=headers)
                if r.status_code == 429:
                    await asyncio.sleep(2 ** i)
                    continue
                r.raise_for_status()
                if r.content.startswith(b"%PDF"):
                    return r.content, None
                return None, "не pdf"
        except Exception as e:
            if i == 2:
                return None, str(e)
            await asyncio.sleep(2 ** i)
    return None, "не скачалось"


def make_images(pdf):
    doc = fitz.open(stream=pdf, filetype="pdf")
    imgs = []
    for i in range(len(doc)):
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        if img.width > 2000 or img.height > 2000:
            img.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        imgs.append(buf)
    doc.close()
    return imgs


def calc_hash(data):
    return hashlib.sha256(data).hexdigest()


def should_show_donate(uid):
    """Возвращает True каждые DONATE_EVERY просмотров"""
    view_count[uid] += 1
    return view_count[uid] % DONATE_EVERY == 0


def donate_link():
    return '❤️<a href="https://www.sberbank.com/sms/pbpn?requisiteNumber=79950614483">Поддержать работу бота</a>'


# === КЭШ ===

async def from_cache(day):
    if day in cache and time.time() - cache[day]['time'] < CACHE_TTL:
        return cache[day]['imgs']
    cache.pop(day, None)
    return None


async def to_cache(day, imgs, h):
    cache[day] = {'imgs': imgs, 'hash': h, 'time': time.time()}


# === МЕНЮ ===

def menu_main(admin=False):
    m = InlineKeyboardMarkup()
    m.row(InlineKeyboardButton("🗓️Расписание", callback_data="schedule"))
    m.row(InlineKeyboardButton("🔔Звонки", callback_data="bell"),
          InlineKeyboardButton("📬Рассылка", callback_data="mailing"))
    if admin:
        m.row(InlineKeyboardButton("📊Статистика", callback_data="admin_stats"))
    return m


def menu_days(show_stars=False):
    now = datetime.now(timezone(timedelta(hours=7)))
    wd = now.weekday()
    d_map = {0: "monday", 1: "tuesday", 2: "wednesday", 3: "thursday",
             4: "friday", 5: "saturday", 6: "monday"}
    curr = d_map.get(wd)

    days = [("Понедельник", "monday"), ("Вторник", "tuesday"), ("Среда", "wednesday"),
            ("Четверг", "thursday"), ("Пятница", "friday"), ("Суббота", "saturday")]
    m = InlineKeyboardMarkup()
    for i in range(0, 6, 3):
        row = []
        for n, k in days[i:i + 3]:
            st = "success" if k == curr else None
            row.append(MyButton(n, callback_data=f"day_{k}", style=st))
        m.add(*row)

    if show_stars:
        m.row(MyButton("⭐️Поддержать звёздами", callback_data="ask_stars"))
    m.row(MyButton("Меню", callback_data="main"))
    return m


def menu_calls():
    m = InlineKeyboardMarkup()
    m.add(InlineKeyboardButton("Понедельник", callback_data="monday_calls"),
          InlineKeyboardButton("Четверг", callback_data="thursday_calls"),
          InlineKeyboardButton("Другие дни", callback_data="other_calls"))
    m.row(InlineKeyboardButton("Меню", callback_data="main"))
    return m


def menu_mail(subbed):
    m = InlineKeyboardMarkup()
    if subbed:
        m.row(MyButton("Отписаться", callback_data="unsub", style="danger"))
    else:
        m.row(MyButton("Подписаться", callback_data="sub", style="success"))
    m.row(MyButton("Меню", callback_data="main"))
    return m


def menu_stats():
    m = InlineKeyboardMarkup()
    m.row(InlineKeyboardButton("👥Пользователи", callback_data="list_users"))
    m.row(InlineKeyboardButton("👥Подписчики", callback_data="list_subs"))
    m.row(InlineKeyboardButton("Меню", callback_data="main"))
    return m


def menu_pages(typ, pg, total):
    m = InlineKeyboardMarkup()
    btns = []
    if pg > 1:
        btns.append(InlineKeyboardButton("◀️", callback_data=f"{typ}_{pg - 1}"))
    if pg < total:
        btns.append(InlineKeyboardButton("▶️", callback_data=f"{typ}_{pg + 1}"))
    if btns:
        m.row(*btns)
    m.row(InlineKeyboardButton("📊Статистика", callback_data="admin_stats"))
    return m


# === РАССЫЛКА (авто, по расписанию) ===

async def send_to_user(uid, imgs, info, caption):
    async with send_limit:
        try:
            for j, img in enumerate(imgs):
                img.seek(0)
                copy = BytesIO(img.read())
                img.seek(0)
                cap = None
                markup = None
                if j == len(imgs) - 1:
                    cap = f"{caption}\n📎<a href=\"{info['link']}\">Ссылка на расписание</a>\n\n{donate_link()}"
                    markup = menu_days(show_stars=False)
                await bot.send_photo(uid, copy, caption=cap,
                                     parse_mode="HTML" if cap else None,
                                     reply_markup=markup)
        except Exception as e:
            print(f"err send {uid}: {e}")
            raise


async def mass_send(users, imgs, info, caption):
    results = await asyncio.gather(
        *[send_to_user(u, imgs, info, caption) for u in users],
        return_exceptions=True
    )
    err = sum(isinstance(r, Exception) for r in results)
    return len(results) - err, err


# === ПРОВЕРКА ОБНОВЛЕНИЙ ===

async def check_loop():
    cache.clear()
    while True:
        try:
            now = datetime.now(timezone(timedelta(hours=7)))
            if not (8 <= now.hour < 18):
                await asyncio.sleep(900)
                continue

            wd = now.weekday()
            # 0=mon, 1=tue, 2=wed, 3=thu, 4=fri, 5=sat, 6=sun
            # пятница проверяет субботу, суббота-воскресенье проверяют понедельник
            if wd == 4:  # пятница
                next_day = "saturday"
            elif wd == 5 or wd == 6:  # суббота или воскресенье
                next_day = "monday"
            else:
                # пн->вт, вт->ср, ср->чт, чт->пт
                next_day = {0: "tuesday", 1: "wednesday", 2: "thursday", 3: "friday"}.get(wd)

            if not next_day or next_day not in SCHEDULE_FILES:
                await asyncio.sleep(900)
                continue

            info = SCHEDULE_FILES[next_day]
            pdf, err = await download_pdf(info["id"])

            if not pdf:
                print(f"не скачал {next_day}: {err}")
                await asyncio.sleep(900)
                continue

            cur_hash = calc_hash(pdf)
            old_hash, last_sent_date = await get_hash_db(next_day)
            today = now.strftime("%Y-%m-%d")

            if cur_hash != old_hash:
                imgs = make_images(pdf)
                await to_cache(next_day, imgs, cur_hash)

                subs = await get_ids('subscribers')
                if subs:
                    ok, fail = await mass_send(subs, imgs, info, f"🔄Расписание на {info['name']}")
                    print(f"рассылка: {ok} ок, {fail} ошибок")

                await save_hash(next_day, cur_hash, today)
            else:
                if last_sent_date != today:
                    await save_hash(next_day, cur_hash, today)
                print(f"без изменений: {next_day}")

            await asyncio.sleep(900)

        except Exception as e:
            print(f"ошибка check: {e}")
            await asyncio.sleep(60)


# === КОМАНДЫ ===

@bot.message_handler(commands=["start"])
async def cmd_start(msg):
    u = msg.from_user
    await track_user(msg.chat.id, u.first_name, u.last_name, u.username)
    await bot.send_message(msg.chat.id, f"Привет, {u.first_name}!😊",
                           reply_markup=menu_main(msg.chat.id == ADMIN_ID))


@bot.message_handler(commands=["schedule"])
async def cmd_schedule(msg):
    u = msg.from_user
    await track_user(msg.chat.id, u.first_name, u.last_name, u.username)
    await bot.send_message(msg.chat.id, "Выберите день☺️", reply_markup=menu_days())


@bot.message_handler(commands=["bell"])
async def cmd_bell(msg):
    u = msg.from_user
    await track_user(msg.chat.id, u.first_name, u.last_name, u.username)
    await bot.send_message(msg.chat.id, "Информация о звонках🔔", reply_markup=menu_calls())


@bot.message_handler(commands=["mailing"])
async def cmd_mailing(msg):
    u = msg.from_user
    await track_user(msg.chat.id, u.first_name, u.last_name, u.username)
    subbed = await check_sub(msg.chat.id)
    txt = "Вы подписаны✅" if subbed else "Вы не подписаны"
    await bot.send_message(msg.chat.id, txt, reply_markup=menu_mail(subbed))


@bot.message_handler(commands=["stats"])
async def cmd_stats(msg):
    if msg.chat.id != ADMIN_ID:
        await bot.send_message(msg.chat.id, "нет доступа")
        return
    total, subs, daily = await get_stats()
    await bot.send_message(msg.chat.id,
                           f"📊Статистика:\n\nВсего: {total}\nПодписаны: {subs}\nСегодня: {daily}",
                           reply_markup=menu_stats())


# === /send — рассылка текста всем ===

@bot.message_handler(commands=["send"])
async def cmd_send(msg):
    if msg.chat.id != ADMIN_ID:
        return
    txt = msg.text.replace("/send", "").strip()
    if not txt:
        await bot.send_message(msg.chat.id, "Использование: /send твой текст")
        return
    users = await get_ids('all_users')
    states[msg.chat.id] = {"type": "send", "text": txt, "users": users}
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("✅Отправить", callback_data="send_yes"),
               InlineKeyboardButton("❌Отмена", callback_data="send_no"))
    await bot.send_message(msg.chat.id,
                           f"Отправить <b>{len(users)}</b> пользователям?\n\n{txt}",
                           parse_mode="HTML", reply_markup=markup)


# === КОЛБЕКИ ===

@bot.callback_query_handler(func=lambda c: c.data.startswith("day_"))
async def cb_day(call):
    day = call.data[4:]
    u = call.from_user
    await track_user(call.message.chat.id, u.first_name, u.last_name, u.username)

    if day not in SCHEDULE_FILES:
        await bot.answer_callback_query(call.id, "неизвестный день")
        return

    info = SCHEDULE_FILES[day]
    await bot.answer_callback_query(call.id, "Загружаю...")

    try:
        async with locks[day]:
            cached = await from_cache(day)
            if cached:
                imgs = cached
            else:
                pdf, err = await download_pdf(info["id"])
                if not pdf:
                    await bot.send_message(call.message.chat.id,
                                           f"❌Ошибка\n<a href=\"{info['link']}\">Открыть</a>",
                                           reply_markup=menu_days(), parse_mode="HTML")
                    return
                imgs = make_images(pdf)
                await to_cache(day, imgs, calc_hash(pdf))

        for j, img in enumerate(imgs):
            img.seek(0)
            copy = BytesIO(img.read())
            img.seek(0)
            cap = None
            markup = None
            if j == len(imgs) - 1:
                show_donate = should_show_donate(call.message.chat.id)
                cap = f"📚Расписание на {info['name']}\n📎<a href=\"{info['link']}\">Ссылка на расписание</a>" + \
                      (f"\n\n{donate_link()}" if show_donate else "")
                markup = menu_days(show_stars=show_donate)
            await bot.send_photo(call.message.chat.id, copy, caption=cap,
                                 parse_mode="HTML" if cap else None, reply_markup=markup)

    except Exception as e:
        await bot.answer_callback_query(call.id, "ошибка")
        print(f"err day: {e}")


@bot.callback_query_handler(func=lambda c: True)
async def cb_all(call):
    cid = call.message.chat.id
    u = call.from_user
    await track_user(cid, u.first_name, u.last_name, u.username)

    try:
        data = call.data

        if data == "admin_stats":
            if cid != ADMIN_ID:
                await bot.answer_callback_query(call.id, "нет")
                return
            total, subs, daily = await get_stats()
            await bot.edit_message_text(chat_id=cid, message_id=call.message.message_id,
                                        text=f"📊Статистика:\n\nВсего: {total}\nПодписаны: {subs}\nСегодня: {daily}",
                                        reply_markup=menu_stats())

        elif data.startswith("list_users"):
            if cid != ADMIN_ID:
                return
            pg = 1 if data == "list_users" else int(data.split("_")[-1])
            if data == "list_users":
                states[cid] = states.get(cid, {})
                query = """SELECT username, first_name, last_name FROM all_users
                           WHERE username IS NOT NULL AND username != ''
                           ORDER BY first_interaction_date DESC"""
                states[cid]["ul"] = await get_list(query)
            ul = states.get(cid, {}).get("ul", [])
            pages = (len(ul) + PAGE_SIZE - 1) // PAGE_SIZE or 1
            start = (pg - 1) * PAGE_SIZE
            items = ul[start:start + PAGE_SIZE]
            await bot.edit_message_text(chat_id=cid, message_id=call.message.message_id,
                                        text=f"👥Пользователи ({pg}/{pages}):\n\n" + "\n".join(items),
                                        reply_markup=menu_pages("list_users", pg, pages))

        elif data.startswith("list_subs"):
            if cid != ADMIN_ID:
                return
            pg = 1 if data == "list_subs" else int(data.split("_")[-1])
            if data == "list_subs":
                states[cid] = states.get(cid, {})
                query = """SELECT u.username, u.first_name, u.last_name FROM all_users u
                           INNER JOIN subscribers s ON u.chat_id = s.chat_id
                           WHERE u.username IS NOT NULL AND u.username != ''
                           ORDER BY s.joined_date DESC"""
                states[cid]["sl"] = await get_list(query)
            sl = states.get(cid, {}).get("sl", [])
            pages = (len(sl) + PAGE_SIZE - 1) // PAGE_SIZE or 1
            start = (pg - 1) * PAGE_SIZE
            items = sl[start:start + PAGE_SIZE]
            await bot.edit_message_text(chat_id=cid, message_id=call.message.message_id,
                                        text=f"👥Подписчики ({pg}/{pages}):\n\n" + "\n".join(items),
                                        reply_markup=menu_pages("list_subs", pg, pages))

        # /send
        elif data == "send_yes":
            if cid != ADMIN_ID:
                return
            d = states.get(cid, {})
            txt = d.get("text")
            users = d.get("users", [])
            await bot.edit_message_text(chat_id=cid, message_id=call.message.message_id, text="🔄...")
            ok = err = 0
            for i in range(0, len(users), 20):
                for uid in users[i:i + 20]:
                    try:
                        await bot.send_message(uid, txt, parse_mode="HTML")
                        ok += 1
                    except:
                        err += 1
                if i + 20 < len(users):
                    await asyncio.sleep(1)
            await bot.send_message(cid, f"✅Готово\nОтправлено: {ok}\nОшибок: {err}")
            states.pop(cid, None)

        elif data == "send_no":
            await bot.edit_message_text(chat_id=cid, message_id=call.message.message_id, text="❌Отменено")
            states.pop(cid, None)

        elif data == "schedule":
            await bot.edit_message_text(chat_id=cid, message_id=call.message.message_id,
                                        text="Выберите день☺️", reply_markup=menu_days())

        elif data == "mailing":
            subbed = await check_sub(cid)
            txt = "Вы подписаны✅" if subbed else "Вы не подписаны"
            await bot.edit_message_text(chat_id=cid, message_id=call.message.message_id,
                                        text=txt, reply_markup=menu_mail(subbed))

        elif data in CALLS:
            await bot.edit_message_text(chat_id=cid, message_id=call.message.message_id,
                                        text=CALLS[data], parse_mode="HTML", reply_markup=menu_calls())

        elif data == "bell":
            await bot.edit_message_text(chat_id=cid, message_id=call.message.message_id,
                                        text="Информация о звонках🔔", reply_markup=menu_calls())

        elif data == "sub":
            await add_sub(cid)
            await bot.edit_message_text(chat_id=cid, message_id=call.message.message_id,
                                        text="Вы подписаны✅", reply_markup=menu_mail(True))

        elif data == "unsub":
            await del_sub(cid)
            await bot.edit_message_text(chat_id=cid, message_id=call.message.message_id,
                                        text="Вы не подписаны", reply_markup=menu_mail(False))

        elif data == "main":
            admin = cid == ADMIN_ID
            try:
                await bot.edit_message_text(chat_id=cid, message_id=call.message.message_id,
                                            text="Выберите кнопку ниже😊", reply_markup=menu_main(admin))
            except:
                await bot.send_message(cid, "Выберите кнопку ниже😊", reply_markup=menu_main(admin))


        elif data == "ask_stars":
            states[cid] = {"type": "stars"}
            await bot.send_message(cid, "Введите количество ⭐️:")
            await bot.answer_callback_query(call.id)

    except Exception as e:
        await bot.answer_callback_query(call.id, "ошибка")
        print(f"cb err: {e}")


# === ОПЛАТА STARS ===

@bot.message_handler(func=lambda m: states.get(m.chat.id, {}).get("type") == "stars")
async def stars_amount(msg):
    try:
        amount = int(msg.text)
        if amount < 1 or amount > 10000:
            await bot.send_message(msg.chat.id, "Введите число от 1 до 10000.")
            return

        states.pop(msg.chat.id, None)

        await bot.send_invoice(
            msg.chat.id,
            title="Поддержать автора",
            description="Буду благодарен за поддержку⭐",
            invoice_payload="donate_stars",  # Внутренняя нагрузка для Telegram
            provider_token="",  # Для Telegram Stars оставляем пустым
            currency="XTR",  # Код валюты Telegram Stars
            prices=[LabeledPrice("Звёзды", amount)],
            start_parameter="donate"
        )
    except ValueError:
        await bot.send_message(msg.chat.id, "Введите число от 1 до 10000.")


@bot.pre_checkout_query_handler(func=lambda q: True)
async def checkout(q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)


@bot.message_handler(content_types=['successful_payment'])
async def got_payment(msg: Message):
    pmt = msg.successful_payment
    await bot.send_message(msg.chat.id, f"Спасибо за поддержку ({pmt.total_amount}⭐)!")
    print(f"Получен донат от {msg.from_user.username}: {pmt.total_amount} звезд")


# === ЗАПУСК ===
async def setup():
    await bot.set_my_commands([
        BotCommand("start", "🚀Старт"),
        BotCommand("schedule", "🗓️Расписание"),
        BotCommand("bell", "🔔Звонки"),
        BotCommand("mailing", "📬Рассылка"),
    ])


async def stats_log():
    while True:
        try:
            t, s, _ = await get_stats()
            print(f"stats: {s} subs, {t} total")
        except:
            pass
        await asyncio.sleep(3600)


async def main():
    await init_db()
    await setup()
    asyncio.create_task(check_loop())
    asyncio.create_task(stats_log())
    asyncio.create_task(keep_api_alive())
    print("Бот и система поддержания API запущены")
    await bot.polling(non_stop=True, skip_pending=True)


async def keep_api_alive():
    """Раз в 12 минут стучится в API на Render, чтобы тот не заснул."""
    # Замени на свою реальную ссылку от Render
    api_url = "https://utmiitx.onrender.com/health"

    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(api_url)
                if response.status_code == 200:
                    print(f"[ping] API жив: {datetime.now().strftime('%H:%M:%S')}")
                else:
                    print(f"[ping] Ошибка API: {response.status_code}")
        except Exception as e:
            print(f"[ping] Не удалось достучаться: {e}")

        # Спим 12 минут (720 секунд)
        await asyncio.sleep(720)


if __name__ == "__main__":
    if os.name == "nt":
        os.system("chcp 65001 > nul")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nстоп")
    except Exception as e:
        print(f"ошибка: {e}")
