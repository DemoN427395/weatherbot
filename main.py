import json
import os
import types
from dotenv import load_dotenv
import schedule
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from telebot import *
import requests as req
from geopy import geocoders, Nominatim
from datetime import *
import time
import sqlite3


load_dotenv()
#

TOKEN = os.getenv('TOKEN')
TOKEN_YANDEX = os.getenv('TOKEN_YANDEX')


bot = telebot.TeleBot(TOKEN)


connection = sqlite3.connect('my_database.db', check_same_thread=False)
cursor = connection.cursor()


cursor.execute('''
CREATE TABLE IF NOT EXISTS Cities (
"chat_id" INTEGER NOT NULL,
"city" TEXT,
"city_time" TEXT,
PRIMARY KEY("chat_id"))
''')


def geo_pos(city: str):
    geolocator = geocoders.Nominatim(user_agent="telebot")
    latitude = str(geolocator.geocode(city).latitude)
    longitude = str(geolocator.geocode(city).longitude)
    
    return latitude, longitude


def yandex_weather(latitude, longitude, TOKEN_YANDEX: str):
    url_yandex = f'https://api.weather.yandex.ru/v2/informers/?lat={latitude}&lon={longitude}&[lang=ru_RU]'
    yandex_req = req.get(url_yandex, headers={'X-Yandex-API-Key': TOKEN_YANDEX}, verify=False)
    conditions = {'clear': 'ясно', 'partly-cloudy': 'малооблачно', 'cloudy': 'облачно с прояснениями',
                  'overcast': 'пасмурно', 'drizzle': 'морось', 'light-rain': 'небольшой дождь',
                  'rain': 'дождь', 'moderate-rain': 'умеренно сильный', 'heavy-rain': 'сильный дождь',
                  'continuous-heavy-rain': 'длительный сильный дождь', 'showers': 'ливень',
                  'wet-snow': 'дождь со снегом', 'light-snow': 'небольшой снег', 'snow': 'снег',
                  'snow-showers': 'снегопад', 'hail': 'град', 'thunderstorm': 'гроза',
                  'thunderstorm-with-rain': 'дождь с грозой', 'thunderstorm-with-hail': 'гроза с градом'
                  }
    wind_dir = {'nw': 'северо-западное', 'n': 'северное', 'ne': 'северо-восточное', 'e': 'восточное',
                'se': 'юго-восточное', 's': 'южное', 'sw': 'юго-западное', 'w': 'западное', 'с': 'штиль'}

    yandex_json = json.loads(yandex_req.text)
    yandex_json['fact']['condition'] = conditions[yandex_json['fact']['condition']]
    yandex_json['fact']['wind_dir'] = wind_dir[yandex_json['fact']['wind_dir']]
    for parts in yandex_json['forecast']['parts']:
        parts['condition'] = conditions[parts['condition']]
        parts['wind_dir'] = wind_dir[parts['wind_dir']]

    pogoda = dict()
    params = ['condition', 'wind_dir', 'pressure_mm', 'humidity']
    for parts in yandex_json['forecast']['parts']:
        pogoda[parts['part_name']] = dict()
        pogoda[parts['part_name']]['temp'] = parts['temp_avg']
        for param in params:
            pogoda[parts['part_name']][param] = parts[param]

    pogoda['fact'] = dict()
    pogoda['fact']['temp'] = yandex_json['fact']['temp']
    for param in params:
        pogoda['fact'][param] = yandex_json['fact'][param]

    pogoda['link'] = yandex_json['info']['url']
    return pogoda


def print_yandex_weather(dict_weather_yandex, message):
    day = {'night': 'ночью', 'morning': 'утром', 'day': 'днем', 'evening': 'вечером', 'fact': 'сейчас'}
    bot.send_message(message.from_user.id, f'Погода на день:')
    for i in dict_weather_yandex.keys():
        if i != 'link':
            time_day = day[i]
            bot.send_message(message.from_user.id, f'Температура {time_day} {dict_weather_yandex[i]["temp"]}°'
                                                   f', {dict_weather_yandex[i]["condition"]}')

    bot.send_message(message.from_user.id, f' Подробный прогноз: '
                                           f'{dict_weather_yandex["link"]}')


def big_weather(message, city):
    latitude, longitude = geo_pos(city)
    yandex_weather_x = yandex_weather(latitude, longitude, TOKEN_YANDEX)
    print_yandex_weather(yandex_weather_x, message)


def add_city(message):
  try:
      latitude, longitude = geo_pos(message.text.lower().split('город ')[1])
      city = message.text.lower().split('город ')[1]
      

      cursor.execute(f"SELECT * FROM Cities WHERE chat_id = {message.from_user.id}")
      existing_record = cursor.fetchone()
      
      if existing_record is None:

          cursor.execute(f"INSERT INTO Cities (chat_id, city) VALUES ({message.from_user.id}, '{city}')")
      else:

          cursor.execute(f"UPDATE Cities SET city = '{city}' WHERE chat_id = {message.from_user.id}")
      
      connection.commit()
      

      cities[message.from_user.id] = city
      
      return cities, 0
  except Exception as err:
      bot.send_message(message.from_user.id, f"Ошибка: {err}")
      return cities, 1


cities = {}


startkeyboard = ("👋 Поздороваться", "🌦️ Погода", "⚙️ Настройки", "🤖 О боте")
settingskeyboard = ("📣 Рассылка", "🛑 Остановить рассылку", "🕒 Время рассылки", "↩️ Назад")


@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(*startkeyboard)
    bot.send_message(message.from_user.id,
                     'Краткий гайд по использованию:'
                     '\n1. Напишите город чтобы получить прогноз.'
                     '\n2. Напишите «Мой город *****» чтобы сохранить свой город и напишите «Погода» чтобы получить прогноз на указанный город.'
                     '\n3. Если хотите рассылку прогноза погоды, введите команду /repeat.'
                     '\n4. О боте /about!'
                     '\nНапишите мне свой город/город, район чтобы я скинул Вам прогноз на сегодня!', reply_markup=markup)


def sheduler(message):
   global should_repeat
   should_repeat = True
   def return_weather(message):
       
       cursor.execute(f"SELECT city FROM Cities WHERE chat_id = {message.from_user.id}")
       city = cursor.fetchone()

       if city is not None:
           
           city = city[0]
           bot.send_message(message.from_user.id, f'{message.from_user.first_name}!'
                                               f' Погода в вашем городе: {city}')
           big_weather(message, city)
       else:
           
           bot.send_message(message.from_user.id, f'{message.from_user.first_name}!'
                                               f' Я не знаю ваш город!\nНапишите: '
                                               f'Мой город ***** и бот запомнит Ваш стандартный город!')
           

   global bot_time
   bot_time = None
   if bot_time is not None:
    second_cursor = cursor.execute(f"SELECT city FROM Cities")
    second_city = second_cursor.fetchone()
    if second_city is not None:
        schedule.every().day.at(bot_time).do(return_weather, message)
        bot.send_message(message.from_user.id, f"Вы указали свой город! \nПогода будет Вам рассылаться каждый день в {bot_time} утра!")
        while True:
            if not should_repeat:
                break
            schedule.run_pending()
            time.sleep(1)
    else:
        bot.send_message(message.from_user.id, "Вы не указали свой город!")
   else:
       bot.send_message(message.from_user.id, "Вы не указали время!")
       return repeat_time(message)

# сделать кнопку выйти




def notrepeat(message):
    global should_repeat
    should_repeat = False
    bot.send_message(message.from_user.id, "Рассылка отключена!")


def repeat_time(message):
    markup_time = InlineKeyboardMarkup()
    row = []
    for i in range(24):
        hour = str(i).zfill(2)
        button = types.InlineKeyboardButton(text=hour+':00', callback_data=hour+':00')
        row.append(button)
        if (i + 1) % 4 == 0:
            markup_time.row(*row)
            row = []
    if row:
        markup_time.row(*row)
    bot.send_message(message.from_user.id, "Выберите час:", reply_markup=markup_time)



@bot.callback_query_handler(func=lambda call:True)
def repeat_time_callback(call):
    global bot_time
    for _ in range(5):
        try:
            if call.data:
                
                bot_time = call.data

                bot.send_message(call.message.chat.id, f'Вы выбрали время: {bot_time}')
                return bot_time
            break 
        except req.exceptions.ConnectionError:
            time.sleep(1)  



@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    global cities
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)


    for _ in range(5):
        try:
            if message.text == "👋 Поздороваться":
                bot.send_message(message.from_user.id,
                         f'Привет {message.from_user.first_name}!'
                         f' Напишите  слово "погода" и я напишу погоду в Вашем'
                         f' "стандартном" городе или напишите название города в котором Вы сейчас')
        
            elif message.text == "🌦️ Погода":
       
                cursor.execute(f"SELECT city FROM Cities WHERE chat_id = {message.from_user.id}")
                city = cursor.fetchone()
        
                if city is not None:
                    city = city[0]
                    bot.send_message(message.from_user.id, f'{message.from_user.first_name}!'
                                                            f' Погода в твоём городе: {city}')
                    big_weather(message, city)


                else:
                    bot.send_message(message.from_user.id, f'{message.from_user.first_name}!'
                                                       f' Я не знаю Ваш город!\nНапишите: '
                                                       f'Мой город ***** и бот запомнит Ваш стандартный город!')
            elif message.text == "🤖 О боте":
                bot.send_message(message.from_user.id, 
                         'Простой бот для прогноза погоды на текущий день!'
                         '\nРазработан студентом группы ИС31-21 Рудовым Я.В.', reply_markup=markup)
        
            elif message.text == "⚙️ Настройки":

                markup.add(*settingskeyboard)
                bot.send_message(message.chat.id, text="Настройки:", reply_markup=markup)

            elif message.text == "📣 Рассылка":
                return sheduler(message)

            elif message.text == "🛑 Остановить рассылку":
                return notrepeat(message)
            
            elif message.text == "🕒 Время рассылки":
                return repeat_time(message)


            elif message.text == "↩️ Назад":
                markup.add(*startkeyboard)
                bot.send_message(message.chat.id, text="Главное меню:", reply_markup=markup)

            elif message.text.lower()[:9] == "мой город":
                cities, flag = add_city(message)
                if flag == 0:
                    bot.send_message(message.from_user.id, f'{message.from_user.first_name}!'
                                                           f' Теперь я знаю Ваш город! это'
                                                           f' {cities[message.from_user.id]}')

                else:
                    bot.send_message(message.from_user.id, f'{message.from_user.first_name}!'
                                                           f' Что-то пошло не так')

            else:
                try:
                    city = message.text
                    bot.send_message(message.from_user.id,
                                     f'Привет {message.from_user.first_name}!'
                                     f'\nВаш выбранный город: {city}')

                    big_weather(message, city)

                except AttributeError as err:
                    bot.send_message(message.from_user.id, f'{message.from_user.first_name}!,'
                                                           f' Я не нашел такого города.'
                                                           f'\n Попробуйте ещё раз!')
                    print(f'Ошибка: {err}')

            break
        except req.exceptions.ConnectionError:
            time.sleep(1)


bot.polling(none_stop=True)