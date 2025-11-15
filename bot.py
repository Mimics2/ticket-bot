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
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Загрузка переменных окружения
load_dotenv()

# Настройки
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CHECK_URL = "https://www.fansale.de/tickets/all/radiohead/520"
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '60'))  # секунды

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
        self.driver = None
        
        # Инициализируем Selenium драйвер
        self.setup_selenium()

    def setup_selenium(self):
        """Настройка Selenium WebDriver для Railway"""
        try:
            chrome_options = Options()
            
            # Опции для Railway (без GUI)
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--remote-debugging-port=9222")
            
            # Случайный User-Agent
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
            ]
            chrome_options.add_argument(f'--user-agent={random.choice(user_agents)}')
            
            # Дополнительные настройки
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Для Railway используем chromedriver из PATH
            self.driver = webdriver.Chrome(options=chrome_options)
            
            # Скрываем автоматизацию
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info("✅ Selenium WebDriver инициализирован")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Selenium: {e}")
            raise

    def get_page_content_selenium(self):
        """Получение страницы через Selenium"""
        try:
            logger.info("🌐 Загружаем страницу через Selenium...")
            
            self.driver.get(CHECK_URL)
            
            # Ждем загрузки контента
            wait = WebDriverWait(self.driver, 15)
            
            # Ждем появления любого контента
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # Случайная задержка как у человека
            time.sleep(random.uniform(2, 5))
            
            # Прокрутка страницы для имитации поведения пользователя
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(1)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            # Получаем HTML после полной загрузки
            page_source = self.driver.page_source
            
            if "Radiohead" in page_source or "radiohead" in page_source:
                logger.info("✅ Страница успешно загружена")
                return page_source
            else:
                logger.warning("⚠️ Страница загрузилась, но не содержит информацию о Radiohead")
                return page_source
                
        except TimeoutException:
            logger.error("⏰ Таймаут при загрузке страницы")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка Selenium: {e}")
            return None

    def get_page_content_requests(self):
        """Резервный метод через requests"""
        try:
            session = requests.Session()
            
            # Случайный User-Agent
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            ]
            
            headers = {
                'User-Agent': random.choice(user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0',
                'Referer': 'https://www.fansale.de/'
            }
            
            logger.info("🌐 Пробуем загрузить через requests...")
            response = session.get(CHECK_URL, headers=headers, timeout=20)
            response.raise_for_status()
            
            logger.info("✅ Requests метод сработал")
            return response.text
            
        except Exception as e:
            logger.error(f"❌ Ошибка requests метода: {e}")
            return None

    def get_page_content(self):
        """Основной метод получения контента"""
        # Сначала пробуем Selenium
        content = self.get_page_content_selenium()
        
        # Если не сработало, пробуем requests
        if not content:
            logger.info("🔄 Пробуем резервный метод...")
            content = self.get_page_content_requests()
            
        return content

    def parse_tickets(self, html_content):
        """Парсинг билетов со страницы"""
        if not html_content:
            return set()

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            tickets = set()

            # Метод 1: Ищем по классам и структуре Fansale
            selectors = [
                '.ticketList', 
                '.ticket-item',
                '.event-ticket',
                '.ticketOffer',
                '.offerItem',
                '[class*="ticket"]',
                '[class*="offer"]',
                '.fs-event-ticket'
            ]

            for selector in selectors:
                elements = soup.select(selector)
                if elements:
                    logger.info(f"🎫 Найден элемент с селектором: {selector}")
                    for element in elements:
                        text = element.get_text(strip=True)
                        if text and len(text) > 10:  # Фильтруем мусор
                            tickets.add(text[:300])
                    break

            # Метод 2: Ищем по текстовому содержанию
            if not tickets:
                keywords = ['Radiohead', 'radiohead', 'Karte', 'karte', 'Ticket', 'ticket', 'Veranstaltung']
                for keyword in keywords:
                    elements = soup.find_all(string=lambda text: text and keyword in text)
                    for element in elements:
                        parent_text = element.parent.get_text(strip=True) if element.parent else str(element)
                        if parent_text and len(parent_text) > 20:
                            tickets.add(parent_text[:300])

            # Метод 3: Проверяем общее наличие контента
            if not tickets:
                body_text = soup.get_text()
                if any(word in body_text for word in ['Radiohead', 'radiohead']):
                    tickets.add("Страница Radiohead загружена - проверьте наличие билетов вручную")

            logger.info(f"📊 Найдено {len(tickets)} потенциальных билетов")
            return tickets

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")
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
            logger.info("✅ Уведомление отправлено")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False

    async def check_for_new_tickets(self):
        """Проверка новых билетов"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"🔍 Проверка в {current_time}")
        
        html_content = self.get_page_content()
        if not html_content:
            logger.error("❌ Не удалось получить контент страницы")
            return

        current_tickets = self.parse_tickets(html_content)
        
        # Если это первая проверка
        if not self.last_tickets:
            self.last_tickets = current_tickets
            if current_tickets:
                logger.info("✅ Первоначальные билеты сохранены")
            else:
                logger.info("ℹ️ Билеты не найдены на первой проверке")
            return

        # Проверяем новые билеты
        new_tickets = current_tickets - self.last_tickets
        
        if new_tickets:
            logger.info(f"🎉 Найдены {len(new_tickets)} новых билетов!")
            
            message = "🎫 <b>НОВЫЕ БИЛЕТЫ НА RADIOHEAD!</b>\n\n"
            
            for i, ticket in enumerate(new_tickets, 1):
                message += f"• {ticket}\n"
            
            message += f"\n🛒 <a href='{CHECK_URL}'>КУПИТЬ СЕЙЧАС</a>"
            message += f"\n\n⏰ Обнаружено: {current_time}"
            
            await self.send_notification(message)
        
        # Обновляем список
        self.last_tickets = current_tickets

    async def send_startup_message(self):
        """Сообщение о запуске"""
        try:
            await self.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text="🚀 <b>Мониторинг билетов запущен!</b>\n\n"
                     f"• Сайт: Fansale\n"
                     f"• Используется: Selenium WebDriver\n"  
                     f"• Интервал: {CHECK_INTERVAL} сек.\n"
                     f"• Запуск: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                     "Бот будет присылать уведомления о новых билетах!",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Ошибка startup сообщения: {e}")

    async def run(self):
        """Основной цикл"""
        try:
            await self.send_startup_message()
            logger.info("🔄 Мониторинг запущен...")
            
            while True:
                try:
                    await self.check_for_new_tickets()
                    # Случайная задержка между проверками
                    delay = CHECK_INTERVAL + random.randint(-10, 10)
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"Ошибка в цикле: {e}")
                    await asyncio.sleep(CHECK_INTERVAL)
                    
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            raise
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("✅ WebDriver закрыт")

async def main():
    """Точка входа"""
    try:
        bot = TicketMonitorBot()
        await bot.run()
    except Exception as e:
        logger.error(f"Не удалось запустить бота: {e}")

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Установите TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID")
        exit(1)
    
    print("🚀 Запуск улучшенного бота мониторинга...")
    asyncio.run(main())
