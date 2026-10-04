"""Telegram attendance bot (runs in the background on your PC).

Send /attendance to your bot  ->  it opens the SVKM portal, fills your login,
sends you the CAPTCHA picture, you reply with the letters, and it sends back
your attendance table.
Commands:  /attendance   /refresh (new CAPTCHA)   /cancel   /testlogin
"""
import re, sys, html, time, socket, datetime, pathlib, traceback, collections, requests, pdfplumber
from playwright.sync_api import sync_playwright

# ---------------- Settings ----------------
ACAD_YEAR  = "Acad .Year 2026-2027"   # change when a new year starts
SEMESTER   = "Semester VII"           # change when a new semester starts
REPORT     = "Detail Report"
START_DATE = "13.07.2026"             # first day counted
CAPTCHA_REPLY_MIN = 15                # how long to wait for your CAPTCHA reply
MAX_CAPTCHA_TRIES = 3
WARN_BELOW = 80                       # subjects under this % get a "!"
HEADLESS = True                        # False = show the browser window on your PC
OPEN_FROM  = datetime.time(18, 0)     # portal lets you view attendance only from 06:00 PM...
OPEN_UNTIL = datetime.time(7, 0)      # ...until 07:00 AM (next morning)
SHORT_NAMES = {                       # short names for the table
    "technical writing": "Tech Writing",
    "distributed computing": "Distributed Comp",
    "computer vision for ai": "Computer Vision",
    "human computer interaction": "HCI",
    "applied time series analysis": "Time Series",
}
# ------------------------------------------

HERE = pathlib.Path(__file__).parent
REPORTS = HERE / "reports"; REPORTS.mkdir(exist_ok=True)
LOGS = HERE / "logs"; LOGS.mkdir(exist_ok=True)
URL = "https://sdc-sppap1.svkm.ac.in:50001/irj/portal"
CMD_ATTENDANCE = re.compile(r"^/+\s*attend", re.I)

def scrub(text):
    """Hide secrets (bot token, password) if they ever appear in logs or error messages."""
    text = str(text)
    for key in ("TELEGRAM_BOT_TOKEN", "PORTAL_PASS"):
        secret = globals().get("CFG", {}).get(key)
        if secret:
            text = text.replace(secret, f"<{key}>")
    return text

def log(*a):
    line = scrub(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] " + " ".join(str(x) for x in a))
    try:
        print(line)
    except Exception:
        pass
    with open(LOGS / "bot.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")

def load_config():
    cfg = {}
    for line in (HERE / "config.txt").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); cfg[k.strip()] = v.strip()
    return cfg

CFG = load_config()
CHAT_ID = str(CFG["TELEGRAM_CHAT_ID"])

# ---------------- Telegram ----------------
class Telegram:
    def __init__(self, token):
        self.api = f"https://api.telegram.org/bot{token}"
        self.offset = None

    def send(self, text, html_mode=False):
        data = {"chat_id": CHAT_ID, "text": text}
        if html_mode:
            data["parse_mode"] = "HTML"
        try:
            requests.post(f"{self.api}/sendMessage", data=data, timeout=20)
        except Exception as e:
            log("send failed:", e)

    def send_photo(self, png_bytes, caption):
        try:
            requests.post(f"{self.api}/sendPhoto", data={"chat_id": CHAT_ID, "caption": caption},
                          files={"photo": ("captcha.png", png_bytes)}, timeout=30)
        except Exception as e:
            log("photo failed:", e)

    def set_commands(self):
        """Show the command list when you type / in Telegram."""
        commands = [{"command": "attendance", "description": "Get your attendance report"},
                    {"command": "refresh", "description": "Send a new CAPTCHA"},
                    {"command": "cancel", "description": "Stop the current request"},
                    {"command": "testlogin", "description": "Check your portal ID and password"},
                    {"command": "help", "description": "How to use this bot"}]
        try:
            requests.post(f"{self.api}/setMyCommands", json={"commands": commands}, timeout=20)
        except Exception as e:
            log("set_commands failed:", e)

    def skip_old_messages(self):
        """Ignore anything sent while the bot was off."""
        try:
            r = requests.get(f"{self.api}/getUpdates", params={"offset": -1, "timeout": 0}, timeout=20).json()
            if r.get("result"):
                self.offset = r["result"][-1]["update_id"] + 1
        except Exception as e:
            log("skip_old failed:", e)

    def poll(self, wait=25):
        """Return new text messages from YOUR chat only."""
        try:
            r = requests.get(f"{self.api}/getUpdates",
                             params={"offset": self.offset, "timeout": wait}, timeout=wait + 10).json()
        except Exception as e:
            log("poll failed:", e); time.sleep(5); return []
        texts = []
        for u in r.get("result", []):
            self.offset = u["update_id"] + 1
            m = u.get("message") or {}
            if str(m.get("chat", {}).get("id")) == CHAT_ID and m.get("text"):
                texts.append(m["text"].strip())
        return texts

TG = Telegram(CFG["TELEGRAM_BOT_TOKEN"])

class Cancelled(Exception):
    pass

class LoginFailed(Cancelled):
    """Portal rejected every try: wrong CAPTCHA, or wrong ID/password."""

def wait_for_reply(minutes):
    """Wait for your next message. Returns the text, or None on timeout."""
    end = time.time() + minutes * 60
    while time.time() < end:
        for t in TG.poll(wait=20):
            return t
    return None

# ---------------- portal ----------------
def work_frame(page):
    for _ in range(90):
        for f in page.frames:
            try:
                if f.locator('label:has-text("Academic Year")').count():
                    return f
            except Exception:
                pass
        page.wait_for_timeout(1000)
    raise RuntimeError("Attendance form did not load")

def field_id(frame, label):
    lab = frame.locator(f'label:has-text("{label}")').first
    for _ in range(20):
        fid = lab.get_attribute("for")
        if fid:
            return fid
        frame.page.wait_for_timeout(500)
    raise RuntimeError(f"Field '{label}' never became available")

def pick(frame, label, option):
    fid = field_id(frame, label)
    btn = frame.locator(f"#{fid}-btn")
    (btn if btn.count() else frame.locator(f"#{fid}")).click()
    frame.page.wait_for_timeout(1000)
    frame.get_by_text(option, exact=True).last.click()
    frame.page.wait_for_timeout(3000)
    val = frame.locator(f"#{fid}").input_value()
    log("Selected", label, "->", val)
    if val != option:
        raise RuntimeError(f"Could not select '{option}' in {label} (got '{val}')")

def fill_date(frame, index, value):
    """index 0 = Start Date, 1 = End Date (portal labels both point to the start box)."""
    frame.locator('label:has-text("Start Date")[for]').first.wait_for(timeout=20_000)
    box = frame.locator('input.lsField__input:not([role="listbox"])').nth(index)
    box.click(); box.fill(value); box.press("Tab")
    frame.page.wait_for_timeout(2000)
    log("Filled", ["Start", "End"][index], "Date ->", box.input_value())

def captcha_picture(page):
    try:
        return page.locator("form").first.screenshot()
    except Exception:
        return page.screenshot()

def login_with_relay(page, done_msg="Logged in. Getting your report..."):
    """Fill ID + password, send you the CAPTCHA picture, type your reply."""
    attendance_tab = page.get_by_role("cell", name="Attendance Display for Students", exact=True)
    for attempt in range(1, MAX_CAPTCHA_TRIES + 1):
        page.get_by_role("textbox", name=re.compile(r"^User")).fill(CFG["PORTAL_USER"])
        page.locator("input[type=password]").fill(CFG["PORTAL_PASS"])
        captcha_box = page.get_by_role("textbox", name=re.compile("Captcha"))
        TG.send_photo(captcha_picture(page),
                      "Reply with the CAPTCHA letters (case-sensitive).\n/refresh = new CAPTCHA, /cancel = stop")
        while True:
            reply = wait_for_reply(CAPTCHA_REPLY_MIN)
            if reply is None:
                raise Cancelled(f"No CAPTCHA reply within {CAPTCHA_REPLY_MIN} min, stopped.")
            if reply.lower().startswith("/cancel"):
                raise Cancelled("Cancelled.")
            if reply.lower().startswith("/refresh"):
                page.locator("#refresh").click(); page.wait_for_timeout(1500)
                TG.send_photo(captcha_picture(page), "New CAPTCHA. Reply with the letters.")
                continue
            if CMD_ATTENDANCE.match(reply) or reply.lower().startswith("/testlogin"):
                TG.send("Already working on it. Reply with the CAPTCHA letters.")
                continue
            break
        captcha_box.fill(reply)
        page.get_by_role("button", name="Log On").click()
        try:
            attendance_tab.wait_for(timeout=25_000)
            log("Logged in")
            TG.send(done_msg)
            return attendance_tab
        except Exception:
            log("Login failed, attempt", attempt)
            if attempt < MAX_CAPTCHA_TRIES:
                TG.send("That didn't work (wrong CAPTCHA?). Here's a new one.")
                page.goto(URL)
    raise LoginFailed("Login failed after several tries. Send /attendance to try again.")

def test_login():
    """Log in and stop, no report. Used by /testlogin and check_setup.py."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, channel="chromium")
        page = browser.new_context(ignore_https_errors=True).new_page()
        try:
            page.goto(URL)
            login_with_relay(page, done_msg="Logged in. Your portal ID and password work.")
        finally:
            browser.close()

def download_report(pdf_path):
    end_date = datetime.date.today().strftime("%d.%m.%Y")
    with sync_playwright() as p:
        # channel="chromium" = full Chrome (has the PDF viewer) even when hidden
        browser = p.chromium.launch(headless=HEADLESS, channel="chromium")
        ctx = browser.new_context(ignore_https_errors=True, accept_downloads=True,
                                  viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        pdf_urls, downloads = [], []
        page.on("download", lambda d: downloads.append(d))   # hidden browser: PDF arrives as a download
        ctx.on("response", lambda r: pdf_urls.append(r.url)
               if "pdf" in (r.headers.get("content-type") or "").lower() and r.url.startswith("http") else None)
        try:
            page.goto(URL)
            login_with_relay(page).click()
            frame = work_frame(page)
            pick(frame, "Academic Year", ACAD_YEAR)
            pick(frame, "Trimester/Semester", SEMESTER)
            pick(frame, "Monthly/Detailed", REPORT)
            fill_date(frame, 0, START_DATE)
            fill_date(frame, 1, end_date)
            frame.locator('[ct="B"]', has_text="SUBMIT").first.click()
            log("Waiting for the PDF report...")
            for i in range(90):
                if pdf_urls or downloads:
                    break
                if i == 20:   # backup: click a Download button if the portal shows one
                    for f in page.frames:
                        try:
                            btn = f.locator('[ct="B"], button, a').filter(has_text=re.compile("download", re.I))
                            if btn.count():
                                log("Clicking Download button")
                                btn.first.click(); break
                        except Exception:
                            pass
                page.wait_for_timeout(1000)
            for d in downloads:
                d.save_as(str(pdf_path))
                if pdf_path.read_bytes()[:4] == b"%PDF":
                    log("Saved", pdf_path.name, "(download)")
                    return
            for u in pdf_urls:
                data = ctx.request.get(u).body()
                if data[:4] == b"%PDF":
                    pdf_path.write_bytes(data); log("Saved", pdf_path.name)
                    return
            raise RuntimeError("The portal did not return a PDF report")
        finally:
            try:
                page.screenshot(path=str(LOGS / "last_screen.png"))
            except Exception:
                pass
            ctx.close(); browser.close()

# ---------------- report ----------------
def parse(pdf_path):
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for pg in pdf.pages:
            for t in pg.extract_tables():
                for r in t:
                    if r and len(r) >= 6 and (r[0] or "").strip().isdigit():
                        rows.append([(c or "").replace("\n", " ").strip() for c in r])
    if not rows:
        raise RuntimeError("No attendance rows found in the PDF")
    return rows

def subject_base(course):
    m = re.match(r"(.*?)\s*[TP]\d\b", course)
    return (m.group(1) if m else course).strip().lower()

def same_subject(a, b):
    wa, wb = a.split(), b.split()
    return len(wa) == len(wb) and all(x.startswith(y) or y.startswith(x) for x, y in zip(wa, wb))

def short_name(base):
    for full, short in SHORT_NAMES.items():
        if same_subject(base, full):
            return short
    return base.title()[:16]

def summary(rows):
    groups = []
    for r in rows:
        base, status = subject_base(r[1]), r[5].upper()
        for g in groups:
            if same_subject(g[0], base):
                if len(base) > len(g[0]):
                    g[0] = base
                g[1][status] += 1
                break
        else:
            groups.append([base, collections.Counter({status: 1})])

    def stats(c):
        held = c["P"] + c["A"] + c["E"]
        pct = 100 * (c["P"] + c["E"]) / held if held else 100
        return c["A"], held, pct

    total = sum((g[1] for g in groups), collections.Counter())
    missed, held, pct = stats(total)
    table = [f"{'Subject':<16} {'Miss':>4} {'Held':>4} {'Att':>5}", "-" * 32]
    for base, c in sorted(groups, key=lambda g: stats(g[1])[2]):
        a, h, p_ = stats(c)
        table.append(f"{short_name(base):<16} {a:>4} {h:>4} {p_:>4.0f}%{'!' if p_ < WARN_BELOW else ' '}")
    table += ["-" * 32, f"{'TOTAL':<16} {missed:>4} {held:>4} {pct:>4.0f}%"]
    msg = (f"<b>Attendance update</b>\n{START_DATE} to {datetime.date.today():%d.%m.%Y}\n\n"
           f"You have missed <b>{missed}</b> of {held} classes (<b>{pct:.1f}%</b> attendance).\n\n"
           f"<pre>{html.escape(chr(10).join(table))}</pre>")
    if any(stats(g[1])[2] < WARN_BELOW for g in groups):
        msg += f"\n! = below {WARN_BELOW}%"
    if total["NU"]:
        msg += f"\n{total['NU']} class(es) not updated on the portal yet (not counted)."
    return msg

def portal_open(now=None):
    """True between OPEN_FROM and OPEN_UNTIL (the window crosses midnight)."""
    t = (now or datetime.datetime.now()).time()
    return t >= OPEN_FROM or t < OPEN_UNTIL

def run_report(reason):
    if not portal_open():
        log("Refused, outside viewing hours:", reason)
        TG.send(f"The portal doesn't allow viewing attendance right now. "
                f"Please try between {OPEN_FROM:%I:%M %p} and {OPEN_UNTIL:%I:%M %p}.")
        return
    log("Run started:", reason)
    TG.send("Opening the portal...")
    pdf_path = REPORTS / f"attendance_{datetime.date.today()}.pdf"
    try:
        download_report(pdf_path)
        TG.send(summary(parse(pdf_path)), html_mode=True)
        log("Run finished")
    except Cancelled as e:
        log("Stopped:", e); TG.send(str(e))
    except Exception as e:
        log("FAILED:", traceback.format_exc())
        TG.send(scrub(f"Attendance bot failed: {e}\nSend /attendance to try again."))
    finally:
        pdf_path.unlink(missing_ok=True)   # PDF is only needed to build the message

def run_login_test():
    log("Login test started")
    TG.send("Testing your portal login...")
    try:
        test_login()
        log("Login test passed")
    except LoginFailed as e:
        log("Login test failed:", e)
        TG.send("Login failed after several tries. If the CAPTCHA was right, "
                "check PORTAL_USER and PORTAL_PASS in config.txt.")
    except Cancelled as e:
        log("Stopped:", e); TG.send(str(e))
    except Exception as e:
        log("FAILED:", traceback.format_exc())
        TG.send(scrub(f"Login test failed: {e}"))

# ---------------- main loop ----------------
def main():
    try:   # only one copy of the bot at a time
        lock = socket.socket(); lock.bind(("127.0.0.1", 47831))
    except OSError:
        log("Bot already running, exiting."); return
    TG.skip_old_messages()
    TG.set_commands()
    log("Bot started")
    while True:
        try:
            for text in TG.poll(wait=25):
                if CMD_ATTENDANCE.match(text):
                    run_report("requested on Telegram")
                elif text.lower().startswith("/testlogin"):
                    run_login_test()
                elif text.lower().startswith(("/start", "/help")):
                    TG.send("Send /attendance to get your attendance report "
                            f"(works {OPEN_FROM:%I:%M %p} to {OPEN_UNTIL:%I:%M %p}).\n"
                            "While logging in: /refresh = new CAPTCHA, /cancel = stop.\n"
                            "/testlogin = check your portal ID and password work.")
        except Exception:
            log("loop error:", traceback.format_exc()); time.sleep(10)

if __name__ == "__main__":
    main()
