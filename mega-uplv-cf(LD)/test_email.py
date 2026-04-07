import urllib.request
import json
import random
import string

def test_guerrilla():
    print("Testing GuerrillaMail...")
    url = "http://api.guerrillamail.com/ajax.php?f=get_email_address&ip=127.0.0.1&agent=Mozilla_foo"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            print("Guerrilla:", response.read().decode()[:100])
    except Exception as e:
        print("Guerrilla error:", e)

def test_mail_tm():
    print("Testing Mail.tm...")
    try:
        # Get domains
        req = urllib.request.Request("https://api.mail.tm/domains", headers={'User-Agent': 'Mozilla'})
        with urllib.request.urlopen(req) as response:
            domains = json.loads(response.read().decode())
            domain = domains['hydra:member'][0]['domain']
            print("Domain:", domain)
            
            # Create account
            username = ''.join(random.choices(string.ascii_lowercase, k=10))
            address = f"{username}@{domain}"
            password = "password123"
            
            data = json.dumps({"address": address, "password": password}).encode('utf-8')
            req2 = urllib.request.Request("https://api.mail.tm/accounts", data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla'})
            with urllib.request.urlopen(req2) as res2:
                print("Account created:", address)
    except Exception as e:
        print("Mail.tm error:", e)

if __name__ == "__main__":
    test_guerrilla()
    test_mail_tm()
