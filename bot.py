import os
import requests
from bs4 import BeautifulSoup
import telegram
from telegram.ext import Application
import asyncio
import logging
from datetime import datetime
import time
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройки
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CHECK_URL = "https://www.fansale.de/events/new"
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '30'))  # секунды

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TicketMonitorBot:
    def __init__(self):
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            raise ValueError("TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID должны быть установлены")
        
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.bot = self.application.bot
        self.last_tickets = set()
        self.session = requests.Session()
        
        # Настройка сессии для обхода защиты
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        })

    def get_page_content(self):
        """Получение содержимого страницы с обработкой ошибок"""
        try:
            logger.info(f"Проверяем страницу: {CHECK_URL}")
            response = self.session.get(CHECK_URL, timeout=15)
            response.raise_for_status()
            
            # Проверяем, что получили нормальную HTML страницу
            if 'text/html' in response.headers.get('content-type', ''):
                return response.text
            else:
                logger.warning("Получен не HTML контент")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при загрузке страницы: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            return None

    def parse_tickets(self, html_content):
        """Парсинг билетов со страницы Fansale"""
        if not html_content:
            return set()

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            tickets = set()

            # Селекторы для Fansale (могут потребовать настройки)
            selectors = [
                '.ticketList',  # Основной контейнер
                '.ticket-item',
                '.event-ticket',
                '[class*="ticket"]',
                '.offer'
            ]

            for selector in selectors:
                ticket_elements = soup.select(selector)
                if ticket_elements:
                    logger.info(f"Найден элемент с селектором: {selector}")
                    break

            # Если не нашли стандартные селекторы, ищем по тексту
            if not ticket_elements:
                # Ищем любые элементы, содержащие информацию о билетах
                potential_tickets = soup.find_all(string=lambda text: text and any(word in text.lower() for word in ['ticket', 'karte', 'karten', 'angebot']))
                for element in potential_tickets:
                    parent = element.parent
                    if parent:
                        ticket_info = parent.get_text(strip=True)
                        if ticket_info:
                            tickets.add(ticket_info[:200])  # Ограничиваем длину

            # Альтернативный метод: проверяем наличие любых предложений
            if not tickets:
                # Проверяем, есть ли вообще контент на странице
                text_content = soup.get_text()
                if any(word in text_content.lower() for word in ['radiohead', 'ticket', 'karte']):
                    # Если страница загрузилась и содержит ключевые слова
                    tickets.add("Билеты могут быть доступны - проверьте страницу вручную")

            return tickets

        except Exception as e:
            logger.error(f"Ошибка при парсинге HTML: {e}")
            return set()

    async def send_notification(self, message):
        """Отправка уведомления в Telegram"""
        try:
            await self.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message,
                parse_mode='HTML',
                disable_web_page_preview=False
            )
            logger.info("✅ Уведомление отправлено в Telegram")
            return True
        except telegram.error.TelegramError as e:
            logger.error(f"Ошибка Telegram API: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления: {e}")
            return False

    async def check_for_new_tickets(self):
        """Проверка новых билетов"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"🔍 Проверка билетов в {current_time}")
        
        html_content = self.get_page_content()
        if not html_content:
            await self.send_notification(
                "❌ <b>Ошибка мониторинга</b>\n\n"
                "Не удалось загрузить страницу с билетами. "
                "Возможно, проблемы с сайтом или подключением."
            )
            return

        current_tickets = self.parse_tickets(html_content)
        logger.info(f"Найдено билетов: {len(current_tickets)}")
        
        # Если это первая проверка, просто сохраняем результат
        if not self.last_tickets:
            self.last_tickets = current_tickets
            if current_tickets:
                logger.info("Первоначальные билеты сохранены")
            return

        # Проверяем новые билеты
        new_tickets = current_tickets - self.last_tickets
        
        if new_tickets:
            logger.info(f"🎉 Найдены новые билеты: {len(new_tickets)}")
            
            message = "🎫 <b>Появились новые билеты на Radiohead!</b>\n\n"
            
            for i, ticket in enumerate(new_tickets, 1):
                message += f"{i}. {ticket}\n"
            
            message += f"\n🛒 <a href='{CHECK_URL}'>Купить билеты</a>"
            message += f"\n\n⏰ Обнаружено: {current_time}"
            
            success = await self.send_notification(message)
            if success:
                logger.info("✅ Уведомление о новых билетах отправлено")
        
        # Обновляем список последних билетов
        self.last_tickets = current_tickets

    async def send_startup_message(self):
        """Отправка сообщения о запуске бота"""
        try:
            await self.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text="🚀 <b>Мониторинг билетов запущен!</b>\n\n"
                     f"• Сайт: {CHECK_URL}\n"
                     f"• Интервал проверки: {CHECK_INTERVAL} сек.\n"
                     f"• Бот запущен: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                     "Я буду присылать уведомления о новых билетах!",
                parse_mode='HTML'
            )
            logger.info("Сообщение о запуске отправлено")
        except Exception as e:
            logger.error(f"Ошибка при отправке startup сообщения: {e}")

    async def run(self):
        """Основной цикл работы бота"""
        try:
            # Отправляем сообщение о запуске
            await self.send_startup_message()
            
            logger.info("🔄 Мониторинг билетов запущен...")
            
            # Основной цикл
            while True:
                try:
                    await self.check_for_new_tickets()
                    await asyncio.sleep(CHECK_INTERVAL)
                    
                except KeyboardInterrupt:
                    logger.info("Мониторинг остановлен пользователем")
                    break
                except Exception as e:
                    logger.error(f"Ошибка в основном цикле: {e}")
                    await asyncio.sleep(CHECK_INTERVAL)
                    
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            raise

async def main():
    """Точка входа"""
    try:
        bot = TicketMonitorBot()
        await bot.run()
    except ValueError as e:
        logger.error(f"Ошибка конфигурации: {e}")
    except Exception as e:
        logger.error(f"Не удалось запустить бота: {e}")

if __name__ == "__main__":
    # Проверяем обязательные переменные
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не установлен")
        exit(1)
    if not TELEGRAM_CHAT_ID:
        print("❌ Ошибка: TELEGRAM_CHAT_ID не установлен")
        exit(1)
    
    print("🚀 Запуск бота мониторинга билетов...")
    asyncio.run(main())
