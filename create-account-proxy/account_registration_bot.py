#!/usr/bin/env python3
"""
Auto Registration Bot với Email Tạm Thời và OTP
Hỗ trợ nhiều email service và tự động lấy OTP
"""

import re
import time
import random
import string
import requests
import hashlib
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup

from config import OTP_PATTERNS


class TempEmailService:
    """Base class cho các email service"""
    
    def get_email(self) -> str:
        """Lấy địa chỉ email tạm thời"""
        raise NotImplementedError
    
    def get_messages(self) -> list:
        """Lấy danh sách tin nhắn"""
        raise NotImplementedError
    
    def extract_otp(self, message: Dict) -> Optional[str]:
        """Trích xuất mã OTP từ email"""
        raise NotImplementedError


class TenMinuteMail(TempEmailService):
    """Service sử dụng 10minutemail.net"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.email = None
        self.session_id = None
    
    def get_email(self) -> str:
        """Lấy email từ 10minutemail"""
        try:
            response = self.session.get('https://10minutemail.net/')
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Tìm email address
            email_input = soup.find('input', {'id': 'mail_address'})
            if email_input and email_input.get('value'):
                self.email = email_input['value']
                print(f"✓ Email tạm thời: {self.email}")
                return self.email
            
            raise Exception("Không thể lấy email từ 10minutemail")
        except Exception as e:
            print(f"✗ Lỗi 10minutemail: {e}")
            raise
    
    def get_messages(self) -> list:
        """Lấy tin nhắn từ inbox"""
        try:
            response = self.session.get('https://10minutemail.net/mailbox.ajax.php')
            data = response.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"✗ Lỗi lấy tin nhắn: {e}")
            return []
    
    def extract_otp(self, message: Dict) -> Optional[str]:
        """Trích xuất OTP từ nội dung email"""
        try:
            # Lấy nội dung email
            msg_id = message.get('mail_id')
            response = self.session.get(
                f'https://10minutemail.net/mailbox.ajax.php?id={msg_id}'
            )
            content = response.text
            
            # Pattern phổ biến cho OTP từ config
            for pattern in OTP_PATTERNS:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    otp = match.group(1)
                    logger.info(f"Tìm thấy OTP: {otp}")
                    return otp
            
            return None
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return None


class OneSecMail(TempEmailService):
    """Service sử dụng 1secmail.com"""
    
    def __init__(self):
        self.session = requests.Session()
        self.email = None
        self.base_url = "https://www.1secmail.com/api/v1/"
    
    def get_email(self) -> str:
        """Tạo email ngẫu nhiên"""
        try:
            params = {'action': 'genRandomMailbox', 'count': 1}
            response = self.session.get(self.base_url, params=params, timeout=10)
            if response.status_code != 200:
                print(f"Loi API 1secmail: HTTP {response.status_code}")
                return ""
            self.email = response.json()[0]
            print(f"Email tam thoi: {self.email}")
            return self.email
        except Exception as e:
            print(f"Loi 1secmail: {e}")
            return ""

    def get_messages(self) -> list:
        """Lấy tin nhắn"""
        try:
            user, domain = self.email.split('@')
            params = {'action': 'getMessages', 'login': user, 'domain': domain}
            response = self.session.get(self.base_url, params=params)
            return response.json() if response.status_code == 200 else []
        except:
            return []

    def extract_otp(self, message: Dict) -> Optional[str]:
        """Trích xuất OTP"""
        try:
            user, domain = self.email.split('@')
            params = {'action': 'readMessage', 'login': user, 'domain': domain, 'id': message['id']}
            response = self.session.get(self.base_url, params=params)
            content = response.json().get('body', '')
            
            for pattern in OTP_PATTERNS:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    otp = match.group(1)
                    print(f"✓ Tìm thấy OTP: {otp}")
                    return otp
            return None
        except:
            return None


class TempMail(TempEmailService):
    """Service sử dụng temp-mail.org API"""
    
    def __init__(self):
        self.session = requests.Session()
        self.email = None
        self.api_url = "https://api.temp-mail.org/request"
    
    def _generate_email(self) -> str:
        """Tạo email ngẫu nhiên"""
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        # Lấy domain khả dụng
        try:
            response = self.session.get(f"{self.api_url}/domains/format/json/")
            domains = response.json()
            domain = random.choice(domains) if domains else "@temporary-mail.net"
            return f"{username}{domain}"
        except:
            return f"{username}@temporary-mail.net"
    
    def get_email(self) -> str:
        """Tạo email tạm thời"""
        self.email = self._generate_email()
        print(f"✓ Email tạm thời: {self.email}")
        return self.email
    
    def get_messages(self) -> list:
        """Lấy tin nhắn"""
        try:
            email_hash = hashlib.md5(self.email.encode()).hexdigest()
            response = self.session.get(
                f"{self.api_url}/mail/id/{email_hash}/format/json/"
            )
            return response.json() if response.status_code == 200 else []
        except:
            return []
    
    def extract_otp(self, message: Dict) -> Optional[str]:
        """Trích xuất OTP"""
        content = message.get('mail_text', '') + message.get('mail_html', '')
        
        for pattern in OTP_PATTERNS:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                otp = match.group(1)
                print(f"✓ Tìm thấy OTP: {otp}")
                return otp
        
        return None


class RegistrationBot:
    """Bot tự động đăng ký tài khoản"""
    
    def __init__(self, email_service: TempEmailService):
        self.email_service = email_service
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def register_account(self, 
                        registration_url: str,
                        email_field: str = 'email',
                        submit_data: Optional[Dict] = None) -> bool:
        """
        Đăng ký tài khoản
        
        Args:
            registration_url: URL form đăng ký
            email_field: Tên field email trong form
            submit_data: Data bổ sung (username, password, etc.)
        """
        try:
            # 1. Lấy email tạm thời
            email = self.email_service.get_email()
            
            # 2. Chuẩn bị data đăng ký
            form_data = submit_data or {}
            form_data[email_field] = email
            
            print(f"\n→ Đang đăng ký tài khoản...")
            print(f"  URL: {registration_url}")
            print(f"  Data: {form_data}")
            
            # 3. Submit form đăng ký
            response = self.session.post(registration_url, data=form_data)
            
            if response.status_code != 200:
                print(f"✗ Đăng ký thất bại: HTTP {response.status_code}")
                return False
            
            print(f"✓ Đã gửi yêu cầu đăng ký")
            return True
            
        except Exception as e:
            print(f"✗ Lỗi đăng ký: {e}")
            return False
    
    def wait_for_otp(self, timeout: int = 120, check_interval: int = 5) -> Optional[str]:
        """
        Đợi và lấy mã OTP từ email
        
        Args:
            timeout: Thời gian chờ tối đa (giây)
            check_interval: Khoảng thời gian kiểm tra (giây)
        """
        print(f"\n→ Đang chờ OTP (timeout: {timeout}s)...")
        
        start_time = time.time()
        last_message_count = 0
        
        while time.time() - start_time < timeout:
            try:
                messages = self.email_service.get_messages()
                
                if len(messages) > last_message_count:
                    print(f"✓ Nhận được {len(messages)} email mới")
                    
                    # Kiểm tra email mới nhất
                    for message in messages:
                        otp = self.email_service.extract_otp(message)
                        if otp:
                            return otp
                    
                    last_message_count = len(messages)
                
                # Hiển thị progress
                elapsed = int(time.time() - start_time)
                print(f"  ⏳ Đã chờ {elapsed}/{timeout}s...", end='\r')
                
                time.sleep(check_interval)
                
            except Exception as e:
                print(f"\n✗ Lỗi kiểm tra email: {e}")
                time.sleep(check_interval)
        
        print(f"\n✗ Timeout! Không nhận được OTP sau {timeout}s")
        return None
    
    def submit_otp(self, 
                   verify_url: str,
                   otp: str,
                   otp_field: str = 'otp',
                   extra_data: Optional[Dict] = None) -> bool:
        """
        Submit mã OTP để xác thực
        
        Args:
            verify_url: URL verify OTP
            otp: Mã OTP
            otp_field: Tên field OTP
            extra_data: Data bổ sung
        """
        try:
            form_data = extra_data or {}
            form_data[otp_field] = otp
            
            print(f"\n→ Đang xác thực OTP...")
            print(f"  URL: {verify_url}")
            print(f"  OTP: {otp}")
            
            response = self.session.post(verify_url, data=form_data)
            
            if response.status_code == 200:
                print(f"✓ Xác thực thành công!")
                return True
            else:
                print(f"✗ Xác thực thất bại: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"✗ Lỗi xác thực: {e}")
            return False
    
    def auto_register(self,
                     registration_url: str,
                     verify_url: str,
                     registration_data: Dict,
                     otp_timeout: int = 120) -> bool:
        """
        Tự động đăng ký và xác thực OTP
        
        Args:
            registration_url: URL đăng ký
            verify_url: URL verify OTP
            registration_data: Data đăng ký (email, password, etc.)
            otp_timeout: Timeout chờ OTP
        """
        print("=" * 60)
        print("🤖 BẮT ĐẦU QUY TRÌNH TỰ ĐỘNG ĐĂNG KÝ")
        print("=" * 60)
        
        # Bước 1: Đăng ký tài khoản
        if not self.register_account(registration_url, submit_data=registration_data):
            return False
        
        # Bước 2: Chờ OTP
        otp = self.wait_for_otp(timeout=otp_timeout)
        if not otp:
            return False
        
        # Bước 3: Submit OTP
        if not self.submit_otp(verify_url, otp):
            return False
        
        print("\n" + "=" * 60)
        print("✓ HOÀN THÀNH ĐĂNG KÝ THÀNH CÔNG!")
        print("=" * 60)
        return True


# ==================== EXAMPLE USAGE ====================

def example_usage():
    """Ví dụ sử dụng"""
    
    # Chọn email service
    # email_service = TenMinuteMail()
    email_service = TempMail()
    
    # Khởi tạo bot
    bot = RegistrationBot(email_service)
    
    # Ví dụ 1: Đăng ký thủ công từng bước
    print("\n📧 VÍ DỤ 1: ĐĂNG KÝ THỦ CÔNG\n")
    
    email = email_service.get_email()
    
    # Giả lập đăng ký (thay bằng URL thật)
    # bot.register_account(
    #     registration_url="https://example.com/register",
    #     submit_data={
    #         'email': email,
    #         'username': 'testuser123',
    #         'password': 'SecurePass123!'
    #     }
    # )
    
    # Chờ OTP
    otp = bot.wait_for_otp(timeout=60)
    
    if otp:
        print(f"\n✓ Đã lấy được OTP: {otp}")
        # bot.submit_otp(
        #     verify_url="https://example.com/verify",
        #     otp=otp
        # )
    
    # Ví dụ 2: Tự động hoàn toàn
    print("\n\n🤖 VÍ DỤ 2: TỰ ĐỘNG HOÀN TOÀN\n")
    
    # bot.auto_register(
    #     registration_url="https://example.com/register",
    #     verify_url="https://example.com/verify",
    #     registration_data={
    #         'username': 'autouser123',
    #         'password': 'AutoPass123!',
    #         'fullname': 'Auto User'
    #     },
    #     otp_timeout=120
    # )


if __name__ == "__main__":
    example_usage()
