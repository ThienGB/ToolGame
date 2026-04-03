#!/usr/bin/env python3
"""
Garena Bulk Registration Bot
Features:
- Selenium with Stealth (undetected-chromedriver)
- Proxy Support
- Email OTP verification (via 10minutemail.net or TempMail)
- Multi-account registration loop
"""

import time
import random
import string
import os
import sys
import logging
from typing import Optional, List, Dict

# Standard Selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# For stealth (if installed, else fallback)
try:
    import undetected_chromedriver as uc
    USE_UC = True
except ImportError:
    USE_UC = False
    from selenium.webdriver.chrome.options import Options

# Import email services from existing bot
try:
    from account_registration_bot import TenMinuteMail, TempMail, TempEmailService, OneSecMail
except ImportError:
    # Basic fallback if import fails
    class TempEmailService:
        def get_email(self): return ""
        def get_messages(self): return []
        def extract_otp(self, msg): return None

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("garena_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ProxyBlockedException(Exception):
    """Exception raised when Garena blocks the proxy IP"""
    pass

class GarenaRegistrationBot:
    def __init__(self, email_service: TempEmailService, proxy: Optional[str] = None, headless: bool = False, country: str = "Singapore (Singapura)"):
        self.email_service = email_service
        self.proxy = proxy
        self.headless = headless
        self.country = country
        self.driver = None
        self.wait = None

    def _init_driver(self):
        """Initializes the browser with stealth options"""
        logger.info("Initializing browser...")
        
        if USE_UC:
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument('--headless')
            
            if self.proxy:
                options.add_argument(f'--proxy-server={self.proxy}')
            
            # Dung thu muc profile that de Garena thay giong nguoi dung cu
            profile_path = os.path.join(os.getcwd(), "garena_profile")
            options.add_argument(f'--user-data-dir={profile_path}')
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            # Rotate User-Agents chuan 2024
            uas = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ]
            ua = random.choice(uas)
            options.add_argument(f'--user-agent={ua}')
            logger.info(f"Using Stealth Profile & UA: {ua}")
            
            try:
                # Ép phiên bản 146
                self.driver = uc.Chrome(options=options, version_main=146)
                logger.info("Undetected ChromeDriver started (Version 146)")
            except Exception as e:
                # Nếu ép 146 vẫn lỗi thì thử auto lại lần cuối
                print(f"\n[!] Loi UC ban 146: {e}. Thu lai ban Auto...")
                try:
                    self.driver = uc.Chrome(options=options)
                    logger.info("Undetected ChromeDriver started (Auto)")
                except Exception as e2:
                    print(f"\n[!] Loi UC (Auto): {e2}")
                    logger.error(f"Failed to start UC: {e2}")
                    logger.info("Retrying with standard Selenium fallback...")
                    self._init_standard_selenium()
        else:
            self._init_standard_selenium()
            
        self.wait = WebDriverWait(self.driver, 25)
        # Randomize window size
        w = random.randint(1024, 1600)
        h = random.randint(700, 900)
        self.driver.set_window_size(w, h)
        logger.info(f"Set window size to {w}x{h}")

    def _init_standard_selenium(self):
        try:
            from selenium.webdriver.chrome.service import Service
            options = Options()
            if self.headless:
                options.add_argument('--headless=new')
            
            if self.proxy:
                options.add_argument(f'--proxy-server={self.proxy}')

            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            self.driver = webdriver.Chrome(options=options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logger.info("✓ Standard Selenium started")
        except Exception as e:
            print(f"\n[!] Lỗi Selenium thường: {e}")
            raise e

    def human_move_to(self, element):
        """Di chuyen chuot den phan tu theo duong cong"""
        from selenium.webdriver.common.action_chains import ActionChains
        actions = ActionChains(self.driver)
        # Lay vi tri hien tai cua chuot (gia dinh) va phan tu
        actions.move_to_element_with_offset(element, random.randint(-5, 5), random.randint(-5, 5)).perform()
        time.sleep(random.uniform(0.1, 0.3))

    def human_type(self, element, text: str):
        """Go phim giong nguoi: toc do nhanh cham bit thong va co do tre 'suy nghi'"""
        self.human_move_to(element)
        element.click()
        time.sleep(random.uniform(0.2, 0.5))
        
        # Thoi diem bat dau go (nhu kieu vua nho ra)
        for i, char in enumerate(text):
            # Nhịp nghỉ lớn giữa các cụm từ (giống người đang nhớ lại)
            if i > 0 and i % 4 == 0:
                time.sleep(random.uniform(0.3, 0.8))
            
            # Ti le go sai cuc thấp 2%
            if random.random() < 0.02:
                wrong_char = random.choice(string.ascii_lowercase)
                element.send_keys(wrong_char)
                time.sleep(random.uniform(0.1, 0.3))
                element.send_keys(Keys.BACKSPACE)
                time.sleep(random.uniform(0.05, 0.2))
            
            element.send_keys(char)
            # Toc do go phím nhanh hon nhung khong deu (0.05 - 0.18s)
            time.sleep(random.uniform(0.05, 0.18))

    def human_hover(self):
        """Thi thoang di chuyen chuot nhe nhang (giong người dang doc/cho)"""
        from selenium.webdriver.common.action_chains import ActionChains
        try:
            actions = ActionChains(self.driver)
            for _ in range(random.randint(2, 4)):
                actions.move_by_offset(random.randint(-10, 10), random.randint(-10, 10)).perform()
                time.sleep(random.uniform(0.1, 0.3))
        except: pass

    def human_click(self, element):
        """Click chuot giong nguoi: di chuot xung quanh roi moi bam"""
        self.human_move_to(element)
        time.sleep(random.uniform(0.2, 0.6))
        element.click()
        time.sleep(random.uniform(0.5, 1.0))

    def generate_garena_password(self) -> str:
        """Tao mat khau dung chuan Garena: hoa, thuong, so, ky hieu"""
        import string
        lower = random.choice(string.ascii_lowercase)
        upper = random.choice(string.ascii_uppercase)
        digit = random.choice(string.digits)
        symbol = random.choice("!@#$%^&*")
        # Them cac ky tu ngau nhien khac de du 12 ki tu
        others = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        password = lower + upper + digit + symbol + others
        # Tron ngau nhien
        l = list(password)
        random.shuffle(l)
        return "".join(l)

    def generate_random_string(self, length: int = 10, alphanumeric: bool = True) -> str:
        chars = string.ascii_letters + string.digits if alphanumeric else string.ascii_lowercase
        return "".join(random.choices(chars, k=length))

    def get_public_ip(self) -> str:
        """Lay dia chi IP public hien tai"""
        try:
            import requests
            response = requests.get('https://api.ipify.org', timeout=10)
            return response.text
        except:
            return "Khong the kiem tra IP"

    def change_ip(self, command: str):
        """Thuc hien lenh doi IP (VPN/Dcom)"""
        if not command: return
        logger.info(f"Dang thuc hien doi IP: {command}")
        try:
            os.system(command)
            time.sleep(10) # Doi 10s cho mang on dinh lai
            new_ip = self.get_public_ip()
            logger.info(f"IP hien tai sau khi doi: {new_ip}")
        except Exception as e:
            logger.error(f"Loi khi doi IP: {e}")

    def register_one_account(self) -> Optional[Dict]:
        """Runs the registration flow for one account"""
        try:
            self._init_driver()
            
            # Delay ngau nhien truoc khi vao Garena de giong nguoi suy nghi
            time.sleep(random.randint(5, 10))
            
            # Garena registration URL
            url = "https://sso.garena.com/universal/register"
            logger.info(f"Navigating to {url}")
            self.driver.get(url)
            time.sleep(random.randint(4, 7))
            
            # MO PHONG NGƯỜI ĐỌC TRANG (Scroll và click vao cho trong)
            try:
                self.driver.execute_script("window.scrollTo(0, 100);")
                time.sleep(1)
                self.driver.execute_script("window.scrollTo(0, 0);")
                logger.info("Da mo phong hanh vi cuon trang (Scroll)")
            except: pass

            # Generate info
            username = self.generate_random_string(9).lower() + str(random.randint(10, 99))
            password = self.generate_random_string(12) + "!"
            email = self.email_service.get_email()
            
            # Tu tao email voi cac ten mien it bị chặn hơn
            first_names = ["nam", "hung", "anh", "minh", "tuan", "hoang", "thanh", "duc", "viet"]
            last_names = ["nguyen", "tran", "le", "pham", "hoang", "vu", "dang", "bui"]
            rand_name = random.choice(first_names) + random.choice(last_names) + str(random.randint(1980, 2005))
            username_email = rand_name + str(random.randint(10, 99))
            
            # Ep dung mien fextemp.com vi no thuong khong bi Garena chan
            domain_email = "fextemp.com"
            email = f"{username_email}@{domain_email}"
            logger.info(f"Su dung email fextemp: {email}")
            password = self.generate_garena_password()
            
            logger.info(f"Attempting to register: User={username}, Pass={password}")

            # Fill Username (Doi thu tu mot chút)
            username_field = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[placeholder="Username"]')))
            self.human_type(username_field, username)
            self.human_hover() # Di chuot nhe sau khi go
            time.sleep(random.randint(1, 2))

            # Password
            password_field = self.driver.find_element(By.CSS_SELECTOR, 'input[placeholder="Password"]')
            self.human_type(password_field, password)
            self.human_hover()
            
            # Confirm Password
            confirm_field = self.driver.find_element(By.CSS_SELECTOR, 'input[placeholder="Re-enter password"]')
            self.human_type(confirm_field, password)
            time.sleep(random.randint(1, 2))

            # Loop thu cac Email khac nhau neu bi "Not authorized"
            email_authorized = False
            for try_mail in range(5): # Thu toi da 5 email khac nhau
                first_names = ["nam", "hung", "anh", "minh", "tuan", "hoang", "thanh", "duc", "viet"]
                last_names = ["nguyen", "tran", "le", "pham", "hoang", "vu", "dang", "bui"]
                rand_name = random.choice(first_names) + random.choice(last_names) + str(random.randint(1980, 2005))
                username_email = rand_name + str(random.randint(10, 999))
                domain_email = random.choice(["fextemp.com", "kzccv.com", "qiott.com", "wuuvo.com", "icznn.com"])
                email = f"{username_email}@{domain_email}"
                
                logger.info(f"Thu email ({try_mail+1}/5): {email}")
                email_field = self.driver.find_element(By.CSS_SELECTOR, 'input[placeholder="Email"]')
                # Xoa trang ô email cu
                self.driver.execute_script("arguments[0].value = '';", email_field)
                self.human_type(email_field, email)
                
                # Blur bang cach nhan TAB
                email_field.send_keys(Keys.TAB)
                time.sleep(5) # Doi Garena validate
                
                # Kiem tra loi "Not authorized"
                page_text = self.driver.page_source
                if "authorized" in page_text.lower() or "contact customer support" in page_text.lower():
                    logger.warning(f"  Email {email} bi chan. Dang thu mail khac...")
                    continue
                else:
                    email_authorized = True
                    logger.info(f"  Email {email} duoc Garena chap nhan!")
                    break
            
            if not email_authorized:
                logger.error("Tat ca email deu bi chan! Co the IP da bi block hoan toan.")
                return None

            # Click "GET CODE" (Dung human_click)
            try:
                get_code_btn = self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'GET CODE')]")))
                self.human_click(get_code_btn)
                logger.info("Da Click GET CODE bang human_click")
            except Exception as e:
                logger.warning(f"Loi khi klick GET CODE: {e}")
                get_code_btn = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.secondary")))
                self.human_click(get_code_btn)

            # Handle possible CAPTCHA or blocking here
            time.sleep(5)
            
            if "Access is temporarily restricted" in self.driver.page_source or "Access Denied" in self.driver.page_source:
                logger.error("✗ IP Blocked by Garena!")
                raise ProxyBlockedException("Proxy is blocked")

            # Wait for OTP via Browser Tab
            logger.info("Dang cho OTP qua Tab trình duyet...")
            otp = None
            start_time = time.time()
            
            # Chuyen sang tab email (hoac mo moi neu chua co)
            original_window = self.driver.current_window_handle
            if len(self.driver.window_handles) < 2:
                self.driver.switch_to.new_window('tab')
            else:
                self.driver.switch_to.window(self.driver.window_handles[1])
            
            # Mo phong vao hòm thư dự phòng (Neu 1secmail bi loi thi vao DropMail/Mail.tm)
            mailbox_url = f"https://dropmail.me/vi/"
            if "1secmail" in domain_email:
                mailbox_url = f"https://www.1secmail.com/mailbox/?login={username_email}&domain={domain_email}"
            
            while time.time() - start_time < 180:
                self.driver.get(mailbox_url)
                time.sleep(10)
                
                try:
                    # Tim OTP trong toan bo noi dung trang (Cach nay dung cho moi loai email)
                    page_text = self.driver.page_source
                    import re
                    from config import OTP_PATTERNS
                    for pattern in OTP_PATTERNS:
                        match = re.search(pattern, page_text)
                        if match:
                            otp = match.group(1)
                            break
                    if otp: break
                    
                    # Neu dung DropMail thi can click vao mail hien ra
                    emails = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'Garena') or contains(text(), 'Security')]")
                    if emails:
                        emails[0].click()
                        time.sleep(2)
                except:
                    pass
                
                logger.info(f"  ... van dang cho OTP ({int(time.time()-start_time)}s)")
            
            # Quay lai tab dang ky
            self.driver.switch_to.window(original_window)
            
            if not otp:
                logger.error("Khong nhan duoc OTP sau 3 phut.")
                return None

            logger.info(f"✓ Received OTP: {otp}")

            # Enter OTP
            otp_field = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[placeholder="Verification Code"]')))
            otp_field.send_keys(otp)
            time.sleep(1)

            # Optional: Select country if needed. Default is often based on IP.
            # Garena uses a standard <select> for country
            try:
                from selenium.webdriver.support.ui import Select
                country_el = self.driver.find_element(By.CSS_SELECTOR, "select:not(.lang)")
                select = Select(country_el)
                # Try to select by visible text if possible
                try:
                    select.select_by_visible_text(self.country)
                    logger.info(f"✓ Country selected: {self.country}")
                except:
                    # Fallback to Singapore if specified text fails
                    select.select_by_visible_text("Singapore (Singapura)")
                    logger.info(f"✓ Country fallback selected: Singapore (Singapura)")
            except Exception as e:
                logger.warning(f"Could not select country: {e}")
            
            # Click "Register Now"
            register_btn = self.driver.find_element(By.CSS_SELECTOR, "button.primary")
            register_btn.click()
            logger.info("Clicked Register Now")

            # Check for success
            time.sleep(5)
            # Typically redirects to a success page or shows a success message
            if "success" in self.driver.current_url.lower() or "completed" in self.driver.page_source.lower():
                logger.info("🎉 ACCOUNT CREATED SUCCESSFULLY!")
                return {
                    "username": username,
                    "password": password,
                    "email": email
                }
            else:
                logger.warning(f"Registration might have failed. URL: {self.driver.current_url}")
                # Save screenshot for debug
                self.driver.save_screenshot(f"debug_{username}.png")
                return None

        except Exception as e:
            logger.error(f"✗ Exception occurred: {e}")
            return None
        finally:
            if self.driver:
                self.driver.quit()

def bulk_register(count: int, proxy_file: Optional[str] = None, country: str = "Singapore (Singapura)", headless: bool = True, vpn_command: Optional[str] = None):
    """Loop for bulk account registration"""
    # Mac dinh dung OneSecMail vi no on dinh nhat hien tai
    email_service = OneSecMail()
    
    proxies = []
    if proxy_file and os.path.exists(proxy_file):
        with open(proxy_file, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
    
    success_accounts = []
    
    for i in range(count):
        logger.info(f"--- Creating account {i+1}/{count} ---")
        
        # Kiem tra IP hien tai
        bot_temp = GarenaRegistrationBot(email_service)
        current_ip = bot_temp.get_public_ip()
        logger.info(f"IP bat dau: {current_ip}")
        
        # Doi IP neu co lenh VPN truoc khi bat dau moi
        if vpn_command:
            bot_temp.change_ip(vpn_command)
            time.sleep(10) # Force short sleep after VPN command
            new_ip = bot_temp.get_public_ip()
            logger.info(f"IP sau khi doi: {new_ip}")

        account_created = False
        retry_count = 0
        max_retries = len(proxies) if proxies else 3 # Retry with all proxies if available

        while not account_created and retry_count < max_retries:
            proxy = proxies[retry_count % len(proxies)] if proxies else None
            
            if proxy:
                logger.info(f"  Attempting with Proxy: {proxy} (Retry {retry_count})")
            
            bot = GarenaRegistrationBot(email_service, proxy=proxy, headless=headless, country=country)
            
            try:
                account = bot.register_one_account()
                
                if account:
                    success_accounts.append(account)
                    # Save with requested format: tk|mk (username|password)
                    with open("accounts.txt", "a") as f:
                        f.write(f"{account['username']}|{account['password']}\n")
                    logger.info(f"🎉 Saved: {account['username']}")
                    account_created = True
                else:
                    logger.warning("  Registration failed for unknown reason. Retrying...")
                    retry_count += 1

            except ProxyBlockedException:
                logger.error(f"  Proxy {proxy} blocked. Switching...")
                # Neu có VPN thi thu doi IP ngay lap tuc
                if vpn_command:
                    bot.change_ip(vpn_command)
                retry_count += 1
                if not proxies:
                    logger.error("No more proxies to try.")
                    break
            except Exception as e:
                logger.error(f"  Unexpected error: {e}")
                retry_count += 1
            
            # Brief pause before retry
            if not account_created:
                time.sleep(2)

        # Cooldown between successful registrations to avoid overall account-gen bans
        if account_created:
            wait_time = random.randint(30, 60)
            logger.info(f"Waiting {wait_time}s before starting next account...")
            time.sleep(wait_time)

    logger.info(f"Bulk registration process finished. Total success: {len(success_accounts)}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Garena Bulk Registration Bot")
    parser.add_argument("--count", type=int, default=1, help="Number of accounts to create")
    parser.add_argument("--proxy", type=str, help="Path to proxy list file")
    parser.add_argument("--country", type=str, default="Singapore (Singapura)", help="Visible text in country dropdown")
    parser.add_argument("--show", dest="headless", action="store_false", default=True, help="Hien thi cua so trinh duyet (Mac dinh la an)")
    parser.add_argument("--vpn", type=str, help="Lenh CMD de doi IP (VD: 'rasdial dcom' hoac 'hma-vpn.exe -changeip')")
    parser.set_defaults(headless=True)
    args = parser.parse_args()

    # Install dependencies check (reminder to user)
    # pip install selenium undetected-chromedriver requests beautifulsoup4
    
    bulk_register(args.count, args.proxy, args.country, args.headless, args.vpn)
