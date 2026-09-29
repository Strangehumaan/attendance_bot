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

**Commands:** `/attendance` · `/refresh` (new CAPTCHA) · `/cancel`

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and get your chat ID from [@userinfobot](https://t.me/userinfobot).
2. Copy `config.example.txt` to `config.txt` and fill it in.
3. Edit the settings at the top of `attendance_bot.py` (`ACAD_YEAR`, `SEMESTER`, `START_DATE`, `SHORT_NAMES`).
4. Run it:

**On your PC**
```bash
pip install -r requirements.txt
python -m playwright install chromium
python attendance_bot.py
```

**24/7 on Oracle Cloud Always Free** (so your PC can stay off)
- Create an Ubuntu **22.04** VM (Ampere A1) in an **Indian region** (Mumbai or Hyderabad). The portal seems to block foreign servers.
- Put it on a **public subnet** with a public IP.
- Copy `attendance_bot.py`, `config.txt` and `server_setup.sh` to `~/bot/` on the server, then run `bash ~/bot/server_setup.sh`.
- The script checks that the portal is reachable, installs everything, and runs the bot as a `systemd` service.



---

Made for my own use at MPSTME . Use it only with your own account.
