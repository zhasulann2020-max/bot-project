import asyncio
import re
import os
import json
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove


# =========================================================
# НАСТРОЙКИ
# =========================================================
TOKEN = "8726002003:AAHW-FgK_cB2qJZITqF7hq2GmSB9x-BC14s"
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1giJSaRtsmMDRNEKrMoUl-IItt0PueEiVQfPN2CsM8mU/edit?usp=sharing"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

BASE_DIR = Path(__file__).resolve().parent
CREDS_FILE = BASE_DIR / "creds.json"


# =========================================================
# GOOGLE SHEETS
# =========================================================

creds_json = os.getenv("CREDS_JSON")

if creds_json:
    creds = Credentials.from_service_account_info(
        json.loads(creds_json),
        scopes=SCOPES
    )
else:
    creds = Credentials.from_service_account_file(
        str(CREDS_FILE),
        scopes=SCOPES
    )
client = gspread.authorize(creds)
sheet = client.open_by_url(SPREADSHEET_URL).sheet1


# =========================================================
# TELEGRAM BOT
# =========================================================
bot = Bot(token=TOKEN)
dp = Dispatcher()

user_data = {}


# =========================================================
# СПРАВОЧНИКИ
# =========================================================
DIRECTION_OPTIONS = [
    "Өнер / Искусство",
    "Мәдениет / Культура",
    "Спорт / Спорт",
    "Ғылым / Наука",
    "Денсаулық сақтау / Здравоохранение",
    "Білім беру / Образование",
    "Басқа / Другое",
]

EVENT_SCOPE_OPTIONS = [
    "Халықаралық / Международное",
    "Қазақстанда / В Казахстане",
]

EVENT_FORMAT_OPTIONS = [
    "Байқау / Конкурс",
    "Форум / Форум",
    "Фестиваль / Фестиваль",
    "Конференция / Конференция",
    "Оқу бағдарламасы / Обучающая программа",
    "Басқа / Другое",
]

HAS_DOCS_OPTIONS = [
    "Иә / Да",
    "Жоқ / Нет",
]

EXPENSE_OPTIONS = [
    "Жол ақысы / Проезд",
    "Тұру / Проживание",
    "Тіркеу жарнасы / Организационный взнос",
    "Бірнеше нұсқа / Несколько вариантов",
]


# =========================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================================================
def make_two_column_keyboard(options: list[str]) -> ReplyKeyboardMarkup:
    rows = []
    row = []
    for option in options:
        row.append(KeyboardButton(text=option))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def make_start_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="БАСТАУ / НАЧАТЬ")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def normalize_phone(phone: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", phone)

    if cleaned.startswith("8") and len(cleaned) == 11:
        cleaned = "+7" + cleaned[1:]

    if cleaned.startswith("7") and len(cleaned) == 11:
        cleaned = "+" + cleaned

    return cleaned


def is_valid_phone(phone: str) -> bool:
    cleaned = normalize_phone(phone)
    return bool(re.fullmatch(r"\+7\d{10}", cleaned))


def normalize_date_range(text: str) -> str:
    return text.strip().replace("—", "-").replace("–", "-").replace(" - ", "-").replace(" ", "")


def is_valid_date_range(text: str) -> bool:
    value = normalize_date_range(text)
    parts = value.split("-")
    if len(parts) != 2:
        return False

    try:
        start_date = datetime.strptime(parts[0], "%d.%m.%Y")
        end_date = datetime.strptime(parts[1], "%d.%m.%Y")
        return start_date <= end_date
    except ValueError:
        return False


def is_valid_link(text: str) -> bool:
    low = text.strip().lower()
    if low in ["жоқ", "нет", "no"]:
        return True
    return bool(re.match(r"^https?://", text.strip()))


def save_to_google_sheet(user_id: int, data: dict, message: types.Message):
    username = message.from_user.username if message.from_user.username else ""

    row = [
        str(user_id),
        username,
        data.get("full_name", ""),
        data.get("phone", ""),
        data.get("direction", ""),
        data.get("event_scope", ""),
        data.get("event_format", ""),
        data.get("trip_purpose", ""),
        data.get("trip_dates", ""),
        data.get("city_country", ""),
        data.get("event_link", ""),
        data.get("has_documents", ""),
        ", ".join(data.get("document_file_ids", [])),
        data.get("requested_expenses", ""),
        data.get("support_reason", ""),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]

    sheet.append_row(row, value_input_option="USER_ENTERED")


async def send_text(
    message: types.Message,
    text: str,
    reply_markup=None,
):
    await bot.send_message(
        chat_id=message.chat.id,
        text=text,
        reply_markup=reply_markup,
    )


async def finish_application(message: types.Message, user_id: int):
    try:
        save_to_google_sheet(user_id, user_data[user_id], message)
        await send_text(
            message,
            "Рақмет! Өтінім қабылданды ✅\n\n"
            "Спасибо! Ваша заявка принята ✅\n\n"
            "Жақын арада жоба менеджері сізбен хабарласады.\n"
            "В ближайшее время с вами свяжется менеджер проекта.",
            reply_markup=ReplyKeyboardRemove(),
        )
        print("Saved:", user_data[user_id])
    except Exception as e:
        await send_text(
            message,
            "Жауаптарды сақтау кезінде қате шықты.\n"
            "Произошла ошибка при сохранении данных.",
            reply_markup=ReplyKeyboardRemove(),
        )
        print("Google Sheets error:", e)

    user_data.pop(user_id, None)


async def ask_direction(message: types.Message, user_id: int):
    user_data[user_id]["step"] = "direction"
    await send_text(
        message,
        "Қай бағыт бойынша өтінім беріп жатырсыз?\n"
        "По какому направлению вы подаете заявку?",
        reply_markup=make_two_column_keyboard(DIRECTION_OPTIONS),
    )


async def ask_event_scope(message: types.Message, user_id: int):
    user_data[user_id]["step"] = "event_scope"
    await send_text(
        message,
        "Іс-шара халықаралық па, әлде Қазақстанда өтеді ме?\n"
        "Мероприятие международное или проходит в Казахстане?",
        reply_markup=make_two_column_keyboard(EVENT_SCOPE_OPTIONS),
    )


async def ask_event_format(message: types.Message, user_id: int):
    user_data[user_id]["step"] = "event_format"
    await send_text(
        message,
        "Іс-шараның форматы қандай?\n"
        "Какой формат мероприятия?",
        reply_markup=make_two_column_keyboard(EVENT_FORMAT_OPTIONS),
    )


async def ask_trip_purpose(message: types.Message, user_id: int):
    user_data[user_id]["step"] = "trip_purpose"
    await send_text(
        message,
        "Сапардың мақсатын жазыңыз:\n"
        "(мысалы: қатысу, сөз сөйлеу, оқу, тәжірибе алмасу)\n\n"
        "Укажите цель поездки:\n"
        "(например: участие, выступление, обучение, обмен опытом)",
        reply_markup=ReplyKeyboardRemove(),
    )


async def ask_trip_dates(message: types.Message, user_id: int):
    user_data[user_id]["step"] = "trip_dates"
    await send_text(
        message,
        "Сапар күндерін көрсетіңіз:\n"
        "(мысалы: 15.07.2026-20.07.2026)\n\n"
        "Укажите даты поездки:\n"
        "(например: 15.07.2026-20.07.2026)"
    )


async def ask_city_country(message: types.Message, user_id: int):
    user_data[user_id]["step"] = "city_country"
    await send_text(
        message,
        "Іс-шара өтетін қала мен елді көрсетіңіз:\n"
        "Укажите город и страну проведения мероприятия:"
    )


async def ask_event_link(message: types.Message, user_id: int):
    user_data[user_id]["step"] = "event_link"
    await send_text(
        message,
        'Іс-шараның сілтемесін жіберіңіз:\n(егер жоқ болса, "жоқ" деп жазыңыз)\n\n'
        'Отправьте ссылку на страницу мероприятия:\n(если нет, напишите "нет")'
    )


async def ask_has_documents(message: types.Message, user_id: int):
    user_data[user_id]["step"] = "has_documents"
    await send_text(
        message,
        "Растайтын құжаттарыңыз бар ма?\n"
        "(шақырту, тіркеу және т.б.)\n\n"
        "Есть ли у вас подтверждающие документы?\n"
        "(приглашение, регистрация и т.д.)",
        reply_markup=make_two_column_keyboard(HAS_DOCS_OPTIONS),
    )


async def ask_upload_documents(message: types.Message, user_id: int):
    user_data[user_id]["step"] = "upload_documents"
    user_data[user_id]["document_file_ids"] = []
    await send_text(
        message,
        "Егер бар болса, растайтын құжаттарды тіркеңіз:\n"
        "(PDF, фото немесе скриншот)\n\n"
        "Если есть, прикрепите подтверждающие документы:\n"
        "(PDF, фото или скриншоты)\n\n"
        "Бірнеше файл жіберуге болады. Болған соң 'Дайын' деп жазыңыз.\n"
        "Можно отправить несколько файлов. Когда закончите, напишите 'Дайын' или 'Готово'.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def ask_requested_expenses(message: types.Message, user_id: int):
    user_data[user_id]["step"] = "requested_expenses"
    await send_text(
        message,
        "Жол гранты аясында қандай шығындарды сұрайсыз?\n"
        "Какие расходы вы запрашиваете в рамках дорожного гранта?",
        reply_markup=make_two_column_keyboard(EXPENSE_OPTIONS),
    )


async def ask_support_reason(message: types.Message, user_id: int):
    user_data[user_id]["step"] = "support_reason"
    await send_text(
        message,
        "Неліктен дәл сіздің сапарыңыз қолдауға лайық?\n"
        "(қысқаша, 2-5 сөйлем)\n\n"
        "Почему именно ваша поездка должна быть поддержана?\n"
        "(кратко, 2-5 предложений)",
        reply_markup=ReplyKeyboardRemove(),
    )


# =========================================================
# START
# =========================================================
@dp.message(CommandStart())
async def start(message: types.Message):
    user_id = message.from_user.id
    user_data[user_id] = {
        "step": "start_button",
        "document_file_ids": [],
    }

    await send_text(
        message,
        "Құрметті қатысушы!\n\n"
        "«Atyrau Youth Connect» жобасына қош келдіңіз.\n\n"
        "Уважаемый участник!\n\n"
        "Добро пожаловать в проект «Atyrau Youth Connect».\n\n"
        "Өтінімді бастау үшін төмендегі батырманы басыңыз.\n"
        "Чтобы начать подачу заявки, нажмите кнопку ниже.",
        reply_markup=make_start_keyboard(),
    )


# =========================================================
# ДОКУМЕНТЫ
# =========================================================
@dp.message(F.document)
async def handle_document(message: types.Message):
    user_id = message.from_user.id

    if user_id not in user_data:
        await send_text(message, "Өтінімді бастау үшін /start жазыңыз\nДля начала отправьте /start")
        return

    if user_data[user_id].get("step") != "upload_documents":
        await send_text(message, "Қазір құжат жіберу кезеңі емес.\nСейчас не этап загрузки документов.")
        return

    file_id = message.document.file_id
    user_data[user_id].setdefault("document_file_ids", []).append(file_id)

    await send_text(
        message,
        "Құжат қабылданды ✅\nДокумент принят ✅\n\n"
        "Тағы файл жіберуге болады немесе 'Дайын' / 'Готово' деп жазыңыз."
    )


@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id

    if user_id not in user_data:
        await send_text(message, "Өтінімді бастау үшін /start жазыңыз\nДля начала отправьте /start")
        return

    if user_data[user_id].get("step") != "upload_documents":
        await send_text(message, "Қазір құжат жіберу кезеңі емес.\nСейчас не этап загрузки документов.")
        return

    file_id = message.photo[-1].file_id
    user_data[user_id].setdefault("document_file_ids", []).append(file_id)

    await send_text(
        message,
        "Сурет қабылданды ✅\nИзображение принято ✅\n\n"
        "Тағы файл жіберуге болады немесе 'Дайын' / 'Готово' деп жазыңыз."
    )


# =========================================================
# ОСНОВНАЯ ЛОГИКА
# =========================================================
@dp.message()
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if user_id not in user_data:
        await send_text(message, "Өтінімді бастау үшін /start жазыңыз\nДля начала отправьте /start")
        return

    step = user_data[user_id].get("step")

    if step == "start_button":
        if text != "БАСТАУ / НАЧАТЬ":
            await send_text(
                message,
                "Өтінімді бастау үшін 'БАСТАУ / НАЧАТЬ' батырмасын басыңыз.\n"
                "Чтобы начать заявку, нажмите кнопку 'БАСТАУ / НАЧАТЬ'."
            )
            return

        user_data[user_id]["step"] = "full_name"
        await send_text(
            message,
            "Аты-жөніңізді жазыңыз:\n"
            "Укажите ваши ФИО:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if step == "full_name":
        if len(text) < 5:
            await send_text(
                message,
                "Аты-жөніңізді толық жазыңыз.\n"
                "Пожалуйста, укажите ФИО полностью."
            )
            return

        user_data[user_id]["full_name"] = text
        user_data[user_id]["step"] = "phone"
        await send_text(
            message,
            "Телефон нөміріңізді жазыңыз:\n"
            "Укажите номер телефона:\n\n"
            "Мысалы / Например:\n"
            "+77001234567\n"
            "или\n"
            "87001234567"
        )
        return

    if step == "phone":
        if not is_valid_phone(text):
            await send_text(
                message,
                "Телефон нөмірі дұрыс форматта емес.\n"
                "Номер телефона указан в неверном формате.\n\n"
                "Дұрыс формат / Правильный формат:\n"
                "+77001234567\n"
                "или\n"
                "87001234567"
            )
            return

        user_data[user_id]["phone"] = normalize_phone(text)
        await ask_direction(message, user_id)
        return

    if step == "direction":
        if text == "Басқа / Другое":
            user_data[user_id]["step"] = "direction_other"
            await send_text(
                message,
                "Қажетті бағытты өзіңіз жазыңыз:\n"
                "Напишите нужное направление:"
            )
            return

        if text not in DIRECTION_OPTIONS:
            await send_text(
                message,
                "Төмендегі нұсқалардың бірін таңдаңыз.\n"
                "Пожалуйста, выберите один из предложенных вариантов."
            )
            return

        user_data[user_id]["direction"] = text
        await ask_event_scope(message, user_id)
        return

    if step == "direction_other":
        if len(text) < 2:
            await send_text(
                message,
                "Бағытты нақтырақ жазыңыз.\n"
                "Пожалуйста, укажите направление точнее."
            )
            return

        user_data[user_id]["direction"] = text
        await ask_event_scope(message, user_id)
        return

    if step == "event_scope":
        if text not in EVENT_SCOPE_OPTIONS:
            await send_text(
                message,
                "Төмендегі нұсқалардың бірін таңдаңыз.\n"
                "Пожалуйста, выберите один из предложенных вариантов."
            )
            return

        user_data[user_id]["event_scope"] = text
        await ask_event_format(message, user_id)
        return

    if step == "event_format":
        if text == "Басқа / Другое":
            user_data[user_id]["step"] = "event_format_other"
            await send_text(
                message,
                "Іс-шара форматын өзіңіз жазыңыз:\n"
                "Напишите формат мероприятия:"
            )
            return

        if text not in EVENT_FORMAT_OPTIONS:
            await send_text(
                message,
                "Төмендегі нұсқалардың бірін таңдаңыз.\n"
                "Пожалуйста, выберите один из предложенных вариантов."
            )
            return

        user_data[user_id]["event_format"] = text
        await ask_trip_purpose(message, user_id)
        return

    if step == "event_format_other":
        if len(text) < 2:
            await send_text(
                message,
                "Форматты нақтырақ жазыңыз.\n"
                "Пожалуйста, укажите формат точнее."
            )
            return

        user_data[user_id]["event_format"] = text
        await ask_trip_purpose(message, user_id)
        return

    if step == "trip_purpose":
        if len(text) < 5:
            await send_text(
                message,
                "Мақсатты толығырақ жазыңыз.\n"
                "Пожалуйста, опишите цель подробнее."
            )
            return

        user_data[user_id]["trip_purpose"] = text
        await ask_trip_dates(message, user_id)
        return

    if step == "trip_dates":
        if not is_valid_date_range(text):
            await send_text(
                message,
                "Күндерді дұрыс форматта жазыңыз.\n"
                "Укажите даты в правильном формате.\n\n"
                "Мысалы / Например:\n"
                "15.07.2026-20.07.2026"
            )
            return

        user_data[user_id]["trip_dates"] = normalize_date_range(text)
        await ask_city_country(message, user_id)
        return

    if step == "city_country":
        if len(text) < 3:
            await send_text(
                message,
                "Қала мен елді толық жазыңыз.\n"
                "Пожалуйста, укажите город и страну полностью."
            )
            return

        user_data[user_id]["city_country"] = text
        await ask_event_link(message, user_id)
        return

    if step == "event_link":
        if not is_valid_link(text):
            await send_text(
                message,
                'Сілтеме http:// немесе https:// арқылы басталуы керек.\n'
                'Ссылка должна начинаться с http:// или https://\n\n'
                'Егер сілтеме жоқ болса, "жоқ" немесе "нет" деп жазыңыз.'
            )
            return

        user_data[user_id]["event_link"] = text
        await ask_has_documents(message, user_id)
        return

    if step == "has_documents":
        if text not in HAS_DOCS_OPTIONS:
            await send_text(
                message,
                "Төмендегі нұсқалардың бірін таңдаңыз.\n"
                "Пожалуйста, выберите один из предложенных вариантов."
            )
            return

        user_data[user_id]["has_documents"] = text

        if text == "Иә / Да":
            await ask_upload_documents(message, user_id)
        else:
            user_data[user_id]["document_file_ids"] = []
            await ask_requested_expenses(message, user_id)
        return

    if step == "upload_documents":
        if text.lower() not in ["дайын", "готово"]:
            await send_text(
                message,
                "Құжаттарды файл ретінде жіберіңіз немесе аяқталса 'Дайын' / 'Готово' деп жазыңыз.\n"
                "Отправьте документы файлами или напишите 'Дайын' / 'Готово', когда закончите."
            )
            return

        await ask_requested_expenses(message, user_id)
        return

    if step == "requested_expenses":
        if text not in EXPENSE_OPTIONS:
            await send_text(
                message,
                "Төмендегі нұсқалардың бірін таңдаңыз.\n"
                "Пожалуйста, выберите один из предложенных вариантов."
            )
            return

        user_data[user_id]["requested_expenses"] = text
        await ask_support_reason(message, user_id)
        return

    if step == "support_reason":
        if len(text) < 20:
            await send_text(
                message,
                "Жауапты сәл толығырақ жазыңыз.\n"
                "Пожалуйста, напишите ответ чуть подробнее."
            )
            return

        user_data[user_id]["support_reason"] = text
        await finish_application(message, user_id)
        return


async def main():
    print("Bot is running...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())