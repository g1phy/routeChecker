import datetime
import logging
import threading
import requests
from bs4 import BeautifulSoup
import urllib3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    CallbackContext, MessageHandler, Filters
)

token = ""

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

help_text = """🍗 Список доступных команд:

/add — добавить новое отслеживание
/list — посмотреть текущие отслеживания"""

state_login, state_choosing_from, state_choosing_to, state_day, state_time = range(5)

list_routes = {'Минск': '1', 'Слуцк': '85', 'Солигорск': '88', 'Бобруйск': '7'}
list_for_check = []
weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
UPDATE_TIME = 60
COUNT_ROUTES = 1


def gettext(cnt):
    return "свободное место" if cnt == 1 else ("свободного места" if cnt < 5 else "свободных мест")


def goodTime(time_cur, time_):
    hour_from, hour_to, minute_from, minute_to = time_

    hour, minute = map(int, time_cur.split(':'))

    if hour == hour_from == hour_to:
        return minute_from <= minute <= minute_to

    if hour == hour_from and minute_from <= minute < 60:
        return True

    if hour == hour_to and 0 <= minute <= minute_to:
        return True

    return hour_from < hour < hour_to


def check_it():
    global list_for_check
    id_for_delete = []
    current = 0

    url = 'https://route.by/local/components/route/user.order/templates/.default/ajax.php'
    for _id, city_from, city_to, date, time_, user in list_for_check:
        if not _id:
            continue
        if (datetime.datetime.strptime(date, '%d.%m.%Y') + datetime.timedelta(1)) < datetime.datetime.now():
            id_for_delete.append(current)
            current += 1
            continue

        body = {'type': 'load_list_order', 'select_in': list_routes[city_from],
                'select_out': list_routes[city_to], 'date': date}
        req = requests.post(url, data=body, verify=False)

        soup = BeautifulSoup(req.json()['alert'], "html.parser")

        for time in soup.find_all(attrs={'class': 'list_order_line'}):
            time_cur = time.find(attrs={'class': 'lol_time'}).text
            if not goodTime(time_cur, time_):
                continue
            time_cnt = int(time.find(attrs={'class': 'lol_driver_space_num'}).text)
            if time_cnt > 0:
                user.send_message(f'📛🌊 Ахтунг! По маршруту {city_from} - {city_to} ({date}) на время {time_cur} '
                                  f'есть {time_cnt} '
                                  f'{gettext(time_cnt)}')
        current += 1

    for i in id_for_delete:
        print(f"We found passed {i}, deleting...")
        list_for_check[i] = [0, 0, 0, 0, 0, 0]

    threading.Timer(UPDATE_TIME, check_it).start()


def start(update: Update, _: CallbackContext) -> int:
    update.message.reply_text("Используйте /help для просмотра списка команд")

    return state_login


def handler_from(update: Update, _: CallbackContext) -> int:
    query = update.callback_query
    query.answer()

    keyboard = []
    current = []
    cnt = 1

    for i in list_routes:
        current.append(InlineKeyboardButton(i, callback_data=i))
        if not cnt % 3:
            keyboard.append(current)
            current = []
        cnt += 1
    if len(current) > 0:
        keyboard.append(current)

    reply_markup = InlineKeyboardMarkup(keyboard)

    _.user_data['city_from'] = query.data
    query.edit_message_text(text=f"☄️ Город отправления: {_.user_data['city_from']}\n⚡️ Выберите город прибытия:",
                            reply_markup=reply_markup)

    return state_choosing_to


def handler_to(update: Update, _: CallbackContext) -> int:
    query = update.callback_query
    query.answer()

    _.user_data['city_to'] = query.data

    reply_markup = InlineKeyboardMarkup([
                                    [
                                          InlineKeyboardButton('Сегодня', callback_data='today'),
                                          InlineKeyboardButton('Завтра', callback_data='tomorrow'),
                                          InlineKeyboardButton('Послезавтра', callback_data='ttomorrow')
                                    ]
                            ])

    query.edit_message_text(text=f"☄️ Город отправления: {_.user_data['city_from']}\n"
                                 f"💫️ Город прибытия: {_.user_data['city_to']}\nВыберите дату: ",
                            reply_markup=reply_markup)

    return state_day


def handler_day(update: Update, _: CallbackContext) -> int:
    query = update.callback_query
    query.answer()

    date = datetime.datetime.now()

    if query.data == 'tomorrow':
        date += datetime.timedelta(1)
    elif query.data == 'ttomorrow':
        date += datetime.timedelta(2)

    _.user_data['date'] = date.strftime('%d.%m.%Y')

    query.edit_message_text(text=f"☄️ Город отправления: {_.user_data['city_from']}\n"
                                 f"💫️ Город прибытия: {_.user_data['city_to']}\n"
                                 f"💥 День отправления: {date.strftime('%d.%m')} ({weekdays[date.weekday()]})\n"
                                 f"✨ Выберите время отправления. Примеры: 16:30; 16:30-18:30")

    return state_time


def handler_time(update: Update, _: CallbackContext) -> int:
    global COUNT_ROUTES
    text = update.message.text

    time = text.split('-')
    cnt_ = 0

    if len(time) < 2:
        if len(time[0].split(':')) < 2:
            update.message.reply_text(text="Некорректное время (пример: 16:30 или 16:30-18:30)")
            return state_time
        time.append(time[0])

    hour_from = int(time[0].split(':')[0])
    hour_to = int(time[1].split(':')[0])
    minute_from = int(time[0].split(':')[1])
    minute_to = int(time[1].split(':')[1])

    while hour_from < hour_to or (hour_from <= hour_to and minute_from <= minute_to):
        cnt_ += 1
        minute_from += 5
        if minute_from >= 60:
            minute_from %= 60
            hour_from += 1

    if not cnt_:
        update.message.reply_text(text="Некорректное время (пример: 16:30 или 16:30-18:30, полночь как 24:00)")
        return state_time

    hour_from = int(time[0].split(':')[0])
    minute_from = int(time[0].split(':')[1])

    list_for_check.append([COUNT_ROUTES,
                           _.user_data['city_from'],
                           _.user_data['city_to'],
                           _.user_data['date'],
                           [hour_from, hour_to, minute_from, minute_to],
                           update.message.from_user])

    COUNT_ROUTES += 1

    date = datetime.datetime.strptime(_.user_data['date'], '%d.%m.%Y')

    update.message.reply_text(text=f"☘️ Успешно добавлено! \n"
                                   f"☄️ Город отправления: {_.user_data['city_from']}\n"
                                   f"💫️ Город прибытия: {_.user_data['city_to']}\n"
                                   f"💥 День отправления: {date.strftime('%d.%m')} ({weekdays[date.weekday()]})\n"
                                   f"🌓 Список времён для проверки: "
                                   f"{str(hour_from).zfill(2)}:{str(minute_from).zfill(2)} - "
                                   f"{str(hour_to).zfill(2)}:{str(minute_to).zfill(2)}")

    _.user_data.clear()
    return state_login


def handler_delete(update: Update, _: CallbackContext) -> int:
    query = update.callback_query
    query.answer()

    idneed = int(query.data)

    try:
        list_for_check[idneed]
    except IndexError:
        query.edit_message_text(f'💮 При попытке удаления произошла ошибка #1.\nОбратитесь к системному администратору')
        return state_login

    if not list_for_check[idneed][0]:
        query.edit_message_text(f'💮 При попытке удаления произошла ошибка #2.\nОбратитесь к системному администратору')
        return state_login
    elif list_for_check[idneed][5].id != query.from_user.id:
        query.edit_message_text(f'💮 При попытке удаления произошла ошибка #3.\nОбратитесь к системному администратору')
        return state_login

    list_for_check[idneed] = [0, 0, 0, 0, 0, 0]
    query.edit_message_text(text=f"☘ Успешно удалено")

    return state_login


def help_command(update: Update, _: CallbackContext) -> int:
    update.message.reply_text(help_text)

    return state_login


def list_command(update: Update, _: CallbackContext) -> int:
    userID = update.message.from_user.id
    cnt = 0
    goodCnt = 0

    for i in list_for_check:
        cnt += 1
        if i[0] == 0:
            continue
        if i[5].id == userID:
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Перестать отслеживать",
                                                                       callback_data=str(cnt))]])

            date = datetime.datetime.strptime(i[3], '%d.%m.%Y')

            hour_from, hour_to, minute_from, minute_to = i[4]

            update.message.reply_text(f"💕 Маршрут №{i[0]}\n"
                                      f"☄️ Город отправления: {i[1]}\n"
                                      f"💫️ Город прибытия: {i[2]}\n"
                                      f"💥 День отправления: {date.strftime('%d.%m')} ({weekdays[date.weekday()]})\n"
                                      f"🌓 Список времён для проверки: "
                                      f"{str(hour_from).zfill(2)}:{str(minute_from).zfill(2)} - "
                                      f"{str(hour_to).zfill(2)}:{str(minute_to).zfill(2)}", reply_markup=reply_markup)

            goodCnt += 1
    if not goodCnt:
        update.message.reply_text('🛑 Ничего не найдено\nДля добавления используйте /add')

    return state_login


def add_command(update: Update, _: CallbackContext) -> int:
    keyboard = []
    current = []
    cnt = 1

    for i in list_routes:
        current.append(InlineKeyboardButton(i, callback_data=i))
        if not cnt % 3:
            keyboard.append(current)
            current = []
        cnt += 1
    if len(current) > 0:
        keyboard.append(current)

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text('Выберите точку отправления:', reply_markup=reply_markup)

    return state_choosing_from


def main() -> None:
    updater = Updater(token=token)
    dispatcher = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), CommandHandler('help', help_command),
                      CommandHandler('add', add_command), CommandHandler('list', list_command)],
        states={
            state_login: [
                CallbackQueryHandler(handler_delete)
                # For Delete
            ],
            state_choosing_from: [
                CallbackQueryHandler(handler_from),
            ],
            state_choosing_to: [
                CallbackQueryHandler(handler_to),
            ],
            state_day: [
                CallbackQueryHandler(handler_day),
            ],
            state_time: [
                MessageHandler(filters=Filters.all, callback=handler_time),
            ],
        },
        fallbacks=[CommandHandler('start', start), CommandHandler('help', help_command),
                   CommandHandler('add', add_command), CommandHandler('list', list_command)],
    )

    dispatcher.add_handler(conv_handler)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    urllib3.disable_warnings(UserWarning)
    check_it()
    main()
