# 📋 Attendance Bot

A tiny Telegram bot that fetches my attendance from the **SVKM NMIMS student portal** and sends me a clean per-subject table, no laptop, no portal-clicking, no guessing.

> ⚠️ **University-specific.** This only works with the SVKM NMIMS SAP portal (`sdc-sppap1.svkm.ac.in`). It is **not** a general attendance tool, and it's an unofficial personal project, not affiliated with the university.

## Why this exists

I wanted to build this for *so long*. Every "how much attendance do I have?" meant logging in, clicking through SAP, downloading a PDF and counting rows by hand, or walking to my mentor to ask 😂

Then I found out **Oracle Cloud gives you an Always Free server**. No idea how I missed that. So it's finally done. It was vibecoded with Claude in one long night.

## How it works

```
You: /attendance
Bot: 📷 [CAPTCHA picture]   "reply with the letters"
You: 2!ps$C
Bot: Logged in. Getting your report...
Bot: You have missed 35 of 193 classes (81.9%)

     Subject          Miss Held   Att
     --------------------------------
     Tech Writing        7   27   74%!
     Distributed Comp    9   41   78%!
     ...
```

1. The bot opens the portal in a hidden Chrome (Playwright) and fills your ID and password.
2. It sends you the CAPTCHA on Telegram. **You** solve it. Nothing is bypassed.
3. It fills the attendance form (year, semester, detail report, start date to today).
4. It grabs the PDF report, parses it with `pdfplumber`, and merges theory and practical per subject.
5. It replies with the table. `!` marks subjects below 80%.

**Commands:** `/attendance` · `/refresh` (new CAPTCHA) · `/cancel` · `/testlogin` (check your portal ID and password; logs in and stops)

The portal only shows attendance between **06:00 PM and 07:00 AM**, so outside those hours the bot just tells you to try later.

## Setup

Everyone runs their **own** copy: the bot only answers the one Telegram chat in its `config.txt` and logs in with that person's portal account. `config.txt` is git-ignored, so your password never gets pushed. Never share it.

### 24/7 on a free Oracle Cloud server (recommended, about 30 min)

The bot keeps running even when your laptop is off.

**1. Make your Telegram bot**
- Open [@BotFather](https://t.me/BotFather), send `/newbot`, and copy the **token** it gives you.
- Open your new bot and press **Start**.
- Open [@userinfobot](https://t.me/userinfobot) and copy your **ID** number.

**2. Make an Oracle Cloud account**
- Sign up at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/). It asks for a card to verify you, but the Always Free server costs nothing.
- ⚠️ Pick **India West (Mumbai)** or **India South (Hyderabad)** as your **Home Region**. It can't be changed later, and the portal blocks servers outside India.

**3. Create the server**
- **Menu → Compute → Instances → Create instance**
- **Image:** Canonical **Ubuntu 22.04**
- **Shape:** **Ampere → VM.Standard.A1.Flex** (1 OCPU, 6 GB memory is enough)
- **Networking:** a public subnet, with **Assign a public IPv4 address** on
- **SSH keys:** **Generate a key pair for me → Download private key**
- Click **Create**. Once it's running, copy its **Public IP address**.
- "Out of capacity"? Try again later or pick a different Availability Domain.

**4. Connect to it** (Windows `cmd`, use your own key file name and IP, type `yes` the first time)
```bash
ssh -i Downloads\ssh-key-XXXX.key ubuntu@YOUR_SERVER_IP
```

**5. Get the code and add your details**
```bash
git clone https://github.com/Strangehumaan/attendance_bot.git ~/bot
cp ~/bot/config.example.txt ~/bot/config.txt
nano ~/bot/config.txt
```
Fill in your portal ID, portal password, bot token and Telegram ID (no spaces, no quotes). Save with **Ctrl+O → Enter → Ctrl+X**.

```bash
nano ~/bot/attendance_bot.py
```
At the top, set `ACAD_YEAR`, `SEMESTER` and `START_DATE` exactly as they appear in your portal. `SHORT_NAMES` is optional (unknown subjects just get a shortened name). Save the same way.

**6. Install and start the bot** (5–10 min)
```bash
bash ~/bot/server_setup.sh
```
It checks the portal is reachable, installs everything, sets the clock to India time, and runs the bot as a service that restarts by itself. When it says **DONE**, you're set. If it says *"The SVKM portal blocks this server"*, the server isn't in an Indian region (step 2).

**7. Test it on Telegram**
- Send `/testlogin` and reply with the CAPTCHA letters. You should get **"Your portal ID and password work."**
- Send `/attendance` between **6 PM and 7 AM**. Type `/` to see all commands.

**Later**
- **Update:** connect (step 4), then `cd ~/bot && git pull && sudo systemctl restart attendance-bot`
- **Bot not replying?** `tail -20 ~/bot/logs/bot.log`
- **SSH says "bad permissions" on the key?** In `cmd`: `icacls Downloads\ssh-key-XXXX.key /inheritance:r /grant:r "%USERNAME%:R"`

### On your PC instead

Works only while your PC is on and the bot window is open.

1. Do step 1 above (Telegram bot) and install [Python](https://www.python.org/downloads/) (tick **Add Python to PATH**).
2. Clone the repo (or **Code → Download ZIP** and extract it):
   ```bash
   git clone https://github.com/Strangehumaan/attendance_bot.git
   ```
3. Copy `config.example.txt` to `config.txt` and fill it in, then set `ACAD_YEAR`, `SEMESTER`, `START_DATE` at the top of `attendance_bot.py`.
4. Install, check, run:
   ```bash
   pip install -r requirements.txt
   python -m playwright install chromium
   python check_setup.py
   python attendance_bot.py
   ```
   `check_setup.py` checks `config.txt`, Telegram and the portal, then does a real login (CAPTCHA on Telegram) and tells you exactly what to fix if something is wrong. Run it while the bot is stopped.


---

Made for my own use at MPSTME . Use it only with your own account.
