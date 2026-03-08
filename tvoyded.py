import logging
import datetime
import random
import sqlite3
import os
import json
import sys
import traceback
from functools import lru_cache
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = '8690499757:AAFLZYPfNb6tNlOA1CYrheqOFk9wJMN4GfE'

# Пути к папкам
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, 'data')
IMAGES_FOLDER = os.path.join(BASE_DIR, 'images')

# Создаём папки, если их нет
os.makedirs(DB_FOLDER, exist_ok=True)
os.makedirs(IMAGES_FOLDER, exist_ok=True)

DB_FILE = os.path.join(DB_FOLDER, 'ded_bot.db')

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, 'bot.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== НАЗВАНИЯ КАРТИНОК ==========
PHOTO_FILES = {
    'welcome':      'welcome.png',
    'water':        'water.png',
    'drank':        'drank.png',
    'plan':         'plan.png',
    'help':         'help.png',
    'sleep':        'sleep.png',
    'woke_up':      'woke_up.png',
    'motivation':   'motivation.png',
    'setup':        'welcome.png',
}

# ========== КЭШИРОВАНИЕ КАРТИНОК ==========
@lru_cache(maxsize=32)
def get_cached_image(image_name):
    """Загружает картинку в память и возвращает BytesIO"""
    try:
        image_path = os.path.join(IMAGES_FOLDER, image_name)
        if not os.path.exists(image_path):
            logger.error(f"❌ Файл не найден: {image_path}")
            return None
        
        file_size = os.path.getsize(image_path)
        if file_size == 0:
            logger.error(f"❌ Файл пустой: {image_path}")
            return None
            
        with open(image_path, 'rb') as f:
            data = f.read()
            if len(data) == 0:
                logger.error(f"❌ Файл прочитан как пустой: {image_name}")
                return None
            return BytesIO(data)
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки {image_name}: {e}")
        return None

async def send_photo_optimized(context, chat_id, image_key, caption=None, reply_markup=None):
    """Улучшенная отправка фото с повторными попытками"""
    
    # Пробуем отправить фото до 3 раз
    for attempt in range(3):
        try:
            image_name = PHOTO_FILES[image_key]
            image_path = os.path.join(IMAGES_FOLDER, image_name)
            
            # Проверяем файл
            if not os.path.exists(image_path):
                logger.error(f"❌ Файл не найден: {image_path}")
                break
            
            # Проверяем размер
            file_size = os.path.getsize(image_path)
            if file_size == 0:
                logger.error(f"❌ Файл пустой: {image_path}")
                break
            
            # Читаем файл заново при каждой попытке (не из кэша)
            with open(image_path, 'rb') as f:
                photo_data = f.read()
                if len(photo_data) == 0:
                    logger.error(f"❌ Файл прочитан как пустой: {image_name}")
                    continue
                
                # Отправляем
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=BytesIO(photo_data),
                    caption=caption,
                    reply_markup=reply_markup,
                    read_timeout=30,
                    write_timeout=30
                )
                
            logger.info(f"✅ Фото отправлено: {image_name} (попытка {attempt+1})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки {image_key} (попытка {attempt+1}): {e}")
            if attempt < 2:  # Если не последняя попытка
                await asyncio.sleep(1)  # Ждём 1 секунду перед повтором
            else:
                # Отправляем только текст
                if caption:
                    await context.bot.send_message(chat_id=chat_id, text=caption, reply_markup=reply_markup)
                return False
    
    return False

# ========== ПЛАНЫ ТРЕНИРОВОК ==========
TRAINING_PLANS = {
    'beginner': {
        'name': '👶 НАЧАЛЬНЫЙ УРОВЕНЬ',
        'description': 'Для новичков, 3 раза в неделю',
        'Понедельник': '🏋️ ГРУДЬ + ТРИЦЕПС\n• Жим штанги лежа: 3×10\n• Жим гантелей на наклонной: 3×12\n• Французский жим: 3×12\n• Разгибания на блоке: 3×15',
        'Среда': '🏋️ СПИНА + БИЦЕПС\n• Тяга верхнего блока: 3×12\n• Тяга гантели в наклоне: 3×12\n• Подъем штанги на бицепс: 3×10\n• Молотки: 3×12',
        'Пятница': '🏋️ НОГИ + ПЛЕЧИ\n• Приседания: 3×12\n• Жим ногами: 3×15\n• Армейский жим: 3×10\n• Махи гантелями: 3×15'
    },
    'intermediate': {
        'name': '🔥 СРЕДНИЙ УРОВЕНЬ',
        'description': 'Для опытных, 4 раза в неделю',
        'Понедельник': '💪 ГРУДЬ + ТРИЦЕПС\n• Жим штанги: 4×8\n• Жим гантелей: 4×10\n• Кроссоверы: 4×12\n• Отжимания на брусьях: 4×8',
        'Вторник': '💪 СПИНА + БИЦЕПС\n• Становая тяга: 4×6\n• Тяга штанги: 4×8\n• Подтягивания: 4×макс\n• Подъем штанги на бицепс: 4×10',
        'Четверг': '💪 ПЛЕЧИ + ТРАПЕЦИИ\n• Жим сидя: 4×8\n• Тяга к подбородку: 4×10\n• Махи в стороны: 4×12\n• Шраги: 4×12',
        'Пятница': '💪 НОГИ\n• Приседания: 4×8\n• Жим ногами: 4×10\n• Румынская тяга: 4×8\n• Выпады: 4×10'
    },
    'advanced': {
        'name': '⚡ ПРОДВИНУТЫЙ УРОВЕНЬ',
        'description': 'Для профи, 5-6 раз в неделю',
        'Понедельник': '🔥 ГРУДЬ + ПЕРЕДНЯЯ ДЕЛЬТА\n• Жим штанги: 5×5\n• Жим гантелей: 4×8\n• Отжимания на брусьях: 4×8\n• Жим гантелей сидя: 4×10',
        'Вторник': '🔥 СПИНА + ЗАДНЯЯ ДЕЛЬТА\n• Становая тяга: 5×5\n• Тяга штанги: 4×8\n• Тяга гантели: 4×10\n• Махи назад: 4×12',
        'Среда': '🔥 НОГИ\n• Приседания: 5×5\n• Жим ногами: 4×10\n• Румынская тяга: 4×8\n• Выпады: 4×10',
        'Пятница': '🔥 ПЛЕЧИ + ТРИЦЕПС\n• Армейский жим: 5×5\n• Жим гантелей: 4×8\n• Махи: 4×12\n• Французский жим: 4×10',
        'Суббота': '🔥 РУКИ + АКЦЕНТЫ\n• Подтягивания: 4×8\n• Бицепс: 4×10\n• Трицепс: 4×10\n• Предплечья: 4×15'
    }
}

# ========== СИСТЕМА ДОСТИЖЕНИЙ ==========
ACHIEVEMENTS = {
    'water_first': {
        'name': '💧 ПЕРВАЯ ВОДА',
        'desc': 'Выпил воду впервые',
        'how_to_get': 'Выпей стакан воды и отметь это в боте (💧 Пить воду → введи количество)',
        'emoji': '💧'
    },
    'water_3_days': {
        'name': '💪 ВОДНЫЙ БАЛАНС',
        'desc': 'Пил воду 3 дня подряд',
        'how_to_get': 'Отмечай воду каждый день 3 дня подряд',
        'emoji': '💪'
    },
    'sleep_5': {
        'name': '😴 5 НОЧЕЙ',
        'desc': 'Проснулся 5 раз',
        'how_to_get': 'Используй трекер сна (🌙 Ложиться спать → 👀 Я проснулся) 5 раз',
        'emoji': '😴'
    },
    'workout_3': {
        'name': '🔥 ТРИ ТРЕНИРОВКИ',
        'desc': 'Выполнил 3 тренировки',
        'how_to_get': 'Заверши 3 тренировки по плану (🏋️ План тренировок → ✅ Завершил тренировку)',
        'emoji': '🔥'
    },
    'veteran': {
        'name': '⭐ ВЕТЕРАН',
        'desc': 'Пользуешься ботом 30 дней',
        'how_to_get': 'Используй бота 30 дней с момента регистрации',
        'emoji': '⭐'
    }
}

# ========== СОВЕТЫ ДЕДА ==========
DEDS_ADVICE = [
    "Сон и питание — 70% успеха. Остальное — железо. 💪",
    "Техника важнее веса. Не позорь деда. 🏋️",
    "Прогрессия нагрузки или ты стоишь на месте. 🔥",
    "Разминка — не для слабаков. Делай всегда. ⚡",
    "Отдых между подходами — не перекур. ⏱️",
    "Вода — это не опция, это топливо. 💧",
    "Нет оправданий. Есть только лень. 😤",
    "Засыпай до полуночи — мышцы растут во сне. 🌙",
    "Белок каждый день. Без него — пустая трата времени. 🍗",
    "Если болит — значит ты делал неправильно. 🤕",
    "Каждый день — шаг к лучшему себе или к дивану. 🏃",
    "Дисциплина бьёт мотивацию в 10 раз. ⚔️",
    "Тренируйся не для зеркала, а для себя через год. 🪞",
    "Железо не ждёт. А ты ждёшь чего? 🏋️‍♂️",
    "Меньше нытья — больше повторений. 💥"
]

# ========== КЛАВИАТУРА (ОРИГИНАЛЬНАЯ) ==========
MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("💧 Пить воду")],
        [KeyboardButton("🏋️ План тренировок")],
        [KeyboardButton("❓ Помощь")],
        [KeyboardButton("🌙 Ложиться спать")],
        [KeyboardButton("🏆 Достижения")],
        [KeyboardButton("🛒 Магазин Деда")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

# ========== РАБОТА С БАЗОЙ ДАННЫХ ==========
def get_db_connection():
    return sqlite3.connect(DB_FILE, timeout=10)

def init_db():
    """Инициализация БД со ВСЕМИ нужными колонками"""
    with get_db_connection() as conn:
        c = conn.cursor()
        
        # Создаём таблицу со всеми колонками
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                gender TEXT,
                weight REAL,
                height REAL,
                last_water TEXT,
                sleep_start TEXT,
                total_sleep_seconds INTEGER DEFAULT 0,
                setup_step INTEGER DEFAULT 0,
                setup_message_id TEXT,
                setup_chat_id TEXT,
                total_water_drinks INTEGER DEFAULT 0,
                water_streak INTEGER DEFAULT 0,
                last_water_date TEXT,
                total_sleeps INTEGER DEFAULT 0,
                workouts_done INTEGER DEFAULT 0,
                achievements TEXT DEFAULT '[]',
                register_date TEXT,
                premium INTEGER DEFAULT 0,
                today_water_ml INTEGER DEFAULT 0,
                last_water_reset TEXT
            )
        ''')
        conn.commit()
        
        # Проверяем, что все колонки существуют
        c.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in c.fetchall()]
        
        # Если какой-то колонки нет, добавляем
        required_columns = ['today_water_ml', 'last_water_reset']
        for col in required_columns:
            if col not in columns:
                try:
                    c.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 0")
                    logger.info(f"✅ Добавлена колонка {col}")
                except:
                    pass
        
        conn.commit()
    
    logger.info("✅ База данных готова")

# Инициализация при запуске
init_db()

def get_user_data(user_id: int) -> dict:
    """Получение данных пользователя"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        
        if row:
            # Получаем названия колонок
            c.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in c.fetchall()]
            
            # Создаём словарь с данными
            data = {}
            for i, col in enumerate(columns):
                if i < len(row):
                    if col in ['last_water', 'sleep_start', 'last_water_date', 'register_date', 'last_water_reset'] and row[i]:
                        try:
                            data[col] = datetime.datetime.fromisoformat(row[i])
                        except:
                            data[col] = None
                    elif col == 'achievements' and row[i]:
                        try:
                            data[col] = json.loads(row[i])
                        except:
                            data[col] = []
                    else:
                        data[col] = row[i]
            return data
    
    # Если пользователя нет — создаём
    now = datetime.datetime.now()
    default = {
        'user_id': user_id,
        'gender': None,
        'weight': None,
        'height': None,
        'last_water': None,
        'sleep_start': None,
        'total_sleep_seconds': 0,
        'setup_step': 0,
        'setup_message_id': None,
        'setup_chat_id': None,
        'total_water_drinks': 0,
        'water_streak': 0,
        'last_water_date': None,
        'total_sleeps': 0,
        'workouts_done': 0,
        'achievements': [],
        'register_date': now,
        'premium': 0,
        'today_water_ml': 0,
        'last_water_reset': now
    }
    save_user_data(user_id, default)
    return default

def save_user_data(user_id: int, data: dict):
    """Сохранение данных пользователя"""
    with get_db_connection() as conn:
        c = conn.cursor()
        
        # Получаем список колонок
        c.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in c.fetchall()]
        
        # Подготавливаем значения
        values = []
        for col in columns:
            if col in data:
                val = data[col]
                if isinstance(val, datetime.datetime):
                    values.append(val.isoformat())
                elif isinstance(val, list):
                    values.append(json.dumps(val))
                else:
                    values.append(val)
            else:
                values.append(None)
        
        # Формируем запрос
        placeholders = ','.join(['?' for _ in columns])
        c.execute(f'''
            INSERT OR REPLACE INTO users ({','.join(columns)})
            VALUES ({placeholders})
        ''', values)
        conn.commit()

def check_and_reset_water(user_data):
    """Проверяет, нужно ли сбросить счетчик воды на новый день"""
    now = datetime.datetime.now()
    
    if user_data.get('last_water_reset'):
        last_reset = user_data['last_water_reset']
        if isinstance(last_reset, str):
            try:
                last_reset = datetime.datetime.fromisoformat(last_reset)
            except:
                last_reset = now
        else:
            last_reset = last_reset
        
        if now.date() > last_reset.date():
            user_data['today_water_ml'] = 0
            user_data['last_water_reset'] = now
    else:
        user_data['today_water_ml'] = 0
        user_data['last_water_reset'] = now
    
    return user_data

def get_water_norm(user_data):
    """Рассчитывает норму воды в мл"""
    if not user_data.get('weight'):
        return 2000
    
    weight = user_data['weight']
    # Простая формула: вес * 30 мл
    norm = weight * 30
    return max(1500, min(4000, int(norm)))

def check_achievements(user_id: int, user_data: dict):
    """Проверка и выдача новых достижений"""
    try:
        new_achievements = []
        current_achievements = user_data.get('achievements', [])
        if isinstance(current_achievements, str):
            try:
                current_achievements = json.loads(current_achievements)
            except:
                current_achievements = []
        
        # Проверяем каждое достижение
        if 'water_first' not in current_achievements and user_data.get('total_water_drinks', 0) > 0:
            new_achievements.append('water_first')
        
        if 'water_3_days' not in current_achievements and user_data.get('water_streak', 0) >= 3:
            new_achievements.append('water_3_days')
        
        if 'sleep_5' not in current_achievements and user_data.get('total_sleeps', 0) >= 5:
            new_achievements.append('sleep_5')
        
        if 'workout_3' not in current_achievements and user_data.get('workouts_done', 0) >= 3:
            new_achievements.append('workout_3')
        
        if 'veteran' not in current_achievements:
            if user_data.get('register_date'):
                register_date = user_data['register_date']
                if isinstance(register_date, str):
                    try:
                        register_date = datetime.datetime.fromisoformat(register_date)
                    except:
                        register_date = datetime.datetime.now()
                days = (datetime.datetime.now() - register_date).days
                if days >= 30:
                    new_achievements.append('veteran')
        
        # Если есть новые достижения, сохраняем
        if new_achievements:
            user_data['achievements'] = current_achievements + new_achievements
            save_user_data(user_id, user_data)
        
        return new_achievements
    except Exception as e:
        logger.error(f"Ошибка проверки достижений: {e}")
        return []

# ========== КОМАНДА /wake ==========
async def wake_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для быстрого пробуждения /wake"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if not user_data or user_data.get('gender') is None:
        await update.message.reply_text("👴 Сначала настрой меня — /start")
        return
    
    now = datetime.datetime.now()
    
    if user_data.get('sleep_start'):
        sleep_start = user_data['sleep_start']
        if isinstance(sleep_start, str):
            try:
                sleep_start = datetime.datetime.fromisoformat(sleep_start)
            except:
                sleep_start = now
        
        duration = now - sleep_start
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60

        user_data['total_sleep_seconds'] = user_data.get('total_sleep_seconds', 0) + duration.seconds
        user_data['total_sleeps'] = user_data.get('total_sleeps', 0) + 1
        user_data['sleep_start'] = None
        
        # Проверяем достижения
        new_achievements = check_achievements(user_id, user_data)
        
        save_user_data(user_id, user_data)

        total_hours = user_data['total_sleep_seconds'] // 3600
        total_min = (user_data['total_sleep_seconds'] % 3600) // 60

        msg = f"🌅 Проснулся! Спал {hours} ч {minutes} мин\n📊 Всего сна: {total_hours} ч {total_min} мин"
        await update.message.reply_text(msg)
        
        # Если есть новые достижения, показываем
        if new_achievements:
            achiev_msg = "🎉 НОВЫЕ ДОСТИЖЕНИЯ!\n\n"
            for ach in new_achievements:
                if ach in ACHIEVEMENTS:
                    achiev_msg += f"{ACHIEVEMENTS[ach]['emoji']} {ACHIEVEMENTS[ach]['name']}\n"
            await update.message.reply_text(achiev_msg)
        
        await send_photo_optimized(
            context,
            update.effective_chat.id,
            'woke_up',
            f"💬 {random.choice(DEDS_ADVICE)}"
        )
    else:
        await update.message.reply_text("❓ Ты и не ложился ещё!")

# ========== ОБРАБОТЧИКИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка команды /start"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)

    if user_data['setup_step'] == 0 and user_data['gender'] is None:
        await send_photo_optimized(
            context, 
            update.effective_chat.id,
            'setup',
            "👴 Привет! Я Твой Дед\n\nСначала настрой меня под себя."
        )

        keyboard = [
            [InlineKeyboardButton("👨 Мужской", callback_data='gender_male')],
            [InlineKeyboardButton("👩 Женский", callback_data='gender_female')]
        ]
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="👇 Выбери пол:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        user_data['setup_message_id'] = str(msg.message_id)
        user_data['setup_chat_id'] = str(update.effective_chat.id)
        user_data['setup_step'] = 0
        save_user_data(user_id, user_data)
    else:
        await send_photo_optimized(
            context,
            update.effective_chat.id,
            'welcome',
            "👋 С возвращением, боец!",
            MAIN_MENU
        )

async def setup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка настройки"""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    logger.info(f"⚙️ Настройка: {query.data} от {user_id}")

    user_data = get_user_data(user_id)
    if not user_data:
        return

    chat_id = int(user_data['setup_chat_id'])
    message_id = int(user_data['setup_message_id'])
    step = user_data['setup_step']

    try:
        if step == 0:  # Выбор пола
            if query.data == 'gender_male':
                user_data['gender'] = 'male'
                avg_weight, avg_height = 80, 175
            elif query.data == 'gender_female':
                user_data['gender'] = 'female'
                avg_weight, avg_height = 68, 162
            else:
                return

            user_data['setup_step'] = 1
            save_user_data(user_id, user_data)

            keyboard = [
                [InlineKeyboardButton(f"⚖️ Средний ({avg_weight} кг)", callback_data=f'weight_avg_{avg_weight}')],
                [InlineKeyboardButton("✏️ Своя цифра", callback_data='weight_custom')]
            ]
            
            await query.edit_message_text(
                text="⚖️ Теперь вес (кг):",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif step == 1:  # Выбор веса
            if query.data.startswith('weight_avg_'):
                user_data['weight'] = int(query.data.split('_')[-1])
                user_data['setup_step'] = 2
                save_user_data(user_id, user_data)

                avg_height = 175 if user_data['gender'] == 'male' else 162
                keyboard = [
                    [InlineKeyboardButton(f"📏 Средний ({avg_height} см)", callback_data=f'height_avg_{avg_height}')],
                    [InlineKeyboardButton("✏️ Своя цифра", callback_data='height_custom')]
                ]
                
                await query.edit_message_text(
                    text="📏 Теперь рост (см):",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif query.data == 'weight_custom':
                user_data['setup_step'] = 1.5
                save_user_data(user_id, user_data)
                await query.edit_message_text(
                    text="✏️ Введи свой вес в кг (число от 30 до 200):",
                    reply_markup=None
                )

        elif step == 2:  # Выбор роста
            if query.data.startswith('height_avg_'):
                user_data['height'] = int(query.data.split('_')[-1])
                user_data['setup_step'] = 0
                save_user_data(user_id, user_data)

                water_norm = get_water_norm(user_data)

                final_text = (
                    f"✅ Настройка завершена!\n\n"
                    f"👤 Пол: {'Мужской' if user_data['gender'] == 'male' else 'Женский'}\n"
                    f"⚖️ Вес: {user_data['weight']} кг\n"
                    f"📏 Рост: {user_data['height']} см\n\n"
                    f"💧 Норма воды: {water_norm} мл/день\n\n"
                    f"👇 Теперь выбирай действие в меню"
                )

                await query.edit_message_text(text=final_text, reply_markup=None)
                await send_photo_optimized(
                    context,
                    chat_id,
                    'welcome',
                    "🎉 Настройка завершена!",
                    MAIN_MENU
                )
            elif query.data == 'height_custom':
                user_data['setup_step'] = 2.5
                save_user_data(user_id, user_data)
                await query.edit_message_text(
                    text="✏️ Введи свой рост в см (число от 100 до 220):",
                    reply_markup=None
                )
    except Exception as e:
        logger.error(f"❌ Ошибка в setup_callback: {e}")
        await query.edit_message_text("❌ Произошла ошибка. Нажми /start заново.")

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка текстового ввода при настройке"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    user_data = get_user_data(user_id)
    
    if not user_data or user_data.get('setup_step', 0) == 0:
        return

    step = user_data['setup_step']
    chat_id = int(user_data['setup_chat_id'])
    message_id = int(user_data['setup_message_id'])

    try:
        if step == 1.5:  # Ввод веса
            weight = int(text)
            if not 30 <= weight <= 200:
                raise ValueError
            user_data['weight'] = weight
            user_data['setup_step'] = 2
            save_user_data(user_id, user_data)

            avg_height = 175 if user_data['gender'] == 'male' else 162
            keyboard = [
                [InlineKeyboardButton(f"📏 Средний ({avg_height} см)", callback_data=f'height_avg_{avg_height}')],
                [InlineKeyboardButton("✏️ Своя цифра", callback_data='height_custom')]
            ]
            
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="📏 Теперь рост (см):",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif step == 2.5:  # Ввод роста
            height = int(text)
            if not 100 <= height <= 220:
                raise ValueError
            user_data['height'] = height
            user_data['setup_step'] = 0
            save_user_data(user_id, user_data)

            water_norm = get_water_norm(user_data)

            final_text = (
                f"✅ Настройка завершена!\n\n"
                f"👤 Пол: {'Мужской' if user_data['gender'] == 'male' else 'Женский'}\n"
                f"⚖️ Вес: {user_data['weight']} кг\n"
                f"📏 Рост: {height} см\n\n"
                f"💧 Норма воды: {water_norm} мл/день\n\n"
                f"👇 Теперь выбирай действие в меню"
            )

            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=final_text,
                reply_markup=None
            )
            
            await send_photo_optimized(
                context,
                update.effective_chat.id,
                'welcome',
                "🎉 Настройка завершена!",
                MAIN_MENU
            )
    except ValueError:
        await update.message.reply_text("❌ Введи нормальное число!")
    except Exception as e:
        logger.error(f"❌ Ошибка handle_text_input: {e}")
        await update.message.reply_text("❌ Что-то пошло не так. Попробуй ещё раз.")

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка главного меню"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    user_data = check_and_reset_water(user_data)
    save_user_data(user_id, user_data)
    
    if not user_data or user_data.get('gender') is None:
        await update.message.reply_text("👴 Сначала настрой меня — /start")
        return

    text = update.message.text.strip()
    advice = random.choice(DEDS_ADVICE)

    try:
        if text == "💧 Пить воду":
            water_norm = get_water_norm(user_data)
            today = user_data.get('today_water_ml', 0)
            if isinstance(today, str):
                try:
                    today = int(today)
                except:
                    today = 0
            
            msg = (
                f"💧 СКОЛЬКО ВЫПИЛ?\n\n"
                f"Сегодня выпито: {today} мл\n"
                f"Норма: {water_norm} мл\n\n"
                f"Введи число (мл), сколько выпил сейчас.\n"
                f"Например: 250, 300, 500"
            )
            await send_photo_optimized(
                context,
                update.effective_chat.id,
                'water',
                msg
            )
            context.user_data['awaiting_water'] = True

        elif text == "🏋️ План тренировок":
            keyboard = [
                [InlineKeyboardButton("👶 Начальный", callback_data='plan_beginner')],
                [InlineKeyboardButton("🔥 Средний", callback_data='plan_intermediate')],
                [InlineKeyboardButton("⚡ Продвинутый", callback_data='plan_advanced')]
            ]
            await send_photo_optimized(
                context,
                update.effective_chat.id,
                'plan',
                "🏋️ ВЫБЕРИ УРОВЕНЬ ПОДГОТОВКИ\n\nВыбери уровень:",
                InlineKeyboardMarkup(keyboard)
            )

        elif text == "❓ Помощь":
            help_text = (
                "📚 ПОМОЩЬ ПО БОТУ\n\n"
                "🔹 💧 Пить воду — введи количество выпитой воды\n"
                "🔹 🏋️ План тренировок — программы по уровням\n"
                "🔹 🌙 Ложиться спать — таймер сна, потом нажми 👀 Проснулся\n"
                "🔹 🏆 Достижения — награды за активность\n"
                "🔹 🛒 Магазин Деда — премиум функции (скоро)\n"
                "🔹 Команда /wake — быстро проснуться\n\n"
                "⏰ Дед напоминает о воде каждые 2 часа\n\n"
                "🏆 ДОСТИЖЕНИЯ:\n"
                f"• {ACHIEVEMENTS['water_first']['how_to_get']}\n"
                f"• {ACHIEVEMENTS['water_3_days']['how_to_get']}\n"
                f"• {ACHIEVEMENTS['sleep_5']['how_to_get']}\n"
                f"• {ACHIEVEMENTS['workout_3']['how_to_get']}\n"
                f"• {ACHIEVEMENTS['veteran']['how_to_get']}"
            )
            await send_photo_optimized(
                context,
                update.effective_chat.id,
                'help',
                f"{help_text}\n\n{advice}"
            )

        elif text == "🌙 Ложиться спать":
            if user_data.get('sleep_start') is None:
                user_data['sleep_start'] = datetime.datetime.now()
                save_user_data(user_id, user_data)

                keyboard = [[InlineKeyboardButton("👀 Я проснулся", callback_data='woke_up')]]
                await send_photo_optimized(
                    context,
                    update.effective_chat.id,
                    'sleep',
                    f"🌙 Спокойной ночи! Заснул в {datetime.datetime.now().strftime('%H:%M')}",
                    InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text("😴 Ты уже спишь, не дёргайся!")

        elif text == "🏆 Достижения":
            achievements = user_data.get('achievements', [])
            if isinstance(achievements, str):
                try:
                    achievements = json.loads(achievements)
                except:
                    achievements = []
            
            msg = "🏆 ТВОИ ДОСТИЖЕНИЯ\n\n"
            
            # Сначала показываем полученные
            if achievements:
                msg += "✅ ПОЛУЧЕННЫЕ:\n"
                for ach in achievements:
                    if ach in ACHIEVEMENTS:
                        msg += f"  {ACHIEVEMENTS[ach]['emoji']} {ACHIEVEMENTS[ach]['name']}\n"
                msg += "\n"
            
            # Показываем все доступные
            msg += "📋 ДОСТУПНЫЕ ДОСТИЖЕНИЯ:\n"
            for key, ach in ACHIEVEMENTS.items():
                if key not in achievements:
                    msg += f"  {ach['emoji']} {ach['name']}\n    {ach['how_to_get']}\n\n"
            
            await send_photo_optimized(
                context,
                update.effective_chat.id,
                'motivation',
                f"{msg}\n\n{advice}"
            )

        elif text == "🛒 Магазин Деда":
            keyboard = [[InlineKeyboardButton("💎 Премиум-подписка", callback_data='subscription')]]
            await send_photo_optimized(
                context,
                update.effective_chat.id,
                'help',
                "🛒 МАГАЗИН ДЕДА\n\nСкоро здесь будут премиум-функции!",
                InlineKeyboardMarkup(keyboard)
            )

    except Exception as e:
        logger.error(f"❌ Ошибка в меню: {e}")
        await update.message.reply_text("❌ Что-то пошло не так. Попробуй ещё раз.")

async def handle_water_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обработка ввода количества воды"""
    if not context.user_data.get('awaiting_water'):
        return False
    
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    user_data = check_and_reset_water(user_data)
    
    try:
        water_ml = int(update.message.text.strip())
        if water_ml < 50 or water_ml > 2000:
            await update.message.reply_text("❌ Введи число от 50 до 2000 мл!")
            context.user_data['awaiting_water'] = False
            return True
        
        # Преобразуем today_water_ml в число, если оно строка
        today_water = user_data.get('today_water_ml', 0)
        if isinstance(today_water, str):
            try:
                today_water = int(today_water)
            except:
                today_water = 0
        
        # Обновляем статистику
        user_data['today_water_ml'] = today_water + water_ml
        user_data['total_water_drinks'] = user_data.get('total_water_drinks', 0) + 1
        user_data['last_water'] = datetime.datetime.now()
        
        # Обновляем streak
        today = datetime.datetime.now().date()
        last_date = user_data.get('last_water_date')
        if last_date:
            if isinstance(last_date, str):
                try:
                    last_date = datetime.datetime.fromisoformat(last_date).date()
                except:
                    last_date = None
            else:
                last_date = last_date.date()
            
            if last_date and (today - last_date).days == 1:
                user_data['water_streak'] = user_data.get('water_streak', 0) + 1
            elif last_date and (today - last_date).days == 0:
                pass
            else:
                user_data['water_streak'] = 1
        else:
            user_data['water_streak'] = 1
        
        user_data['last_water_date'] = datetime.datetime.now()
        
        # Проверяем достижения
        new_achievements = check_achievements(user_id, user_data)
        
        save_user_data(user_id, user_data)
        
        # Проверяем норму
        water_norm = get_water_norm(user_data)
        today_total = user_data['today_water_ml']
        
        if today_total >= water_norm:
            msg = f"✅ Норма выполнена! Сегодня выпито {today_total} мл из {water_norm} мл\nМолодец, но много пить не нужно!"
        else:
            msg = f"✅ Записано: +{water_ml} мл\nСегодня выпито: {today_total} из {water_norm} мл\nОсталось: {water_norm - today_total} мл"
        
        await update.message.reply_text(msg)
        
        # Если есть новые достижения, показываем
        if new_achievements:
            achiev_msg = "🎉 НОВЫЕ ДОСТИЖЕНИЯ!\n\n"
            for ach in new_achievements:
                if ach in ACHIEVEMENTS:
                    achiev_msg += f"{ACHIEVEMENTS[ach]['emoji']} {ACHIEVEMENTS[ach]['name']}\n"
            await update.message.reply_text(achiev_msg)
        
        # Отправляем мотивацию
        advice = random.choice(DEDS_ADVICE)
        await send_photo_optimized(
            context,
            update.effective_chat.id,
            'drank',
            f"💬 {advice}"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Введи число (мл)!")
    
    context.user_data['awaiting_water'] = False
    return True

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка инлайн-кнопок"""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    logger.info(f"🔘 Нажата кнопка: {query.data} от {user_id}")

    user_data = get_user_data(user_id)
    if not user_data:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Ошибка. Нажми /start"
        )
        return

    now = datetime.datetime.now()

    try:
        # КНОПКА ПРОСНУЛСЯ
        if query.data == 'woke_up':
            if user_data.get('sleep_start'):
                sleep_start = user_data['sleep_start']
                if isinstance(sleep_start, str):
                    try:
                        sleep_start = datetime.datetime.fromisoformat(sleep_start)
                    except:
                        sleep_start = now
                
                duration = now - sleep_start
                hours = duration.seconds // 3600
                minutes = (duration.seconds % 3600) // 60

                user_data['total_sleep_seconds'] = user_data.get('total_sleep_seconds', 0) + duration.seconds
                user_data['total_sleeps'] = user_data.get('total_sleeps', 0) + 1
                user_data['sleep_start'] = None
                
                # Проверяем достижения
                new_achievements = check_achievements(user_id, user_data)
                
                save_user_data(user_id, user_data)

                total_hours = user_data['total_sleep_seconds'] // 3600
                total_min = (user_data['total_sleep_seconds'] % 3600) // 60

                msg = f"🌅 Проснулся! Спал {hours} ч {minutes} мин\n📊 Всего сна: {total_hours} ч {total_min} мин"
                
                # Отправляем новое сообщение вместо редактирования
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=msg
                )
                
                # Если есть новые достижения, показываем
                if new_achievements:
                    achiev_msg = "🎉 НОВЫЕ ДОСТИЖЕНИЯ!\n\n"
                    for ach in new_achievements:
                        if ach in ACHIEVEMENTS:
                            achiev_msg += f"{ACHIEVEMENTS[ach]['emoji']} {ACHIEVEMENTS[ach]['name']}\n"
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=achiev_msg
                    )
                
                await send_photo_optimized(
                    context,
                    update.effective_chat.id,
                    'woke_up',
                    f"💬 {random.choice(DEDS_ADVICE)}"
                )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❓ Ты и не ложился ещё!"
                )

        # КНОПКИ ПЛАНОВ ТРЕНИРОВОК
        elif query.data in ['plan_beginner', 'plan_intermediate', 'plan_advanced']:
            # Определяем уровень
            if query.data == 'plan_beginner':
                plan = TRAINING_PLANS['beginner']
            elif query.data == 'plan_intermediate':
                plan = TRAINING_PLANS['intermediate']
            else:
                plan = TRAINING_PLANS['advanced']
            
            msg = f"{plan['name']}\n{plan['description']}\n\n"
            for day, exercises in plan.items():
                if day not in ['name', 'description']:
                    msg += f"📅 {day}:\n{exercises}\n\n"
            
            keyboard = [[InlineKeyboardButton("✅ Завершил тренировку", callback_data='workout_done')]]
            
            # Отправляем новое сообщение
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=msg,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        # КНОПКА ТРЕНИРОВКА ВЫПОЛНЕНА
        elif query.data == 'workout_done':
            user_data['workouts_done'] = user_data.get('workouts_done', 0) + 1
            
            # Проверяем достижения
            new_achievements = check_achievements(user_id, user_data)
            
            save_user_data(user_id, user_data)
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="✅ Отлично потренировался!"
            )
            
            # Если есть новые достижения, показываем
            if new_achievements:
                achiev_msg = "🎉 НОВЫЕ ДОСТИЖЕНИЯ!\n\n"
                for ach in new_achievements:
                    if ach in ACHIEVEMENTS:
                        achiev_msg += f"{ACHIEVEMENTS[ach]['emoji']} {ACHIEVEMENTS[ach]['name']}\n"
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=achiev_msg
                )
            
            await send_photo_optimized(
                context,
                update.effective_chat.id,
                'motivation',
                f"💬 {random.choice(DEDS_ADVICE)}"
            )

        # КНОПКА ПОДПИСКИ
        elif query.data == 'subscription':
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="💎 ПРЕМИУМ-ПОДПИСКА\n\n⚡ Будет доступна совсем скоро!\nСледи за обновлениями 👀"
            )

    except Exception as e:
        logger.error(f"🔥 Ошибка в button_handler: {e}")
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Что-то пошло не так. Попробуй ещё раз."
            )
        except:
            pass

async def hourly_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ежечасные напоминания о воде"""
    now = datetime.datetime.now()
    
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT user_id, last_water, sleep_start FROM users WHERE last_water IS NOT NULL")
            rows = c.fetchall()

        for user_id, last_water_str, sleep_start_str in rows:
            try:
                if sleep_start_str:
                    sleep_start = datetime.datetime.fromisoformat(sleep_start_str)
                    if (now - sleep_start) < datetime.timedelta(hours=8):
                        continue
                
                if last_water_str:
                    last_water = datetime.datetime.fromisoformat(last_water_str)
                    if (now - last_water) > datetime.timedelta(hours=2):
                        await context.bot.send_message(
                            chat_id=user_id,
                            text="💧 Дед напоминает: пора выпить воды! (нажми 💧 Пить воду и введи количество)"
                        )
            except Exception as e:
                logger.warning(f"⚠️ Ошибка напоминания для {user_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Ошибка в hourly_reminder: {e}")

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Главный обработчик текста"""
    # Сначала проверяем, не ввод ли это количества воды
    if await handle_water_input(update, context):
        return
    
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)

    if user_data and user_data.get('setup_step', 0) > 0:
        await handle_text_input(update, context)
    else:
        await handle_menu(update, context)

# ========== ЗАПУСК ==========
def main():
    print("="*60)
    print("🚀 ЗАПУСК БОТА «ТВОЙ ДЕД»")
    print("="*60)
    print(f"📁 База данных: {DB_FILE}")
    print(f"📁 Папка с картинками: {IMAGES_FOLDER}")
    
    print("\n🔍 ПРОВЕРКА КАРТИНОК:")
    for key, filename in PHOTO_FILES.items():
        path = os.path.join(IMAGES_FOLDER, filename)
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"✅ {filename}: {size} байт")
        else:
            print(f"❌ {filename} не найден!")
    
    print("="*60)

    try:
        application = Application.builder().token(TOKEN).build()

        # Обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("wake", wake_command))
        application.add_handler(CallbackQueryHandler(setup_callback, pattern=r'^(gender|weight|height)_'))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

        # Планировщик напоминаний (каждый час)
        application.job_queue.run_repeating(hourly_reminder, interval=3600, first=60)

        print("\n✅ Бот успешно запущен! Нажми Ctrl+C для остановки")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        print(f"\n❌ ОШИБКА ЗАПУСКА: {e}")
        traceback.print_exc()
        print("\nНажми Enter для выхода...")
        input()

if __name__ == '__main__':
    main()