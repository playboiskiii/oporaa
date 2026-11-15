"""
«Опора» — Telegram-бот психологической поддержки для учащихся на нейросети GigaChat (Сбер).
Вставь 2 ключа ниже и запусти: python bot.py (или run.bat)
"""
import asyncio
import logging
import os
from collections import defaultdict, deque
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from gigachat import GigaChat

from prompt import CRISIS_TEXT, CRISIS_TRIGGERS, HELP_TEXT, SYSTEM_PROMPT

# ================== ВСТАВЬ СВОИ КЛЮЧИ ==================
BOT_TOKEN = os.getenv("BOT_TOKEN") or "9121159502:AAFqGYXs1n-IRyM5kDp-S1n46ZA3kf7MN14"
# «Ключ авторизации» (Authorization key) из личного кабинета developers.sber.ru
GIGACHAT_KEY = os.getenv("GIGACHAT_KEY") or "MDFhMWRmNjctMTMzYS03Y2E4LWE1YmYtYjQ3OTdkMzQ0NWVmOjkyY2E4MjdiLThjMjktNDI2ZC1iMmExLTRiNGQ2NTg0YzhiMg=="
# =======================================================

GIGACHAT_MODEL = "GigaChat"  # можно "GigaChat-Pro" / "GigaChat-Max", если они есть в твоём тарифе
HISTORY_LIMIT = 20           # сколько последних сообщений помнить
ALLOWED_USERS = set()        # например {123456789} — тогда ботом сможешь пользоваться только ты (id узнать: /id)
# Характер агента и кризисные контакты — в файле prompt.py

if "СЮДА" in BOT_TOKEN or "СЮДА" in GIGACHAT_KEY:
    raise SystemExit("Открой bot.py и вставь BOT_TOKEN и GIGACHAT_KEY в начале файла")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Сертификат НУЦ Минцифры: если файл лежит рядом с bot.py — соединение проверяется полностью.
CERT = Path(__file__).with_name("Russian_Trusted_Root_CA")
if CERT.exists():
    giga = GigaChat(credentials=GIGACHAT_KEY, scope="GIGACHAT_API_PERS", model=GIGACHAT_MODEL,
                    ca_bundle_file=str(CERT), timeout=60)
else:
    logging.warning("Не найден russian_trusted_root_ca.cer — проверка SSL для GigaChat отключена (см. README)")
    giga = GigaChat(credentials=GIGACHAT_KEY, scope="GIGACHAT_API_PERS", model=GIGACHAT_MODEL,
                    verify_ssl_certs=False, timeout=60)

# У физлиц GigaChat обрабатывает только 1 запрос за раз — ставим остальных в очередь
giga_slot = asyncio.Semaphore(1)

# История диалога для каждого пользователя (хранится в памяти, сбрасывается при перезапуске)
history: dict[int, deque] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))
# Чтобы один пользователь не отправлял несколько запросов параллельно
locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

TG_LIMIT = 4096  # максимальная длина сообщения в Telegram


def allowed(message: Message) -> bool:
    return not ALLOWED_USERS or message.from_user.id in ALLOWED_USERS


async def keep_typing(chat_id: int, stop: asyncio.Event):
    """Показывает «печатает...», пока нейронка думает."""
    while not stop.is_set():
        await bot.send_chat_action(chat_id, ChatAction.TYPING)
        try:
            await asyncio.wait_for(stop.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass


async def ask_llm(user_id: int, text: str) -> str:
    history[user_id].append({"role": "user", "content": text})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history[user_id]]
    async with giga_slot:
        resp = await giga.achat({"messages": messages, "temperature": 0.7})
    answer = resp.choices[0].message.content or "(пустой ответ)"
    history[user_id].append({"role": "assistant", "content": answer})
    return answer


def is_crisis(text: str) -> bool:
    t = text.lower().replace("ё", "е")
    return any(w.replace("ё", "е") in t for w in CRISIS_TRIGGERS)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        f"Привет, {message.from_user.first_name}! Я «Опора» — бот поддержки для школьников и студентов.\n\n"
        "Можешь рассказать, что тебя беспокоит: учёба, сессия, стресс, отношения, одиночество — что угодно. "
        "Я выслушаю и помогу разобраться.\n\n"
        "Важно: я ИИ, а не психолог и не врач. Если тебе очень плохо — нажми /help, там телефоны живых специалистов.\n"
        "Не пиши мне своё ФИО, адрес и другие личные данные.\n\n"
        "/help — куда обратиться за помощью\n"
        "/reset — начать разговор заново"
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT)


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    history.pop(message.from_user.id, None)
    await message.answer("Контекст очищен, начинаем заново.")


@dp.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"Твой id: {message.from_user.id}")


@dp.message(F.text)
async def on_text(message: Message):
    if not allowed(message):
        await message.answer("Доступ к боту закрыт.")
        return

    user_id = message.from_user.id
    if is_crisis(message.text):
        # Кризисные контакты отправляются сразу, не дожидаясь нейросети
        await message.answer(CRISIS_TEXT)
    async with locks[user_id]:
        stop = asyncio.Event()
        typing = asyncio.create_task(keep_typing(message.chat.id, stop))
        try:
            answer = await ask_llm(user_id, message.text)
        except Exception as e:
            logging.exception("Ошибка LLM")
            # убираем вопрос из истории, чтобы не сломать контекст
            if history[user_id] and history[user_id][-1]["role"] == "user":
                history[user_id].pop()
            await message.answer(f"Я сейчас не могу ответить (ошибка {type(e).__name__}), попробуй через минуту. "
                                 "Если тебе срочно нужна помощь — нажми /help.")
            return
        finally:
            stop.set()
            await typing

    for i in range(0, len(answer), TG_LIMIT):
        await message.answer(answer[i : i + TG_LIMIT])


@dp.message()
async def on_other(message: Message):
    await message.answer("Пока я понимаю только текст.")


async def main():
    logging.info("Бот «Опора» запущен, модель: %s", GIGACHAT_MODEL)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
