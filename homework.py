import logging
import os
import sys
import time

import requests
from dotenv import load_dotenv
from telebot import TeleBot

from exceptions import TokenError


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_heandler = logging.StreamHandler(sys.stdout)
stream_heandler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s'
)
stream_heandler.setFormatter(formatter)
logger.addHandler(stream_heandler)

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    required_tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    missing_data = [
        token_name for token_name, value in required_tokens.items()
        if value is None
    ]
    if missing_data:
        message = f'Отсутствуют данные: {", ".join(missing_data)}'
        logger.critical(message)
        raise TokenError(message)
    else:
        logger.info('Есть все нужные данные.')


def send_message(bot: TeleBot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Отправлено сообщение в Telegram: {message}')
    except Exception as error:
        logger.error(f'Cбой при отправке сообщения в Telegram: {error}')


def get_api_answer(timestamp):
    """Делает запрос к API."""
    logger.debug(f'Время для запроса {timestamp}')
    payload = {'from_date': f'{timestamp}'}
    try:
        response = requests.get(url=ENDPOINT, headers=HEADERS, params=payload)
        if response.status_code != 200:
            raise requests.exceptions.HTTPError
    except requests.exceptions.ConnectionError as error:
        logger.error(f'Эндпоинт недоступен: {error}')
        raise
    except requests.exceptions.HTTPError as error:
        logger.error(f'HTTP ошибка при запросе к эндпоинту: {error}')
        raise
    except requests.RequestException as error:
        logger.error(f'Ошибка при запросе к API: {error}')
    else:
        response = response.json()
        logger.debug(f'Получен ответ: {response}')
        return response


def check_response(response):
    """Проверяет ответ API.
    Проверяет ответ API на соответствие документации и при наличии возвращает
    один элемент из списка домашних работ.
    """
    if not isinstance(response, dict):
        message = 'Ответ API не является словарем.'
        logger.error(message)
        raise TypeError(message)
    if 'homeworks' not in response or 'current_date' not in response:
        message = 'Отсутствуют ожидаемые ключи в ответе API.'
        logger.error(message)
        raise KeyError(message)
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        message = 'Под ключем homeworks нет списка.'
        logger.error(message)
        raise TypeError(message)
    logger.debug(f'Кол-во дз: {len(homeworks)}.')
    if len(homeworks) > 0:
        homework = homeworks[0]
        logger.debug(f'Последнее дз: {homework}')
        return homework
    else:
        logger.debug('Нет новых статусов ДЗ.')
        return None


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework or 'status' not in homework:
        message = 'Отсутствуют ожидаемые ключи в объекте ДЗ.'
        logger.error(message)
        raise KeyError(message)
    homework_name = homework.get('homework_name')
    status = homework.get('status')
    if status not in HOMEWORK_VERDICTS:
        message = f'Неожиданный статус домашней работы: {status}'
        logger.error(message)
        raise KeyError(message)
    verdict = HOMEWORK_VERDICTS.get(f'{status}')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    last_error_message = None
    check_tokens()

    bot = TeleBot(TELEGRAM_TOKEN)
    logger.debug('Бот запущен')
    timestamp = int(time.time())
    # timestamp = 1709805600

    while True:
        logger.debug('Начат цикл')
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            if homework:
                message = parse_status(homework)
                send_message(bot, message)
            timestamp = response.get('current_date', timestamp)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if last_error_message != message:
                send_message(bot, message)
                last_error_message = message

        logger.debug('Задержка')
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
