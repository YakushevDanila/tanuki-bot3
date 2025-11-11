from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
from datetime import datetime, date as dt, timedelta
import logging
import os
from dotenv import load_dotenv

# Загружаем переменные из .env.local
load_dotenv('.env.local')

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Проверяем обязательные переменные
required_vars = ['BOT_TOKEN', 'GOOGLE_CREDENTIALS', 'SHEET_ID']
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    logger.error(f"❌ Отсутствуют переменные окружения: {', '.join(missing_vars)}")
    logger.info("💡 Создайте файл .env.local с необходимыми переменными")
    exit(1)

# Получаем токен из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Функция очистки ввода от временных меток
def clean_user_input(text):
    if not text:
        return ""
    parts = text.strip().split()
    return parts[0] if parts else ""

# FSM States
class Form(StatesGroup):
    waiting_for_date = State()
    waiting_for_start = State()
    waiting_for_end = State()
    waiting_for_revenue_date = State()
    waiting_for_revenue = State()
    waiting_for_tips_date = State()
    waiting_for_tips = State()
    waiting_for_edit_date = State()
    waiting_for_edit_field = State()
    waiting_for_edit_value = State()
    waiting_for_profit_date = State()
    waiting_for_overwrite_confirm = State()
    waiting_for_stats_start = State()
    waiting_for_stats_end = State()
    waiting_for_export_start = State()
    waiting_for_export_end = State()

# ВЫБОР ХРАНИЛИЩА
storage_type = os.getenv('STORAGE_TYPE', 'google_sheets').lower()

if storage_type == 'google_sheets':
    try:
        from sheets import add_shift, update_value, get_profit, check_shift_exists
        logger.info("✅ Using Google Sheets storage")
    except Exception as e:
        logger.error(f"❌ Failed to use Google Sheets: {e}")
        # Fallback to SQLite если Google Sheets не работает
        try:
            from database import db_manager as storage
            add_shift = storage.add_shift
            update_value = storage.update_value
            get_profit = storage.get_profit
            check_shift_exists = storage.check_shift_exists
            logger.info("✅ Fallback to SQLite storage")
        except ImportError:
            logger.error("❌ No storage backend available")
            exit(1)
else:
    from database import db_manager as storage
    add_shift = storage.add_shift
    update_value = storage.update_value
    get_profit = storage.get_profit
    check_shift_exists = storage.check_shift_exists
    logger.info("✅ Using SQLite storage")

# Импортируем функции для статистики и экспорта (только для SQLite)
try:
    from database import db_manager
except ImportError:
    db_manager = None

# ВРЕМЕННО ОТКЛЮЧАЕМ ПРОВЕРКУ ДОСТУПА
def check_access(message: types.Message):
    logger.info(f"🔓 Access granted for user: {message.from_user.id}")
    return True

@dp.message(Command("start"))
async def start_cmd(msg: types.Message):
    if not check_access(msg): return
    storage_info = "Google Sheets" if storage_type == "google_sheets" else "SQLite"
    text = (
        "Привет! 🌸\n"
        "Вот что я умею:\n"
        "/add_shift — добавить дату и время смены\n"
        "/revenue — ввести выручку за день\n"
        "/tips — добавить сумму чаевых 💰\n"
        "/edit — изменить данные\n"
        "/profit — узнать прибыль за день\n"
        "/stats — статистика за период\n"
        "/export — экспорт данных за период\n"
        "/myid — показать мой ID\n"
        "/help — показать это сообщение\n"
        f"\n💾 Хранилище: {storage_info}\n"
        "💰 Формула прибыли: (часы × 220) + чаевые + (выручка × 0.015)"
    )
    await msg.answer(text)

@dp.message(Command("myid"))
async def show_my_id(msg: types.Message):
    user_id = msg.from_user.id
    first_name = msg.from_user.first_name or "Пользователь"
    await msg.answer(f"👤 {first_name}, ваш ID: `{user_id}`", parse_mode="Markdown")

@dp.message(Command("help"))
async def help_cmd(msg: types.Message):
    await start_cmd(msg)

# ADD SHIFT FLOW
@dp.message(Command("add_shift"))
async def add_shift_start(msg: types.Message, state: FSMContext):
    if not check_access(msg): return
    await msg.answer("Введи дату смены (ДД.ММ.ГГГГ):")
    await state.set_state(Form.waiting_for_date)

@dp.message(Form.waiting_for_date)
async def process_date(msg: types.Message, state: FSMContext):
    clean_date = clean_user_input(msg.text)
    
    # Проверяем валидность даты
    try:
        datetime.strptime(clean_date, "%d.%m.%Y").date()
    except ValueError:
        await msg.answer("❌ Неверный формат даты. Используй ДД.ММ.ГГГГ (например, 15.03.2024)")
        await state.clear()
        return
    
    # Проверяем, существует ли уже смена с этой датой
    exists = await check_shift_exists(clean_date)
    if exists:
        await state.update_data(date=clean_date)
        await msg.answer(f"❌ Смена на дату {clean_date} уже существует!\n"
                        "Хочешь перезаписать ее? (да/нет)")
        await state.set_state(Form.waiting_for_overwrite_confirm)
    else:
        await state.update_data(date=clean_date)
        await msg.answer("Введи время начала смены (чч:мм):")
        await state.set_state(Form.waiting_for_start)

# Обработчик подтверждения перезаписи
@dp.message(Form.waiting_for_overwrite_confirm)
async def process_overwrite_confirm(msg: types.Message, state: FSMContext):
    user_response = clean_user_input(msg.text).lower()
    
    if user_response in ['да', 'yes', 'y', 'д']:
        await msg.answer("Введи время начала смены (чч:мм):")
        await state.set_state(Form.waiting_for_start)
    elif user_response in ['нет', 'no', 'n', 'н']:
        await msg.answer("❌ Добавление смены отменено. Используй /add_shift чтобы начать заново.")
        await state.clear()
    else:
        await msg.answer("Пожалуйста, ответь 'да' или 'нет'")

@dp.message(Form.waiting_for_start)
async def process_start(msg: types.Message, state: FSMContext):
    clean_start = clean_user_input(msg.text)
    
    # Проверяем валидность времени
    try:
        datetime.strptime(clean_start, "%H:%M")
    except ValueError:
        await msg.answer("❌ Неверный формат времени. Используй чч:мм (например, 09:00)")
        await state.clear()
        return
        
    await state.update_data(start=clean_start)
    await msg.answer("Теперь время окончания (чч:мм):")
    await state.set_state(Form.waiting_for_end)

@dp.message(Form.waiting_for_end)
async def process_end(msg: types.Message, state: FSMContext):
    user_data = await state.get_data()
    date_msg = user_data['date']
    start = user_data['start']
    end = clean_user_input(msg.text)
    
    # Проверяем валидность времени окончания
    try:
        datetime.strptime(end, "%H:%M")
    except ValueError:
        await msg.answer("❌ Неверный формат времени. Используй чч:мм (например, 18:00)")
        await state.clear()
        return
    
    success = await add_shift(date_msg, start, end)
    if success:
        await msg.answer(f"✅ Смена {date_msg} ({start}-{end}) добавлена 🩷")
    else:
        await msg.answer("❌ Ошибка при добавлении смены")
    
    await state.clear()

# REVENUE FLOW
@dp.message(Command("revenue"))
async def revenue_start(msg: types.Message, state: FSMContext):
    if not check_access(msg): return
    await msg.answer("Введи дату (ДД.ММ.ГГГГ):")
    await state.set_state(Form.waiting_for_revenue_date)

@dp.message(Form.waiting_for_revenue_date)
async def process_revenue_date(msg: types.Message, state: FSMContext):
    clean_date = clean_user_input(msg.text)
    
    # Проверяем существование смены
    exists = await check_shift_exists(clean_date)
    if not exists:
        await msg.answer(f"❌ Смена на дату {clean_date} не найдена. Сначала добавь смену через /add_shift")
        await state.clear()
        return
        
    await state.update_data(revenue_date=clean_date)
    await msg.answer("Введи сумму выручки (только число):")
    await state.set_state(Form.waiting_for_revenue)

@dp.message(Form.waiting_for_revenue)
async def process_revenue(msg: types.Message, state: FSMContext):
    user_data = await state.get_data()
    date_msg = user_data['revenue_date']
    rev = clean_user_input(msg.text)
    
    # Проверяем, что введено число
    try:
        float(rev)
    except ValueError:
        await msg.answer("❌ Неверный формат числа. Введи только цифры (например: 5000)")
        await state.clear()
        return
    
    success = await update_value(date_msg, "выручка", rev)
    if success:
        await msg.answer(f"✅ Выручка {rev}₽ обновлена для даты {date_msg} 💰✨")
    else:
        await msg.answer("❌ Не удалось обновить выручку")
    
    await state.clear()

# TIPS FLOW
@dp.message(Command("tips"))
async def tips_start(msg: types.Message, state: FSMContext):
    if not check_access(msg): return
    await msg.answer("Введи дату (ДД.ММ.ГГГГ):")
    await state.set_state(Form.waiting_for_tips_date)

@dp.message(Form.waiting_for_tips_date)
async def process_tips_date(msg: types.Message, state: FSMContext):
    clean_date = clean_user_input(msg.text)
    
    # Проверяем существование смены
    exists = await check_shift_exists(clean_date)
    if not exists:
        await msg.answer(f"❌ Смена на дату {clean_date} не найдена. Сначала добавь смену через /add_shift")
        await state.clear()
        return
        
    await state.update_data(tips_date=clean_date)
    await msg.answer("Введи сумму чаевых (число):")
    await state.set_state(Form.waiting_for_tips)

@dp.message(Form.waiting_for_tips)
async def process_tips(msg: types.Message, state: FSMContext):
    user_data = await state.get_data()
    date_msg = user_data['tips_date']
    tips_amount = clean_user_input(msg.text)
    
    # Проверяем, что введено число
    try:
        float(tips_amount)
    except ValueError:
        await msg.answer("❌ Неверный формат числа. Введи только цифры (например: 500)")
        await state.clear()
        return
    
    success = await update_value(date_msg, "чай", tips_amount)
    if success:
        await msg.answer(f"✅ Чаевые {tips_amount}₽ добавлены для даты {date_msg} ☕️💖")
    else:
        await msg.answer("❌ Не удалось добавить чаевые")
    
    await state.clear()

# EDIT FLOW
@dp.message(Command("edit"))
async def edit_start(msg: types.Message, state: FSMContext):
    if not check_access(msg): return
    await msg.answer("Укажи дату (ДД.ММ.ГГГГ):")
    await state.set_state(Form.waiting_for_edit_date)

@dp.message(Form.waiting_for_edit_date)
async def process_edit_date(msg: types.Message, state: FSMContext):
    clean_date = clean_user_input(msg.text)
    
    # Проверяем существование смены
    exists = await check_shift_exists(clean_date)
    if not exists:
        await msg.answer(f"❌ Смена на дату {clean_date} не найдена. Сначала добавь смену через /add_shift")
        await state.clear()
        return
        
    await state.update_data(edit_date=clean_date)
    await msg.answer("Что редактируем? (чай, начало, конец, выручка)")
    await state.set_state(Form.waiting_for_edit_field)

@dp.message(Form.waiting_for_edit_field)
async def process_edit_field(msg: types.Message, state: FSMContext):
    field = clean_user_input(msg.text).lower()
    if field not in ["чай", "начало", "конец", "выручка"]:
        await msg.answer("❌ Такого параметра нет. Используй: чай, начало, конец, выручка")
        await state.clear()
        return
    
    await state.update_data(edit_field=field)
    await msg.answer(f"Введи новое значение для {field}:")
    await state.set_state(Form.waiting_for_edit_value)

@dp.message(Form.waiting_for_edit_value)
async def process_edit_value(msg: types.Message, state: FSMContext):
    user_data = await state.get_data()
    date_msg = user_data['edit_date']
    field = user_data['edit_field']
    value = clean_user_input(msg.text)
    
    success = await update_value(date_msg, field, value)
    if success:
        await msg.answer(f"✅ {field} изменен на {value} для даты {date_msg} 🩷")
    else:
        await msg.answer("❌ Ошибка: не удалось сохранить изменения")
    
    await state.clear()

# PROFIT FLOW
@dp.message(Command("profit"))
async def profit_start(msg: types.Message, state: FSMContext):
    if not check_access(msg): return
    await msg.answer("Введи дату (ДД.ММ.ГГГГ):")
    await state.set_state(Form.waiting_for_profit_date)

@dp.message(Form.waiting_for_profit_date)
async def process_profit_date(msg: types.Message, state: FSMContext):
    clean_date = clean_user_input(msg.text)
    
    # Проверяем валидность даты
    try:
        day = datetime.strptime(clean_date, "%d.%m.%Y").date()
        if day > dt.today():
            await msg.answer("❌ Этот день ещё не наступил 🐾")
            await state.clear()
            return
    except ValueError:
        await msg.answer("❌ Неверный формат даты. Используй ДД.ММ.ГГГГ")
        await state.clear()
        return

    # Проверяем существование смены
    exists = await check_shift_exists(clean_date)
    if not exists:
        await msg.answer(f"❌ Смена на дату {clean_date} не найдена. Сначала добавь смену через /add_shift")
        await state.clear()
        return

    profit_value = await get_profit(clean_date)
    if profit_value is None:
        await msg.answer("❌ Нет данных о прибыли на эту дату 😿")
        await state.clear()
        return

    try:
        profit_float = float(profit_value)
        logger.info(f"💰 Final profit calculation: {profit_float} for {clean_date}")
    except ValueError:
        logger.error(f"❌ Cannot convert profit to float: {profit_value}")
        profit_float = 0

    # Обновленные сообщения с учетом новой формулы
    if profit_float < 4000:
        text = f"📊 Твоя прибыль за {clean_date}: {profit_float:.2f}₽.\nНе расстраивайся, котик 🐾 — ты отлично поработала!"
    elif 4000 <= profit_float <= 6000:
        text = f"📊 Твоя прибыль за {clean_date}: {profit_float:.2f}₽.\nНеплохая смена 😺 — беги радовать себя чем-то вкусным!"
    else:
        text = f"📊 Твоя прибыль за {clean_date}: {profit_float:.2f}₽.\nТы просто суперстар 🌟 — ещё немного, и миллион твой!"
    
    await msg.answer(text)
    await state.clear()

# STATS FLOW - только для SQLite
@dp.message(Command("stats"))
async def stats_start(msg: types.Message, state: FSMContext):
    if not check_access(msg): return
    
    if storage_type == 'google_sheets':
        await msg.answer("❌ Статистика временно недоступна при использовании Google Sheets. Используй SQLite хранилище.")
        return
        
    if not db_manager:
        await msg.answer("❌ Модуль статистики недоступен")
        return
        
    await msg.answer("Введи начальную дату для статистики (ДД.ММ.ГГГГ):")
    await state.set_state(Form.waiting_for_stats_start)

@dp.message(Form.waiting_for_stats_start)
async def process_stats_start(msg: types.Message, state: FSMContext):
    clean_date = clean_user_input(msg.text)
    
    try:
        datetime.strptime(clean_date, "%d.%m.%Y").date()
        await state.update_data(stats_start=clean_date)
        await msg.answer("Введи конечную дату (ДД.ММ.ГГГГ):")
        await state.set_state(Form.waiting_for_stats_end)
    except ValueError:
        await msg.answer("❌ Неверный формат даты. Используй ДД.ММ.ГГГГ")
        await state.clear()

@dp.message(Form.waiting_for_stats_end)
async def process_stats_end(msg: types.Message, state: FSMContext):
    clean_date = clean_user_input(msg.text)
    
    try:
        datetime.strptime(clean_date, "%d.%m.%Y").date()
        user_data = await state.get_data()
        start_date = user_data['stats_start']
        end_date = clean_date
        
        stats = await db_manager.get_statistics(start_date, end_date)
        
        if not stats:
            await msg.answer("❌ Нет данных за указанный период")
            await state.clear()
            return
        
        # Форматируем статистику
        text = f"📊 Статистика за период {start_date} - {end_date}:\n\n"
        text += f"• Количество смен: {stats['shift_count']}\n"
        text += f"• Общая выручка: {stats['total_revenue']:.2f}₽\n"
        text += f"• Общие чаевые: {stats['total_tips']:.2f}₽\n"
        text += f"• Общая прибыль: {stats['total_profit']:.2f}₽\n"
        text += f"• Средняя выручка за смену: {stats['avg_revenue']:.2f}₽\n"
        text += f"• Средние чаевые за смену: {stats['avg_tips']:.2f}₽\n"
        text += f"• Средняя прибыль за смену: {stats['avg_profit']:.2f}₽"
        
        await msg.answer(text)
        
    except ValueError:
        await msg.answer("❌ Неверный формат даты. Используй ДД.ММ.ГГГГ")
    
    await state.clear()

# EXPORT FLOW - только для SQLite
@dp.message(Command("export"))
async def export_start(msg: types.Message, state: FSMContext):
    if not check_access(msg): return
    
    if storage_type == 'google_sheets':
        await msg.answer("❌ Экспорт временно недоступен при использовании Google Sheets. Используй SQLite хранилище.")
        return
        
    if not db_manager:
        await msg.answer("❌ Модуль экспорта недоступен")
        return
        
    await msg.answer("Введи начальную дату для экспорта (ДД.ММ.ГГГГ):")
    await state.set_state(Form.waiting_for_export_start)

@dp.message(Form.waiting_for_export_start)
async def process_export_start(msg: types.Message, state: FSMContext):
    clean_date = clean_user_input(msg.text)
    
    try:
        datetime.strptime(clean_date, "%d.%m.%Y").date()
        await state.update_data(export_start=clean_date)
        await msg.answer("Введи конечную дату (ДД.ММ.ГГГГ):")
        await state.set_state(Form.waiting_for_export_end)
    except ValueError:
        await msg.answer("❌ Неверный формат даты. Используй ДД.ММ.ГГГГ")
        await state.clear()

@dp.message(Form.waiting_for_export_end)
async def process_export_end(msg: types.Message, state: FSMContext):
    clean_date = clean_user_input(msg.text)
    
    try:
        datetime.strptime(clean_date, "%d.%m.%Y").date()
        user_data = await state.get_data()
        start_date = user_data['export_start']
        end_date = clean_date
        
        shifts = await db_manager.get_shifts_in_period(start_date, end_date)
        
        if not shifts:
            await msg.answer("❌ Нет данных за указанный период")
            await state.clear()
            return
        
        # Формируем экспорт
        export_text = f"Экспорт данных за период {start_date} - {end_date}\n\n"
        
        total_revenue = 0
        total_tips = 0
        
        for shift in shifts:
            export_text += f"📅 {shift['date']} ({shift['start']}-{shift['end']})\n"
            export_text += f"   Выручка: {shift['revenue']:.2f}₽\n"
            export_text += f"   Чаевые: {shift['tips']:.2f}₽\n"
            export_text += f"   Прибыль: {(shift['revenue'] + shift['tips']):.2f}₽\n\n"
            
            total_revenue += shift['revenue']
            total_tips += shift['tips']
        
        export_text += f"ИТОГО:\n"
        export_text += f"Выручка: {total_revenue:.2f}₽\n"
        export_text += f"Чаевые: {total_tips:.2f}₽\n"
        export_text += f"Общая прибыль: {total_revenue + total_tips:.2f}₽"
        
        # Разбиваем на части если сообщение слишком длинное
        if len(export_text) > 4000:
            parts = [export_text[i:i+4000] for i in range(0, len(export_text), 4000)]
            for part in parts:
                await msg.answer(part)
                await asyncio.sleep(0.5)
        else:
            await msg.answer(export_text)
        
    except ValueError:
        await msg.answer("❌ Неверный формат даты. Используй ДД.ММ.ГГГГ")
    
    await state.clear()

@dp.message()
async def echo(message: types.Message):
    """Обработка любых других сообщений"""
    if not check_access(message): return
    await message.answer("Не понимаю эту команду 😿\nИспользуй /help для списка команд")

async def main():
    try:
        logger.info("🚀 Starting bot with enhanced features...")
        
        # УДАЛЯЕМ ВЕБХУК ПЕРЕД ЗАПУСКОМ POLLING
        logger.info("🗑️ Deleting webhook...")
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook deleted successfully")
        
        logger.info("✅ Starting polling...")
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"💥 Bot crashed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🟢 Bot starting with enhanced features...")
    asyncio.run(main())

