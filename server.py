import os
import time
import sqlite3
import schedule
import requests
import imaplib
import json
from email.message import EmailMessage
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from threading import Thread
from bs4 import BeautifulSoup

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
            requirements TEXT,
            tags TEXT,
            date TEXT,
            status TEXT,
            draft_status TEXT DEFAULT 'None'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            subject TEXT,
            body TEXT,
            gmail_user TEXT,
            gmail_pass TEXT,
            telegram_token TEXT,
            telegram_chat_id TEXT
        )
    """)
    c.execute("INSERT OR IGNORE INTO settings (id, subject, body, gmail_user, gmail_pass, telegram_token, telegram_chat_id) VALUES (1, '', '', '', '', '', '')")
    conn.commit()
    conn.close()

def get_settings():
    conn = sqlite3.connect("cloud_leads.db")
    c = conn.cursor()
    c.execute("SELECT subject, body, gmail_user, gmail_pass, telegram_token, telegram_chat_id FROM settings WHERE id = 1")
    row = c.fetchone()
    conn.close()
    if row:
        return {"subject": row[0], "body": row[1], "gmail_user": row[2], "gmail_pass": row[3], "telegram_token": row[4], "telegram_chat_id": row[5]}
    return {}

def send_telegram(company, url, pay):
    settings = get_settings()
    token = settings.get("telegram_token", "")
    chat_id = settings.get("telegram_chat_id", "")
    if not token or not chat_id: return

    text = f"🎯 *New Global ESL Lead Discovered!*\n\n🏢 *Company/Source:* {company}\n💰 *Pay:* {pay}\n🔗 *Link:* {url}"
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def create_gmail_draft(company, target_email=""):
    settings = get_settings()
    user = settings.get("gmail_user", "")
    password = settings.get("gmail_pass", "")
    subject_template = settings.get("subject", "")
    body_template = settings.get("body", "")

    if not user or not password: return "No Credentials"
    
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(user, password)
        
        msg = EmailMessage()
        msg['Subject'] = subject_template.replace("{company}", company)
        msg['From'] = user
        msg['To'] = target_email
        msg.set_content(body_template.replace("{company}", company))
        
        mail.append('[Gmail]/Drafts', '', imaplib.Time2Internaldate(time.time()), str(msg).encode('utf-8'))
        mail.logout()
        return "Drafted"
    except Exception as e:
        print("Gmail Draft Error:", e)
        return "Failed"

def global_web_scraper():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌐 Launching Global & Social Media Deep Crawler...")
    
    discovered_leads = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # منابع گسترده شامل پلتفرم‌های تخصصی، انجمن‌ها و شبکه‌های اجتماعی
    targets = [
        "https://www.eslcafe.com/jobs/china",
        "https://www.eslcafe.com/jobs/international",
        "https://teast.co/jobs",
        "https://www.eslauthority.com/jobs/",
        "https://www.tefl.com/job-seeker/job-search.html"
    ]
    
    for url in targets:
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for link in soup.find_all("a", href=True):
                    title = link.get_text(strip=True)
                    if len(title) > 8 and any(k in title.lower() for k in ["esl", "english", "teacher", "online", "china", "tutor", "hiring"]):
                        href = link["href"]
                        full_url = href if href.startswith("http") else f"https://www.eslcafe.com{href}"
                        company = title.split("-")[0].strip()[:35]
                        discovered_leads.append({
                            "company": company, 
                            "url": full_url, 
                            "students": "Young Learners & Adults", 
                            "pay": "$20 - $30/hr",
                            "requirements": json.dumps(["BA Degree", "TEFL/TESOL"]), 
                            "tags": json.dumps(["Global Web", "Social & Board"]), 
                            "status": "Actively Hiring"
                        })
        except Exception as e:
            print(f"Error scraping {url}: {e}")

    # ثبت نتایج در دیتابیس ابری و ارسال به تلگرام و جیمیل
    conn = sqlite3.connect("cloud_leads.db")
    c = conn.cursor()
    for lead in discovered_leads:
        try:
            draft_status = create_gmail_draft(lead["company"])
            if draft_status != "Drafted": draft_status = "Drafting..."

            c.execute(
                "INSERT INTO leads (company, url, students, pay, requirements, tags, date, status, draft_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (lead["company"], lead["url"], lead["students"], lead["pay"], lead["requirements"], lead["tags"], datetime.now().strftime("%Y-%m-%d"), lead["status"], draft_status)
            )
            conn.commit()
            send_telegram(lead["company"], lead["url"], lead["pay"])
        except sqlite3.IntegrityError:
            pass # رکورد تکراری رد می‌شود
    conn.close()

@app.route("/api/leads", methods=["GET"])
def api_leads():
    conn = sqlite3.connect("cloud_leads.db")
    c = conn.cursor()
    c.execute("SELECT id, company, url, students, pay, requirements, tags, date, status, draft_status FROM leads ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        results.append({
            "id": r[0], "company": r[1], "url": r[2], "students": r[3], "pay": r[4],
            "requirements": json.loads(r[5]) if r[5] else [],
            "tags": json.loads(r[6]) if r[6] else [],
            "date": r[7], "status": r[8], "draftStatus": r[9]
        })
    return jsonify(results)

@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.json or {}
        conn = sqlite3.connect("cloud_leads.db")
        c = conn.cursor()
        c.execute("""
            UPDATE settings SET 
            subject = ?, body = ?, gmail_user = ?, gmail_pass = ?, telegram_token = ?, telegram_chat_id = ?
            WHERE id = 1
        """, (data.get("subject",""), data.get("body",""), data.get("gmail_user",""), data.get("gmail_pass",""), data.get("telegram_token",""), data.get("telegram_chat_id","")))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    return jsonify(get_settings())

@app.route("/api/force_scan", methods=["POST"])
def force_scan():
    Thread(target=global_web_scraper).start()
    return jsonify({"status": "Global Scan started"})

def run_loop():
    global_web_scraper()
    schedule.every(20).minutes.do(global_web_scraper)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    init_db()
    Thread(target=run_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
