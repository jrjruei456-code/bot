import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from datetime import datetime
from typing import Dict

# ================= НАСТРОЙКИ =================
TOKEN = "8653515267:AAE7RcmGh6FL5S6hY7KDqugf0yMpBbWz5Lo"
ADMIN_IDS = [5847729581, 222222222]  # список ID админов
CHANNEL_ID = -1003754542956          # ID канала
# =============================================

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())

post_counter = 0
user_posts: Dict[int, dict] = {}          # все посты
pending_reject: Dict[int, int] = {}       # {admin_id: post_id} для отклонений
pending_schedule: Dict[int, int] = {}     # {admin_id: post_id} для планирования

# ================= СТАРТ =================
@dp.message(lambda message: message.text == "/start")
async def start(message: Message):
    await message.answer("Отправьте псиоп для публикации.")

# ================= ПРИЁМ НОВОГО КОНТЕНТА =================
async def receive_content(message: Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer("Админы не могут отправлять посты.")
        return

    global post_counter
    post_counter += 1
    post_id = post_counter

    # текст берём из text или caption
    text = message.text or message.caption or ""
    photo = message.photo[-1].file_id if message.photo else None
    video = message.video.file_id if message.video else None

    user_posts[post_id] = {
        "user_id": message.from_user.id,
        "text": text,
        "photo": photo,
        "video": video,
        "status": "pending"
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Анонимно", callback_data=f"anon_{post_id}"),
            InlineKeyboardButton(text="Публично", callback_data=f"sign_{post_id}")
        ]
    ])
    await message.answer("Хотите ли вы публично оповестить мировое сообщество о вашем заговоре?", reply_markup=kb)

# ================= ВЫБОР ПОДПИСИ =================
@dp.callback_query(F.data.startswith(("anon_", "sign_")))
async def choose_signature(callback: CallbackQuery):
    action, post_id = callback.data.split("_")
    post_id = int(post_id)

    post = user_posts.get(post_id)
    if not post or post["status"] != "pending":
        await callback.answer("Пост уже обработан.")
        return

    user = callback.from_user
    post["real_sender"] = f"@{user.username}" if user.username else user.full_name
    signature = f"\n\n— {post['real_sender']}" if action == "sign" else "\n\n— Анонимно"
    post["final_text"] = post.get("text", "") + signature

    # удаляем кнопки у пользователя
    await callback.message.edit_reply_markup(reply_markup=None)

    # клавиатура для админа
    admin_text = f"{post['final_text']}\n\nОтправитель: {post['real_sender']}"
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton(text="🕒 Назначить время", callback_data=f"schedule_{post_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{post_id}")
        ]
    ])

    for admin_id in ADMIN_IDS:
        if post.get("video"):
            await bot.send_video(admin_id, video=post["video"], caption=admin_text, reply_markup=admin_kb)
        elif post.get("photo"):
            await bot.send_photo(admin_id, photo=post["photo"], caption=admin_text, reply_markup=admin_kb)
        else:
            await bot.send_message(admin_id, admin_text, reply_markup=admin_kb)

    await callback.message.answer("Ваш псиоп в скором времени рассмотрят мировые элиты.")
    await callback.answer()

# ================= МГНОВЕННАЯ ПУБЛИКАЦИЯ =================
@dp.callback_query(F.data.startswith("approve_"))
async def approve_post(callback: CallbackQuery):
    post_id = int(callback.data.split("_")[1])
    post = user_posts.get(post_id)
    if not post or post["status"] != "pending":
        await callback.answer("Уже обработано.")
        return

    await publish_post(post)
    post["status"] = "approved"

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Пост опубликован.")
    await callback.answer()

# ================= НАЗНАЧЕНИЕ ВРЕМЕНИ =================
@dp.callback_query(F.data.startswith("schedule_"))
async def schedule_post(callback: CallbackQuery):
    post_id = int(callback.data.split("_")[1])
    post = user_posts.get(post_id)
    if not post or post["status"] != "pending":
        await callback.answer("Уже обработано.")
        return

    admin_id = callback.from_user.id
    pending_schedule[admin_id] = post_id

    await callback.message.answer(
        f"Вы назначаете время для поста от {post.get('real_sender','неизвестного')}.\n"
        "Введите дату и время публикации в формате DD.MM.YYYY HH:MM\n"
        "Пример: 25.12.2026 18:30"
    )
    await callback.answer()

# ================= ПУБЛИКАЦИЯ С ОТЛОЖКОЙ =================
async def delayed_publish(post, delay):
    await asyncio.sleep(delay)
    await publish_post(post)
    post["status"] = "approved"

# ================= ПУБЛИКАЦИЯ =================
async def publish_post(post):
    bot_username = (await bot.get_me()).username
    final_text = f"{post.get('final_text','')}\n\nПсиоп был опубликован при помощи @{bot_username}"

    if post.get("video"):
        await bot.send_video(CHANNEL_ID, video=post["video"], caption=final_text)
    elif post.get("photo"):
        await bot.send_photo(CHANNEL_ID, photo=post["photo"], caption=final_text)
    else:
        await bot.send_message(CHANNEL_ID, final_text)

# ================= ОТКЛОНЕНИЕ =================
@dp.callback_query(F.data.startswith("reject_"))
async def reject_post(callback: CallbackQuery):
    post_id = int(callback.data.split("_")[1])
    post = user_posts.get(post_id)
    if not post or post["status"] != "pending":
        await callback.answer("Уже обработано.")
        return

    admin_id = callback.from_user.id
    pending_reject[admin_id] = post_id

    await callback.message.answer(
        f"Вы отклоняете пост от {post.get('real_sender','неизвестного')}.\n"
        "Напишите причину отказа:"
    )
    await callback.answer()

# ================= ОБРАБОТКА СООБЩЕНИЙ АДМИНА =================
@dp.message()
async def admin_messages(message: Message):
    admin_id = message.from_user.id

    # отклонение
    post_id_reject = pending_reject.get(admin_id)
    if post_id_reject:
        post = user_posts.get(post_id_reject)
        if post:
            post["status"] = "rejected"
            try:
                await bot.send_message(post["user_id"], f"Ваш пост отклонён.\nПричина: {message.text}")
            except:
                pass
        await message.answer("Пользователь уведомлён. Пост отклонён.")
        pending_reject.pop(admin_id, None)
        return

    # планирование времени
    post_id_schedule = pending_schedule.get(admin_id)
    if post_id_schedule:
        post = user_posts.get(post_id_schedule)
        if not post:
            pending_schedule.pop(admin_id, None)
            return

        try:
            publish_time = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        except ValueError:
            await message.answer("Неверный формат. Попробуйте снова.")
            return

        delay = (publish_time - datetime.now()).total_seconds()
        if delay <= 0:
            await message.answer("Время должно быть в будущем.")
            return

        post["status"] = "scheduled"
        asyncio.create_task(delayed_publish(post, delay))

        await message.answer("Пост поставлен в очередь на указанное время.")
        pending_schedule.pop(admin_id, None)
        return

    # обычная заявка от пользователя
    if message.from_user.id not in ADMIN_IDS:
        await receive_content(message)

# ================= ЗАПУСК =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
