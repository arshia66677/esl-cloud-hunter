import os
import time
import base64
import sqlite3
import schedule
import requests
from email.message import EmailMessage
from bs4 import BeautifulSoup
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from threading import Thread

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

DEFAULT_SUBJECT = "Application for ESL Instructor - {company}"
DEFAULT_BODY = """Dear Hiring Team at {company},

I am writing to express my interest in teaching ESL with your team.
I have extensive experience teaching young learners and adults with engaging, structured curricula.

Attached are my credentials. Looking forward to your response.

Best regards,"""

app = Flask(__name__)
CORS(app)

def init_db():
    conn = sqlite3.connect("cloud_leads.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT,
            url TEXT UNIQUE,
            students TEXT,
            pay TEXT,
            date_discovered TEXT,
            draft_status TEXT DEFAULT 'Pending'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            subject TEXT,
            body TEXT
        )
    """)
    c.execute("INSERT OR IGNORE INTO settings (id, subject, body) VALUES (1, ?, ?)", (DEFAULT_SUBJECT, DEFAULT_BODY))
    conn.commit()
    conn.close()

def send_telegram(company, url, pay):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[Telegram] Skipped: Bot tokens not set.")
        return
    text = (
        f"🎯 *New ESL Company Discovered!*\n\n"
        f"🏢 *Company:* {company}\n"
        f"💰 *Pay:* {pay}\n"
        f"🔗 *Apply Link:* {url}\n"
        f"📅 *Discovered:* {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"[Telegram Error] {e}")

def scrape():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 Cloud Scraper scanning job boards...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get("https://www.eslcafe.com/jobs/international", headers=headers, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for link in soup.find_all("a", href=True):
                title = link.get_text(strip=True)
                href = link["href"]
                if any(k in title.lower() for k in ["online", "remote", "china", "kids", "tutor", "esl"]):
                    full_url = href if href.startswith("http") else f"https://www.eslcafe.com{href}"
                    company = title.split("-")[0].strip() if "-" in title else title[:30]

                    conn = sqlite3.connect("cloud_leads.db")
                    c = conn.cursor()
                    try:
                        c.execute(
                            "INSERT INTO leads (company, url, students, pay, date_discovered) VALUES (?, ?, ?, ?, ?)",
                            (company, full_url, "Young Learners / Adults", "$18 - $25/hr", datetime.now().strftime("%Y-%m-%d"))
                        )
                        conn.commit()
                        print(f"✨ [NEW LEAD FOUND] {company}")
                        send_telegram(company, full_url, "$18 - $25/hr")
                    except sqlite3.IntegrityError:
                        pass
                    finally:
                        conn.close()
    except Exception as e:
        print(f"[Scraper Error] {e}")

@app.route("/api/leads", methods=["GET"])
def get_leads():
    conn = sqlite3.connect("cloud_leads.db")
    c = conn.cursor()
    c.execute("SELECT id, company, url, students, pay, date_discovered, draft_status FROM leads ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        "id": r[0], "company": r[1], "url": r[2], "students": r[3],
        "pay": r[4], "date": r[5], "draftStatus": r[6]
    } for r in rows])

@app.route("/api/settings", methods=["GET", "POST"])
def manage_settings():
    conn = sqlite3.connect("cloud_leads.db")
    c = conn.cursor()
    if request.method == "POST":
        data = request.json or {}
        c.execute("UPDATE settings SET subject = ?, body = ? WHERE id = 1", (data.get('subject', ''), data.get('body', '')))
        conn.commit()
        conn.close()
        return jsonify({"status": "updated"})
    c.execute("SELECT subject, body FROM settings WHERE id = 1")
    row = c.fetchone()
    conn.close()
    return jsonify({"subject": row[0], "body": row[1]})

def run_loop():
    scrape()
    schedule.every(30).minutes.do(scrape)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    init_db()
    Thread(target=run_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
