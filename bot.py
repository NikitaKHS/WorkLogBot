import asyncio
import logging
import json
import re

from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import CommandStart
from aiogram.filters.state import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= НАСТРОЙКИ ===================
TELEGRAM_TOKEN = "Ваш_токен_от_бота"
CATEGORIES_FILE = "categories.json"
# ================================================

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

user_tasks: dict[int, list[dict[str, str | None]]] = {}

class AddTaskStates(StatesGroup):
    waiting_for_work_type = State()
    waiting_for_category = State()
    waiting_for_custom_category = State()
    waiting_for_quantity = State()
    waiting_for_link = State()

default_categories = ["Сервер", "Кроссировка", "Облако", "Конструктив"]

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================

def load_categories() -> list[str]:
    try:
        with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default_categories.copy()

def save_categories(categories: list[str]) -> None:
    with open(CATEGORIES_FILE, "w", encoding="utf-8") as f:
        json.dump(categories, f, ensure_ascii=False, indent=4)

def decline(word: str, count: int) -> str:
    if 11 <= (count % 100) <= 14:
        if word.endswith("о"):
            return word[:-1] + "ов"
        if word.endswith("а"):
            return word[:-1] + "ок"
        return word + "ов"
    last = count % 10
    if last == 1:
        return word
    if 2 <= last <= 4:
        if word.endswith("ка"):
            return word[:-2] + "ки"
        if word.endswith("о"):
            return word[:-1] + "а"
        if word.endswith("а"):
            return word[:-1] + "ы"
        return word + "а"
    if word.endswith("о"):
        return word[:-1] + "ов"
    if word.endswith("а"):
        return word[:-1] + "ок"
    return word + "ов"

def get_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="➕ Добавить", callback_data="add"),
            InlineKeyboardButton(text="❌ Удалить запись", callback_data="delete")
        ],
        [
            InlineKeyboardButton(text="✅ Получить итог", callback_data="final"),
            InlineKeyboardButton(text="🧹 Очистить всё", callback_data="clear")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_work_type_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="Монтаж", callback_data="work_montage"),
            InlineKeyboardButton(text="Демонтаж", callback_data="work_dismantle")
        ],
        [
            InlineKeyboardButton(text="Отмена", callback_data="cancel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_category_keyboard(categories: list[str]) -> InlineKeyboardMarkup:
    inline = []
    temp = []
    for cat in categories:
        temp.append(InlineKeyboardButton(text=cat, callback_data=f"category_{cat}"))
        if len(temp) == 2:
            inline.append(temp.copy())
            temp.clear()
    if temp:
        inline.append(temp.copy())
    inline.append([InlineKeyboardButton(text="➕ Своя услуга", callback_data="category_custom")])
    inline.append([InlineKeyboardButton(text="Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=inline)

def get_skip_link_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="Пропустить", callback_data="skip_link")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_delete_keyboard(user_id: int) -> InlineKeyboardMarkup:
    inline = []
    tasks = user_tasks.get(user_id, [])
    for idx, _ in enumerate(tasks):
        inline.append([InlineKeyboardButton(text=f"Удалить {idx+1}", callback_data=f"remove_{idx}")])
    inline.append([InlineKeyboardButton(text="Отмена", callback_data="cancel_delete")])
    return InlineKeyboardMarkup(inline_keyboard=inline)

def save_record(uid: int, record_text: str, link: str | None) -> None:
    user_tasks.setdefault(uid, []).append({"record": record_text, "link": link})

# ================= ОБРАБОТЧИКИ ==================

async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Привет! Выбери действие:", reply_markup=get_main_keyboard())

async def manual_add(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AddTaskStates.waiting_for_work_type)
    await call.message.answer("Выбери тип работы:", reply_markup=get_work_type_keyboard())

async def menu_callback(call: types.CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    action = call.data
    if action == "delete":
        tasks = user_tasks.get(uid, [])
        if tasks:
            await call.message.answer("Выбери запись для удаления:", reply_markup=get_delete_keyboard(uid))
        else:
            await call.message.answer("Нет записей для удаления.", reply_markup=get_main_keyboard())
    elif action == "final":
        tasks = user_tasks.get(uid, [])
        if not tasks:
            await call.message.answer("Нет записей.", reply_markup=get_main_keyboard())
            return
        msg = ""
        for i, t in enumerate(tasks, 1):
            if t["link"]:
                msg += f"{i}) {t['record']} - {t['link']}\n\n"
            else:
                msg += f"{i}) {t['record']}\n\n"
        await call.message.answer(msg.strip(), parse_mode="Markdown", reply_markup=get_main_keyboard())
    elif action == "clear":
        user_tasks[uid] = []
        await call.message.answer("Все записи очищены.", reply_markup=get_main_keyboard())

async def work_type_selected(call: types.CallbackQuery, state: FSMContext):
    work_type = "Монтаж" if call.data.split("_", 1)[1] == "montage" else "Демонтаж"
    await state.update_data(work_type=work_type)
    await state.set_state(AddTaskStates.waiting_for_category)
    categories = load_categories()
    await call.message.answer("Выбери услугу:", reply_markup=get_category_keyboard(categories))

async def category_selected(call: types.CallbackQuery, state: FSMContext):
    cat = call.data.split("_", 1)[1]
    if cat == "custom":
        await state.set_state(AddTaskStates.waiting_for_custom_category)
        await call.message.answer("Введи название новой услуги:")
    else:
        await state.update_data(category=cat)
        await state.set_state(AddTaskStates.waiting_for_quantity)
        await call.message.answer("Сколько штук?")

async def custom_category_received(message: types.Message, state: FSMContext):
    custom = message.text.strip()
    categories = load_categories()
    if custom not in categories:
        categories.append(custom)
        save_categories(categories)
    await state.update_data(category=custom)
    await state.set_state(AddTaskStates.waiting_for_quantity)
    await message.answer(f"Новая услуга «{custom}» добавлена. Теперь введи количество:")

async def quantity_received(message: types.Message, state: FSMContext):
    qty_text = message.text.strip()
    if not qty_text.isdigit():
        await message.reply("Введи число.")
        return
    count = int(qty_text)
    data = await state.get_data()
    work_type = data["work_type"]
    category = data["category"]
    cat_form = decline(category, count)
    record_text = f"{work_type} {count} {cat_form}"
    await state.update_data(record=record_text)
    await state.set_state(AddTaskStates.waiting_for_link)
    await message.answer("Прикрепи ссылку или нажми «Пропустить»:", reply_markup=get_skip_link_keyboard())

async def link_received(message: types.Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    record_text = data["record"]
    if text.lower().startswith("http"):
        save_record(message.from_user.id, record_text, text)
        await message.answer(f"{record_text} - {text}", parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        save_record(message.from_user.id, record_text, None)
        await message.answer(f"{record_text}", parse_mode="Markdown", reply_markup=get_main_keyboard())
    await state.clear()

async def skip_link(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    record_text = data["record"]
    save_record(call.from_user.id, record_text, None)
    await call.message.answer(f"{record_text}", parse_mode="Markdown", reply_markup=get_main_keyboard())
    await state.clear()

async def remove_record(call: types.CallbackQuery):
    uid = call.from_user.id
    idx = int(call.data.split("_", 1)[1])
    tasks = user_tasks.get(uid, [])
    if 0 <= idx < len(tasks):
        deleted = tasks.pop(idx)
        await call.message.answer(f"Удалено: {deleted['record']}", reply_markup=get_main_keyboard())
    else:
        await call.message.answer("Ошибка.", reply_markup=get_main_keyboard())

async def cancel_all(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("Отменено.", reply_markup=get_main_keyboard())

# ================= РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ==================

dp.message.register(cmd_start, CommandStart())

dp.callback_query.register(manual_add, lambda c: c.data == "add")
dp.callback_query.register(menu_callback, lambda c: c.data in ["delete", "final", "clear"])

dp.callback_query.register(
    work_type_selected,
    lambda c: c.data.startswith("work_"),
    StateFilter(AddTaskStates.waiting_for_work_type),
)
dp.callback_query.register(
    category_selected,
    lambda c: c.data.startswith("category_"),
    StateFilter(AddTaskStates.waiting_for_category),
)

dp.message.register(custom_category_received, StateFilter(AddTaskStates.waiting_for_custom_category))
dp.message.register(quantity_received, StateFilter(AddTaskStates.waiting_for_quantity))
dp.message.register(link_received, StateFilter(AddTaskStates.waiting_for_link))
dp.callback_query.register(skip_link, lambda c: c.data == "skip_link", StateFilter(AddTaskStates.waiting_for_link))

dp.callback_query.register(remove_record, lambda c: c.data.startswith("remove_"))
dp.callback_query.register(cancel_all, lambda c: c.data in ["cancel", "cancel_delete"])

# ==================== ПУСК БОТА ====================

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
