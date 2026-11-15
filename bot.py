import asyncio
import logging
import os
from collections import defaultdict, deque
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from gigachat import GigaChat

from prompt import CRISIS_TEXT, CRISIS_TRIGGERS, HELP_TEXT, SYSTEM_PROMPT

BOT_TOKEN = os.getenv("BOT_TOKEN") or "9121159502:AAFqGYXs1n-IRyM5kDp-S1n46ZA3kf7MN14"
GIGACHAT_KEY = os.getenv("GIGACHAT_KEY") or "MDFhMWRmNjctMTMzYS03Y2E4LWE1YmYtYjQ3OTdkMzQ0NWVmOjkyY2E4MjdiLThjMjktNDI2ZC1iMmExLTRiNGQ2NTg0YzhiMg=="

GIGACHAT_MODEL = "GigaChat-3-Ultra"
HISTORY_LIMIT = 20
ALLOWED_USERS = set()

if "СЮДА" in BOT_TOKEN or "СЮДА" in GIGACHAT_KEY:
    raise SystemExit("Вставь BOT_TOKEN и GIGACHAT_KEY в начале файла или в переменные окружения")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

CERT = Path(__file__).with_name("Russian_Trusted_Root_CA.cer")
if CERT.exists():
    giga = GigaChat(credentials=GIGACHAT_KEY, scope="GIGACHAT_API_PERS", model=GIGACHAT_MODEL,
                    ca_bundle_file=str(CERT), timeout=60)
else:
    logging.warning("Не найден сертификат — проверка SSL для GigaChat отключена")
    giga = GigaChat(credentials=GIGACHAT_KEY, scope="GIGACHAT_API_PERS", model=GIGACHAT_MODEL,
                    verify_ssl_certs=False, timeout=60)

giga_slot = asyncio.Semaphore(1)
history: dict[int, deque] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))
locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
user_lang: dict[int, str] = defaultdict(lambda: "ru")
TG_LIMIT = 4096

LANG_PROMPT = "Выбери язык / Choose language / Chọn ngôn ngữ / 选择语言："

TEXTS = {
    "ru": {
        "welcome": "Привет, {name}! Я «Опора» — бот поддержки для студентов и школьников.\n\nРасскажи, что тебя беспокоит: учёба, сессия, стресс или одиночество. Я выслушаю и помогу разобраться.\n\nВажно: я ИИ, а не врач. Если очень плохо — нажми /help.\nНе пиши ФИО и адрес.\n\n/help — помощь | /reset — заново | /lang — язык",
        "help": HELP_TEXT,
        "reset": "Контекст очищен, начинаем заново.",
        "crisis": CRISIS_TEXT,
        "denied": "Доступ к боту закрыт.",
        "error": "Не могу ответить сейчас ({err}), попробуй через минуту. Срочная помощь: /help.",
        "other": "Пока я понимаю только текст.",
        "lang_set": "Язык изменён на русский 🇷🇺",
        "rule": "\n\nВАЖНО: Отвечай пользователю строго на русском языке."
    },
    "en": {
        "welcome": "Hi, {name}! I'm Opora — an AI support companion for students.\n\nShare what's on your mind: exams, burnout, stress, or loneliness. I'm here to listen.\n\nImportant: I am an AI, not a doctor. For crisis contacts, tap /help.\nDo not share personal data.\n\n/help — crisis help | /reset — restart | /lang — language",
        "help": "🆘 Crisis & Support Contacts:\n• Worldwide free helplines: https://findahelpline.com\n• Emergency in Russia: 112 or +7 (495) 989-50-50 (24/7)\n• Crisis Text Line (US/UK/CA): Text HOME to 741741 or 85258",
        "reset": "Conversation cleared. Let's start fresh.",
        "crisis": "⚠️ Please reach out for real support right now:\n• Worldwide: https://findahelpline.com\n• Russia: 112 or +7 (495) 989-50-50",
        "denied": "Access restricted.",
        "error": "Can't reply right now ({err}), try again in a minute. Urgent help: /help.",
        "other": "I only understand text messages.",
        "lang_set": "Language switched to English 🇬🇧",
        "rule": "\n\nIMPORTANT: Always reply to the user strictly in English."
    },
    "vi": {
        "welcome": "Xin chào, {name}! Mình là Opora — trợ lý AI hỗ trợ tinh thần cho học sinh, sinh viên.\n\nHãy chia sẻ điều làm bạn bận tâm: học tập, thi cử, căng thẳng hay cô đơn. Mình luôn lắng nghe.\n\nLưu ý: Mình là AI, không phải bác sĩ. Nếu khẩn cấp hãy nhấn /help.\nKhông gửi thông tin cá nhân.\n\n/help — hỗ trợ | /reset — làm mới | /lang — ngôn ngữ",
        "help": "🆘 Liên hệ hỗ trợ tâm lý khẩn cấp:\n• Tại Việt Nam (24/7 miễn phí): 1800 599 920 hoặc 111\n• Tại Nga (cho du học sinh): 112 hoặc +7 (495) 989-50-50\n• Quốc tế: https://findahelpline.com",
        "reset": "Đã xóa lịch sử trò chuyện. Bắt đầu lại nhé.",
        "crisis": "⚠️ Bạn không đơn độc, hãy liên hệ hỗ trợ ngay:\n• Việt Nam: 1800 599 920 hoặc 111\n• Nga: 112 hoặc +7 (495) 989-50-50\n• Quốc tế: https://findahelpline.com",
        "denied": "Quyền truy cập bị hạn chế.",
        "error": "Không thể trả lời lúc này ({err}), thử lại sau ít phút. Hỗ trợ gấp: /help.",
        "other": "Mình chỉ hiểu tin nhắn văn bản.",
        "lang_set": "Đã chuyển sang Tiếng Việt 🇻🇳",
        "rule": "\n\nQUAN TRỌNG: Luôn trả lời hoàn toàn bằng tiếng Việt (Vietnamese)."
    },
    "zh": {
        "welcome": "你好，{name}！我是「Opora」——专为学生打造的心理支持 AI 助手。\n\n你可以倾诉学业压力、考试焦虑或孤独感，我会耐心倾听。\n\n重要提示：我是 AI，非专业医生。紧急情况请点 /help。\n请勿发送个人隐私信息。\n\n/help — 心理援助 | /reset — 重新开始 | /lang — 切换语言",
        "help": "🆘 紧急心理援助热线：\n• 中国心理援助热线：12356 或 400-161-9995（24小时）\n• 俄罗斯紧急求助（在俄留学生）：112 或 +7 (495) 989-50-50\n• 全球免费援助：https://findahelpline.com",
        "reset": "对话已清空，重新开始吧。",
        "crisis": "⚠️ 请及时寻求专业帮助：\n• 中国热线：12356 或 400-161-9995\n• 俄罗斯求助：112 或 +7 (495) 989-50-50\n• 全球查询：https://findahelpline.com",
        "denied": "访问受限。",
        "error": "暂时无法回复（{err}），请稍后再试。紧急帮助：/help。",
        "other": "目前仅支持文字消息。",
        "lang_set": "语言已切换为中文 🇨🇳",
        "rule": "\n\n重要指令：请务必全程使用简体中文回复用户。"
    }
}

EXTRA_TRIGGERS = [
    "suicide", "kill myself", "end my life", "don't want to live", "self harm", "want to die",
    "tự tử", "tự sát", "muốn chết", "không muốn sống",
    "自杀", "不想活", "想死", "轻生", "自残"
]

def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang:ru"),
         InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang:en")],
        [InlineKeyboardButton(text="🇻🇳 Tiếng Việt", callback_data="set_lang:vi"),
         InlineKeyboardButton(text="🇨🇳 中文", callback_data="set_lang:zh")]
    ])

def allowed(message: Message) -> bool:
    return not ALLOWED_USERS or message.from_user.id in ALLOWED_USERS

async def keep_typing(chat_id: int, stop: asyncio.Event):
    while not stop.is_set():
        await bot.send_chat_action(chat_id, ChatAction.TYPING)
        try:
            await asyncio.wait_for(stop.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass

async def ask_llm(user_id: int, text: str) -> str:
    lang = user_lang[user_id]
    history[user_id].append({"role": "user", "content": text})
    sys_prompt = SYSTEM_PROMPT + TEXTS[lang]["rule"]
    messages = [{"role": "system", "content": sys_prompt}, *history[user_id]]
    async with giga_slot:
        resp = await giga.achat({"messages": messages, "temperature": 0.7})
    answer = resp.choices[0].message.content or "(пустой ответ)"
    history[user_id].append({"role": "assistant", "content": answer})
    return answer

def is_crisis(text: str) -> bool:
    t = text.lower().replace("ё", "е")
    return any(w.replace("ё", "е") in t for w in CRISIS_TRIGGERS) or any(w in t for w in EXTRA_TRIGGERS)

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(LANG_PROMPT, reply_markup=lang_keyboard())

@dp.message(Command("lang"))
async def cmd_lang(message: Message):
    await message.answer(LANG_PROMPT, reply_markup=lang_keyboard())

@dp.callback_query(F.data.startswith("set_lang:"))
async def on_lang_select(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    if lang not in TEXTS:
        lang = "ru"
    user_lang[callback.from_user.id] = lang
    await callback.answer()
    await callback.message.edit_text(TEXTS[lang]["lang_set"])
    await callback.message.answer(TEXTS[lang]["welcome"].format(name=callback.from_user.first_name))

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(TEXTS[user_lang[message.from_user.id]]["help"])

@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    user_id = message.from_user.id
    history.pop(user_id, None)
    await message.answer(TEXTS[user_lang[user_id]]["reset"])

@dp.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"Your ID: {message.from_user.id}")

@dp.message(F.text)
async def on_text(message: Message):
    lang = user_lang[message.from_user.id]
    if not allowed(message):
        await message.answer(TEXTS[lang]["denied"])
        return
    user_id = message.from_user.id
    if is_crisis(message.text):
        await message.answer(TEXTS[lang]["crisis"])
    async with locks[user_id]:
        stop = asyncio.Event()
        typing = asyncio.create_task(keep_typing(message.chat.id, stop))
        try:
            answer = await ask_llm(user_id, message.text)
        except Exception as e:
            logging.exception("Ошибка LLM")
            if history[user_id] and history[user_id][-1]["role"] == "user":
                history[user_id].pop()
            await message.answer(TEXTS[lang]["error"].format(err=type(e).__name__))
            return
        finally:
            stop.set()
            await typing
    for i in range(0, len(answer), TG_LIMIT):
        await message.answer(answer[i : i + TG_LIMIT])

@dp.message()
async def on_other(message: Message):
    await message.answer(TEXTS[user_lang[message.from_user.id]]["other"])

async def main():
    logging.info("Бот «Опора» запущен, модель: %s", GIGACHAT_MODEL)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
