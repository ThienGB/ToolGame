# 🤖 Auto Registration Bot với OTP Email

Tool tự động hóa đăng ký tài khoản với xác thực OTP qua email tạm thời.

## 📋 Tính năng

- Tự động tạo email tạm thời (10minutemail, temp-mail)
- Đăng ký tài khoản tự động
- Lấy mã OTP từ email tự động
- Xác thực OTP tự động
- Hỗ trợ cả HTTP requests và Selenium

## 🛠️ Cài đặt

```bash
pip install requests beautifulsoup4 selenium --break-system-packages
```

## 🚀 Sử dụng nhanh

```python
from account_registration_bot import RegistrationBot, TempMail

email_service = TempMail()
bot = RegistrationBot(email_service)

# Tự động đăng ký
bot.auto_register(
    registration_url="https://api.example.com/register",
    verify_url="https://api.example.com/verify",
    registration_data={
        'username': 'myuser123',
        'password': 'SecurePass123!'
    },
    otp_timeout=120
)
```

Xem chi tiết trong code!
