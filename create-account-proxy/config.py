"""
Config cho các website phổ biến
Bạn có thể thêm config cho website cần đăng ký
"""

# Các pattern OTP phổ biến
OTP_PATTERNS = [
    r'(?:OTP|code|mã|Code|CODE)(?:\s*:?\s*)(\d{4,8})',
    r'(?:verification|xác thực)(?:\s*code\s*:?\s*)(\d{4,8})',
    r'<b>(\d{4,8})</b>',
    r'<strong>(\d{4,8})</strong>',
    r'(\d{4,8})\s*(?:is your|là mã)',
    r'\b(\d{6})\b',  # 6 chữ số (Để cuối cùng để tránh bắt lầm)
    r'\b(\d{4})\b',  # 4 chữ số
    r'\b(\d{8})\b',  # 8 chữ số
]

# Config cho từng website
WEBSITE_CONFIGS = {
    "example_site": {
        "name": "Example Website",
        "registration_url": "https://example.com/api/register",
        "verify_url": "https://example.com/api/verify",
        "fields": {
            "email": "email",
            "username": "username", 
            "password": "password",
            "otp": "verification_code"
        },
        "headers": {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        },
        "method": "POST",  # hoặc "GET"
        "data_format": "json",  # hoặc "form"
    },
    
    "shopee_vn": {
        "name": "Shopee Vietnam",
        "registration_url": "https://shopee.vn/buyer/signup",
        "verify_url": "https://shopee.vn/verify/otp",
        "fields": {
            "email": "email",
            "password": "password",
            "otp": "otp_code"
        }
    },
    
    "lazada_vn": {
        "name": "Lazada Vietnam", 
        "registration_url": "https://member.lazada.vn/user/register",
        "verify_url": "https://member.lazada.vn/user/verify",
        "fields": {
            "email": "loginId",
            "password": "password",
            "otp": "verifyCode"
        }
    },
    
    # Thêm website của bạn tại đây
    "your_website": {
        "name": "Your Website Name",
        "registration_url": "https://yoursite.com/register",
        "verify_url": "https://yoursite.com/verify-otp",
        "fields": {
            "email": "email",
            "username": "user_name",
            "password": "pass",
            "otp": "otp_code"
        },
        "extra_data": {
            # Thêm fields cố định nếu cần
            "country": "VN",
            "language": "vi"
        }
    }
}

# User agents để rotate
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

# Email services khả dụng
EMAIL_SERVICES = {
    "10minutemail": {
        "class": "TenMinuteMail",
        "reliability": "high",
        "speed": "fast"
    },
    "tempmail": {
        "class": "TempMail", 
        "reliability": "medium",
        "speed": "medium"
    },
    "guerrillamail": {
        "url": "https://www.guerrillamail.com/",
        "reliability": "high",
        "speed": "fast"
    }
}
