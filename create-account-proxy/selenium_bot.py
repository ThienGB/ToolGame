#!/usr/bin/env python3
"""
Registration Bot với Selenium - Cho các website phức tạp
Sử dụng khi website có JavaScript, CAPTCHA, hoặc flow phức tạp
"""

import time
import re
from typing import Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

# Import email service từ file chính
from account_registration_bot import TempMail, TenMinuteMail


class SeleniumRegistrationBot:
    """Bot đăng ký sử dụng Selenium WebDriver"""
    
    def __init__(self, email_service, headless: bool = False):
        """
        Args:
            email_service: Instance của TempEmailService
            headless: Chạy browser ẩn (True) hay hiện (False)
        """
        self.email_service = email_service
        self.driver = self._init_driver(headless)
        self.wait = WebDriverWait(self.driver, 10)
    
    def _init_driver(self, headless: bool):
        """Khởi tạo Chrome WebDriver"""
        options = Options()
        
        if headless:
            options.add_argument('--headless')
        
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    
    def fill_form(self, selectors: dict, data: dict):
        """
        Điền form tự động
        
        Args:
            selectors: Dict mapping field -> CSS selector
                Example: {'email': '#email', 'password': 'input[name="pass"]'}
            data: Dict chứa giá trị điền vào
                Example: {'email': 'test@mail.com', 'password': '123456'}
        """
        for field, value in data.items():
            if field in selectors:
                try:
                    element = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selectors[field]))
                    )
                    element.clear()
                    element.send_keys(value)
                    print(f"✓ Đã điền {field}: {value}")
                except TimeoutException:
                    print(f"✗ Không tìm thấy field: {field}")
    
    def click_button(self, selector: str):
        """Click button"""
        try:
            button = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            button.click()
            print(f"✓ Đã click button: {selector}")
            return True
        except TimeoutException:
            print(f"✗ Không tìm thấy button: {selector}")
            return False
    
    def wait_for_element(self, selector: str, timeout: int = 10) -> bool:
        """Đợi element xuất hiện"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            return True
        except TimeoutException:
            return False
    
    def get_text(self, selector: str) -> Optional[str]:
        """Lấy text từ element"""
        try:
            element = self.driver.find_element(By.CSS_SELECTOR, selector)
            return element.text
        except:
            return None
    
    def auto_register_with_selenium(self,
                                   url: str,
                                   form_selectors: dict,
                                   registration_data: dict,
                                   submit_button: str,
                                   otp_input: str,
                                   otp_submit_button: str,
                                   otp_timeout: int = 120):
        """
        Tự động đăng ký với Selenium
        
        Args:
            url: URL trang đăng ký
            form_selectors: Dict selectors cho form
            registration_data: Data đăng ký
            submit_button: Selector button submit
            otp_input: Selector input OTP
            otp_submit_button: Selector button submit OTP
            otp_timeout: Timeout chờ OTP
        """
        try:
            print("=" * 60)
            print("🚀 BẮT ĐẦU ĐĂNG KÝ VỚI SELENIUM")
            print("=" * 60)
            
            # 1. Lấy email tạm thời
            email = self.email_service.get_email()
            registration_data['email'] = email
            
            # 2. Mở trang đăng ký
            print(f"\n→ Đang mở trang: {url}")
            self.driver.get(url)
            time.sleep(2)
            
            # 3. Điền form
            print(f"\n→ Đang điền form đăng ký...")
            self.fill_form(form_selectors, registration_data)
            
            # 4. Click submit
            print(f"\n→ Đang submit form...")
            self.click_button(submit_button)
            time.sleep(3)
            
            # 5. Chờ OTP
            print(f"\n→ Đang chờ OTP...")
            start_time = time.time()
            otp = None
            last_message_count = 0
            
            while time.time() - start_time < otp_timeout:
                messages = self.email_service.get_messages()
                
                if messages and len(messages) > last_message_count:
                    for message in messages:
                        otp = self.email_service.extract_otp(message)
                        if otp:
                            break
                    last_message_count = len(messages)
                    if otp:
                        break
                
                elapsed = int(time.time() - start_time)
                print(f"  ⏳ {elapsed}/{otp_timeout}s...", end='\r')
                time.sleep(5)
            
            if not otp:
                print(f"\n✗ Không nhận được OTP!")
                return False
            
            print(f"\n✓ Đã nhận OTP: {otp}")
            
            # 6. Nhập OTP
            print(f"\n→ Đang nhập OTP...")
            otp_field = self.wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, otp_input))
            )
            otp_field.clear()
            otp_field.send_keys(otp)
            
            # 7. Submit OTP
            print(f"→ Đang xác thực OTP...")
            self.click_button(otp_submit_button)
            time.sleep(3)
            
            # 8. Kiểm tra kết quả
            print(f"\n→ Kiểm tra kết quả...")
            # Có thể thêm logic check thành công ở đây
            
            print("\n" + "=" * 60)
            print("✓ HOÀN THÀNH!")
            print("=" * 60)
            
            return True
            
        except Exception as e:
            print(f"\n✗ Lỗi: {e}")
            return False
        
    def close(self):
        """Đóng browser"""
        if self.driver:
            self.driver.quit()
            print("Browser đã đóng")


# ==================== EXAMPLE USAGE ====================

def example_shopee_register():
    """Ví dụ đăng ký Shopee (mẫu - cần điều chỉnh selectors)"""
    
    email_service = TempMail()
    bot = SeleniumRegistrationBot(email_service, headless=False)
    
    try:
        bot.auto_register_with_selenium(
            url="https://shopee.vn/buyer/signup",
            
            # Selectors cho form (CẦN ĐIỀU CHỈNH THEO WEBSITE THẬT)
            form_selectors={
                'phone': 'input[name="phone"]',
                'password': 'input[type="password"]',
            },
            
            registration_data={
                'phone': '0987654321',  # Số điện thoại giả
                'password': 'SecurePass123!',
            },
            
            submit_button='button[type="submit"]',
            otp_input='input[placeholder*="OTP"]',
            otp_submit_button='button:contains("Xác nhận")',
            
            otp_timeout=120
        )
    finally:
        bot.close()


def example_custom_website():
    """Template cho website tùy chỉnh"""
    
    email_service = TenMinuteMail()
    bot = SeleniumRegistrationBot(email_service, headless=False)
    
    try:
        # Mở trang
        bot.driver.get("https://your-website.com/register")
        
        # Lấy email
        email = email_service.get_email()
        
        # Điền form thủ công
        bot.fill_form(
            selectors={
                'username': '#username',
                'email': '#email',
                'password': '#password',
                'confirm_password': '#confirm-password',
            },
            data={
                'username': 'testuser123',
                'email': email,
                'password': 'MySecurePass123!',
                'confirm_password': 'MySecurePass123!',
            }
        )
        
        # Submit
        bot.click_button('#register-button')
        
        # Đợi trang OTP load
        time.sleep(3)
        
        # Chờ OTP qua email
        print("Đang chờ OTP...")
        start = time.time()
        otp = None
        
        while time.time() - start < 120:
            messages = email_service.get_messages()
            if messages:
                otp = email_service.extract_otp(messages[0])
                if otp:
                    break
            time.sleep(5)
        
        if otp:
            # Nhập OTP
            bot.fill_form(
                selectors={'otp': '#otp-input'},
                data={'otp': otp}
            )
            bot.click_button('#verify-button')
            
            print("✓ Đăng ký thành công!")
        
    finally:
        input("Press Enter to close browser...")
        bot.close()


if __name__ == "__main__":
    # Chọn ví dụ muốn chạy
    # example_shopee_register()
    example_custom_website()
