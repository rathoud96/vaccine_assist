from flask import Flask
import requests
import telegram
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext)

from datetime import datetime  
import json  
from time import sleep
import pytz 
from apscheduler.schedulers.background import BackgroundScheduler
import redis
from dotenv import load_dotenv
import os
import logging

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

global TOKEN
global r

load_dotenv()


VACCINE, AGE = range(2)

TOKEN = os.environ['TOKEN']

PORT = int(os.environ.get('PORT', '8443'))

app = Flask(__name__)

def get_image(type): 
    url = f'https://source.unsplash.com/1600x900/?{type}'
    return url

def send(msg, chat_id, token=TOKEN):
	"""
	Send a mensage to a telegram user specified on chatId
	chat_id must be a number!
	"""
	bot = telegram.Bot(token=token)
	bot.sendMessage(chat_id=chat_id, text=msg)

def start(update, _): 
    reply_keyboard = [[18, 45]]
    update.message.reply_text("Hello! My name is Magna.\n"
    "I will help you to notify for vaccination slots in your city.\n"
    "Please select your age group",
    reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )

    return AGE

def get_user_data():
    data = r.hgetall(name="vaccine_users")
    print(data)
    chat_ids = data.keys()

    for chat_id in chat_ids:
        pin_age_data = json.loads(data[chat_id])
        pincode = pin_age_data['pincode']
        min_age_limit = int(pin_age_data['min_age_limit'])
        check_for_slots(pincode, min_age_limit, chat_id)


def check_for_slots(pin_code, min_age_limit, chat_id):
    tz_NY = pytz.timezone('Asia/Kolkata')   
    datetime_NY = datetime.now(tz_NY)
    todays_date = datetime_NY.strftime("%d-%m-%Y")
    url = f'https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByPin?pincode={pin_code}&date={todays_date}'

    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'})
    data = json.loads(response.text)
    for center in data["centers"]:
        center_name = center["name"]
        for session in center["sessions"]:
            session["min_age_limit"]
            if min_age_limit == session["min_age_limit"] and session["available_capacity"] > 0:
                message = f'In {center_name} on date {session["date"]} available_capacity is {session["available_capacity"]} for age group {min_age_limit}'
                send(message, chat_id)

def age(update, context):
    context.user_data['min_age_limit'] = update.message.text

    update.message.reply_text("Please enter valid pincode")

    return VACCINE

def vaccine_slot(update, context):
    tz_NY = pytz.timezone('Asia/Kolkata')   
    datetime_NY = datetime.now(tz_NY)
    todays_date = datetime_NY.strftime("%d-%m-%Y")
    pin_code = update.message.text
    r.hset(name="vaccine_users", key=update.message.chat.id, value=json.dumps({'pincode': pin_code, 'min_age_limit': context.user_data['min_age_limit']}))
    context.user_data['pincode'] = pin_code
    header = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
            }
    url = f'https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByPin?pincode={pin_code}&date={todays_date}'

    response = requests.get(url, headers=header)
    print(response)
    data = json.loads(response.text)
    count = 0
    for center in data["centers"]:
        center_name = center["name"]
        for session in center["sessions"]:
            min_age_limit= session["min_age_limit"]
            if int(context.user_data['min_age_limit']) == min_age_limit and session["available_capacity"] > 0:
                count = 1
                message = f'In {center_name} on date {session["date"]} available_capacity is {session["available_capacity"]} for age group {min_age_limit}'
                update.message.reply_text(message)
    if count == 0:
        update.message.reply_text("Sorry! We could not find any slots for you\n"
                "I will notify you as soon as slots get available")
    return ConversationHandler.END


def cancel(update, _):
    update.message.reply_text('Bye bye!!!, see you soon')

    return ConversationHandler.END

@app.route("/")
def index():
    return "Running"

def home():
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AGE: [MessageHandler(Filters.regex('^(18|45)$'), age)],
            VACCINE: [MessageHandler(Filters.regex("\d{5}"), vaccine_slot)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    dp.add_handler(conv_handler)
    app_name = os.environ['APP_NAME']
    updater.start_webhook(listen="0.0.0.0",
                          port=PORT,
                          url_path=TOKEN,
                          webhook_url='https://'+ app_name + '.herokuapp.com/' + TOKEN)
    # updater.start_polling()
    updater.idle()
  
if __name__ == "__main__":
    print("started")
    r = redis.from_url(os.environ['REDIS_URL'], decode_responses=True)
    scheduler = BackgroundScheduler()
    scheduler.add_job(get_user_data, 'interval', seconds=60)
    scheduler.start()
    # print('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))

    # try:
    #     # This is here to simulate application activity (which keeps the main thread alive).
    #     while True:
    #         sleep(2)
    # except (KeyboardInterrupt, SystemExit):
    #     # Not strictly necessary if daemonic mode is enabled but should be done if possible
    #     scheduler.shutdown()
    home()