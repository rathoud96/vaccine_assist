import json
import logging
import os
from datetime import datetime

import pytz
import redis
import requests
import telegram
from dotenv import load_dotenv
from flask import Flask
from telegram import Bot, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    CallbackContext,
    CommandHandler,
    ConversationHandler,
    Filters,
    MessageHandler,
    Updater,
)

from app.scheduler import scheduler

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logger = logging.getLogger(__name__)

global TOKEN
global r

load_dotenv()


VACCINE, AGE = range(2)

TOKEN = os.environ["TOKEN"]

# PORT = os.environ.get("PORT", "8443")

app = Flask(__name__)


def send(msg, chat_id, token=TOKEN):
    """
    Send a mensage to a telegram user specified on chatId
    chat_id must be a number!
    """
    bot = Bot(token=token)
    bot.sendMessage(chat_id=chat_id, text=msg)


def start(update, _):
    reply_keyboard = [[18, 45]]
    update.message.reply_text(
        "Hello! My name is Kakashi.\n"
        "I will help you to notify for vaccination slots in your city.\n"
        "Please select your age group",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )

    return AGE


def get_user_data():
    data = r.hgetall(name="vaccine_users")
    chat_ids = data.keys()

    for chat_id in chat_ids:
        pin_age_data = json.loads(data[chat_id])
        pincode = pin_age_data["pincode"]
        min_age_limit = int(pin_age_data["min_age_limit"])
        check_for_slots(pincode, min_age_limit, chat_id)


def check_for_slots(pin_code, min_age_limit, chat_id):
    data = get_vaccine_data(pin_code)
    filter_based_on_age_group(chat_id, data, min_age_limit)


def age(update, context):
    context.user_data["min_age_limit"] = update.message.text

    update.message.reply_text("Please enter valid pincode")

    return VACCINE


def invalid_pin(update, context):
    update.message.reply_text(
        "Oops! Seems like you have entered invalid pincode, please enter valid one."
    )

    return VACCINE


def vaccine_slot(update, context):
    pin_code = update.message.text
    response = requests.get(f"https://api.postalpincode.in/pincode/{pin_code}")
    status = json.loads(response.text)[0]["Status"]
    if status == "Success":
        chat_id = update.message.chat.id
        r.hset(
            name="vaccine_users",
            key=chat_id,
            value=json.dumps(
                {
                    "pincode": pin_code,
                    "min_age_limit": context.user_data["min_age_limit"],
                    "is_notify": True,
                }
            ),
        )
        context.user_data["pincode"] = pin_code
        data = get_vaccine_data(pin_code)
        is_slots_available = filter_based_on_age_group(
            chat_id, data, context.user_data["min_age_limit"]
        )
        if not is_slots_available:
            message = "Sorry! Could not find any slots for you.\nI will notify you as soon as slots get available."
            send(message, chat_id)
        return ConversationHandler.END
    else:
        invalid_pin(update, context)


def get_vaccine_data(pincode):
    tz_NY = pytz.timezone("Asia/Kolkata")
    datetime_NY = datetime.now(tz_NY)
    header = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36"
    }
    url = f'https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByPin?pincode={pincode}&date={datetime_NY.strftime("%d-%m-%Y")}'
    response = requests.get(url, headers=header)
    logger.info(response)

    return json.loads(response.text)


def filter_based_on_age_group(chat_id, data, age_group, is_slots_avalable=False):
    for center in data["centers"]:
        for session in center["sessions"]:
            min_age_limit = session["min_age_limit"]
            if age_group == min_age_limit and session["available_capacity"] > 0:
                is_slots_avalable = True
                message = f'In {center["name"]} on date {session["date"]} available_capacity is {session["available_capacity"]} for age group {min_age_limit}'
                send(message, chat_id)
    return is_slots_avalable


def cancel(update, _):
    update.message.reply_text("Bye bye!!!, see you soon")

    return ConversationHandler.END


def stop(update, context):
    chat_id = update.message.chat_id
    r.hset(
        name="vaccine_users",
        key=chat_id,
        value=json.dumps(
            {
                "pincode": context.user_data["pincode"],
                "min_age_limit": context.user_data["min_age_limit"],
                "is_notify": False,
            }
        ),
    )
    update.message.reply_text("Bye bye!!!, see you soon")

    return ConversationHandler.END


def home():
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AGE: [MessageHandler(Filters.regex("^(18|45)$"), age)],
            VACCINE: [
                MessageHandler(Filters.regex("^[1-9][0-9]{5}$"), vaccine_slot),
                MessageHandler(
                    Filters.regex("\d{1}|\d{2}|\d{3}|\d{4}|[a-z]"), invalid_pin
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    dp.add_handler(CommandHandler("stop", stop))
    dp.add_handler(conv_handler)
    # app_name = os.environ['APP_NAME']
    # updater.start_webhook(listen="0.0.0.0",
    #                       port=PORT,
    #                       url_path=TOKEN,
    #                       webhook_url='https://'+ app_name + '.herokuapp.com/' + TOKEN)
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    r = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    scheduler(get_user_data)
    home()
