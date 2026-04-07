import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def test_developermail():
    try:
        req = urllib.request.Request("https://www.developermail.com/api/v1/mailbox", headers={'Accept': 'application/json'})
        req.get_method = lambda: 'PUT'
        with urllib.request.urlopen(req, context=ctx) as response:
            data = json.loads(response.read().decode())
            name = data['result']['name']
            token = data['result']['token']
            print("Developermail created:", f"{name}@developermail.com")
            
            # test get messages (which returns IDs)
            req_msg = urllib.request.Request(f"https://www.developermail.com/api/v1/mailbox/{name}", headers={'Accept': 'application/json', 'X-MailboxToken': token})
            with urllib.request.urlopen(req_msg, context=ctx) as res_msg:
                msgs = json.loads(res_msg.read().decode())
                print("Messages:", msgs['result'])
                
    except Exception as e:
        print("Developermail error:", e)

if __name__ == "__main__":
    with open("mail_test_output.txt", "w") as f:
        import sys
        sys.stdout = f
        sys.stderr = f
        test_developermail()
