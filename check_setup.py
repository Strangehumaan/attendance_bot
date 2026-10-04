"""Setup check: run this once after setup to make sure you can log in.

    python check_setup.py

Checks config.txt, Telegram, that the portal is reachable, then does a real
login (you solve the CAPTCHA on Telegram as usual). It stops right after
logging in, no report is downloaded. Stop the bot before running this.
"""
import sys, socket, pathlib, requests, urllib3

HERE = pathlib.Path(__file__).parent
NEEDED = ("PORTAL_USER", "PORTAL_PASS", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")

def ok(msg):
    print("OK    ", msg)

def fail(msg):
    print("FAIL  ", msg)
    sys.exit(1)

# 1. config.txt
cfg_file = HERE / "config.txt"
if not cfg_file.exists():
    fail("config.txt not found. Copy config.example.txt to config.txt and fill it in.")
cfg = {}
for line in cfg_file.read_text(encoding="utf-8-sig").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); cfg[k.strip()] = v.strip()
missing = [k for k in NEEDED if not cfg.get(k)]
if missing:
    fail("config.txt is missing: " + ", ".join(missing))
ok("config.txt is filled in")

# 2. the bot must not be running (it would grab your CAPTCHA reply)
try:
    lock = socket.socket(); lock.bind(("127.0.0.1", 47831))
except OSError:
    fail("The bot is running. Stop it first, then run this check again.")

# 3. Telegram
api = f"https://api.telegram.org/bot{cfg['TELEGRAM_BOT_TOKEN']}"
try:
    me = requests.get(f"{api}/getMe", timeout=20).json()
except Exception as e:
    fail(f"Can't reach Telegram ({type(e).__name__}). Check your internet.")
if not me.get("ok"):
    fail("TELEGRAM_BOT_TOKEN is wrong. Copy it again from @BotFather.")
r = requests.post(f"{api}/sendMessage", timeout=20,
                  data={"chat_id": cfg["TELEGRAM_CHAT_ID"], "text": "Setup check: Telegram works."}).json()
if not r.get("ok"):
    fail(f"Bot can't message you ({r.get('description')}). Check TELEGRAM_CHAT_ID "
         f"and send /start to @{me['result']['username']} first.")
ok(f"Telegram works (bot @{me['result']['username']})")

# 4. portal reachable
import attendance_bot as bot   # safe now: config is valid
urllib3.disable_warnings()
try:
    requests.get(bot.URL, verify=False, timeout=25)
except Exception:
    fail("Can't reach the SVKM portal. Check your internet. Servers outside India are blocked.")
ok("Portal is reachable")

# 5. real login (you solve the CAPTCHA on Telegram)
from playwright.sync_api import sync_playwright
print("...    Sending you the CAPTCHA on Telegram, reply with the letters.")
bot.TG.skip_old_messages()
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=bot.HEADLESS, channel="chromium")
        page = browser.new_context(ignore_https_errors=True).new_page()
        try:
            page.goto(bot.URL)
            bot.login_with_relay(page)
        finally:
            browser.close()
except bot.Cancelled as e:
    fail(f"{e} If the CAPTCHA was right, check PORTAL_USER and PORTAL_PASS in config.txt.")
except Exception as e:
    fail(bot.scrub(f"Browser problem: {e}\nDid you run: python -m playwright install chromium"))
ok("Logged in to the portal")
bot.TG.send("Setup check passed. Send /attendance once the bot is running.")
print("\nAll good. Start the bot with: python attendance_bot.py")
