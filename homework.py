import logging
import os
import sys
import time
from contextlib import suppress
from http import HTTPStatus

import requests
import telebot
from dotenv import load_dotenv

from exceptions import TokenError


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_heandler = logging.StreamHandler(sys.stdout)
stream_heandler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s (%(funcName)s - line %(lineno)d)'
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
        if not value
    ]
    if missing_data:
        message = f'Отсутствуют данные: {", ".join(missing_data)}'
        logger.critical(message)
        raise TokenError(message)
    logger.info('Есть все нужные данные.')


def send_message(bot: telebot.TeleBot, message):
    """Отправляет сообщение в Telegram-чат."""
    logger.debug(f'Начало отправки сообщения в Telegram: {message}')
    bot.send_message(TELEGRAM_CHAT_ID, message)
    logger.debug(f'Отправлено сообщение: {message}')


def get_api_answer(timestamp):
    """Делает запрос к API."""
    logger.debug(f'Время для запроса {timestamp}')
    payload = {'from_date': f'{timestamp}'}

    try:
        response = requests.get(url=ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException as error:
        raise Exception(f'Ошибка при запросе к API: {error}. '
                        '(from get_api_answer)') from error

    if response.status_code != HTTPStatus.OK:
        raise ValueError('HTTP ошибка при запросе к эндпоинту API. '
                         '(from get_api_answer)')
    response = response.json()
    logger.debug(f'Получен ответ: {response}')
    return response


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    logger.debug('Начало проверки ответа API')
    if not isinstance(response, dict):
        raise TypeError(f'Тип ответа API {type(response)}. '
                        f'Ожидаемый - словарь. (from check_response)')
    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ожидаемый ключ: homeworks. '
                       '(from check_response)')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError(f'Под ключем homeworks получен {type(homeworks)}. '
                        f'Ожидаемый тип - список. (from check_response)')
    logger.debug('Окончание проверки ответа API')


def parse_status(homework):
    """Извлекает статус домашней работы."""
    logger.debug('Начало получения статуса домашней работы.')

    missing_keys = [key for key in ('homework_name', 'status')
                    if key not in homework]
    if missing_keys:
        raise KeyError(f'Отсутствуют ожидаемые ключи в объекте ДЗ: '
                       f'{", ".join(missing_keys)}. (from parse_status)')

    homework_name = homework.get('homework_name')
    status = homework.get('status')
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неожиданный статус домашней работы: {status}. '
                         f'(from parse_status)')
    verdict = HOMEWORK_VERDICTS.get(f'{status}')
    logger.debug('Статус домашней работы получен.')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    last_sended_error_message = ''
    last_sended_status_message = ''
    check_tokens()

    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    logger.debug('Бот запущен')
    timestamp = int(time.time())
    # timestamp = 1709805600

    while True:
        logger.debug('Начат цикл')
        try:
            response = get_api_answer(timestamp)
            check_response(response)

            homeworks = response.get('homeworks')
            logger.debug(f'Кол-во дз: {len(homeworks)}.')
            if homeworks:
                homework = homeworks[0]
                logger.debug(f'Последнее дз: {homework}')
                message = parse_status(homework)
                if last_sended_status_message != message:
                    send_message(bot, message)
                    last_sended_status_message = message
            else:
                logger.debug('Нет новых статусов ДЗ.')

            timestamp = response.get('current_date', timestamp)
        except telebot.apihelper.ApiTelegramException as error:
            logger.error(f'Cбой при отправке сообщения в Telegram: {error}')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if last_sended_error_message != message:
                with suppress(telebot.apihelper.ApiTelegramException):
                    send_message(bot, message)
                    last_sended_error_message = message
        finally:
            logger.debug('Задержка')
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
