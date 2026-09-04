import os
import time
import sqlite3
import schedule
import requests
import imaplib
import json
import re
from email.message import EmailMessage
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from threading import Thread

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

def send_telegram(email_found, source_query):
    settings = get_settings()
    token = settings.get("telegram_token", "").strip()
    chat_id = settings.get("telegram_chat_id", "").strip()
    if not token or not chat_id: return

    text = f"🌍 GLOBAL WEB LEAD FOUND!\n\n📧 Target Email: {email_found}\n🔍 Source: Found via Search Engine\n🔗 Search Query: {source_query}\n\n✅ Draft created in your Gmail!"
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        print("Telegram Send Error:", e)

def create_gmail_draft(target_email):
    settings = get_settings()
    user = settings.get("gmail_user", "").strip()
    password = settings.get("gmail_pass", "").strip()
    subject_template = settings.get("subject", "")
    body_template = settings.get("body", "")

    if not user or not password: return "No Credentials"
    if not target_email or "@" not in target_email: return "Invalid Email"
    if target_email.lower() == user.lower(): return "Same as user email"
    
    # فیلتر کردن دامنه‌های اشتباه (مثل .composition)
    domain_part = target_email.split(".")[-1]
    if len(domain_part) > 7: return "Invalid Domain"

    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(user, password)
        
        msg = EmailMessage()
        company_placeholder = target_email.split("@")[0].capitalize()
        msg['Subject'] = subject_template.replace("{company}", company_placeholder)
        msg['From'] = user
        msg['To'] = target_email
        msg.set_content(body_template.replace("{company}", company_placeholder))
        
        mail.append('[Gmail]/Drafts', '', imaplib.Time2Internaldate(time.time()), str(msg).encode('utf-8'))
        mail.logout()
        return "Drafted"
    except Exception as e:
        print("Gmail Draft Error:", e)
        return "Failed"

def global_web_scraper():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌐 THE WHOLE INTERNET SEARCH ENGINE STARTED...")
    settings = get_settings()
    user_email = settings.get("gmail_user", "").lower().strip()
    
    # این عبارات کل فیسبوک، لینکدین و اینترنت را می‌گردند
    search_queries = [
        'site:facebook.com "English teacher" China hiring "@"',
        '"ESL teacher" China hiring "send your CV" "@"',
        'site:linkedin.com "English teacher" hiring "@"',
        '"online English tutor" hiring "contact" "@"',
        '"teach English in China" recruiter email "@"'
    ]
    
    email_regex = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,7}"
    discovered_leads = []
    unique_emails = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    }

    # استفاده از موتور جستجوی سبک برای جلوگیری از بلاک شدن توسط فایروال‌ها
    for query in search_queries:
        try:
            url = "https://lite.duckduckgo.com/lite/"
            payload = {'q': query}
            res = requests.post(url, data=payload, headers=headers, timeout=15)
            
            if res.status_code == 200:
                # استخراج هجومی تمام ایمیل‌های موجود در صفحه نتایج کل وب
                found_emails = re.findall(email_regex, res.text)
                for email in found_emails:
                    email = email.lower()
                    # فیلتر کردن ایمیل‌های نامعتبر، تکراری یا ایمیل خود شما
                    if email not in unique_emails and email != user_email and "example" not in email and "yourdomain" not in email:
                        unique_emails.add(email)
                        discovered_leads.append({
                            "company": "Global Web Lead",
                            "url": f"Query: {query}",
                            "students": "Global Search",
                            "pay": "Negotiable",
                            "requirements": json.dumps(["Global Match"]),
                            "tags": json.dumps(["Web/Facebook"]),
                            "status": "Found",
                            "email": email
                        })
        except Exception as e:
            print(f"Search Engine Error: {e}")
            
    # ذخیره در دیتابیس و ارسال به تلگرام/جیمیل
    conn = sqlite3.connect("cloud_leads.db")
    c = conn.cursor()
    for lead in discovered_leads:
        # ساخت یک URL یکتا برای دیتابیس تا خطا ندهد
        unique_db_url = lead["email"] 
        
        # بررسی اینکه آیا این ایمیل قبلاً در دیتابیس ثبت شده یا نه
        c.execute("SELECT id FROM leads WHERE url = ?", (unique_db_url,))
        if not c.fetchone():
            draft_status = create_gmail_draft(lead["email"])
            
            # فقط اگر پیش‌نویس موفق بود یا ایمیل معتبر بود در لیست می‌آید
            if draft_status == "Drafted":
                c.execute(
                    "INSERT INTO leads (company, url, students, pay, requirements, tags, date, status, draft_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (lead["company"], unique_db_url, lead["students"], lead["pay"], lead["requirements"], lead["tags"], datetime.now().strftime("%Y-%m-%d"), lead["status"], draft_status)
                )
                conn.commit()
                send_telegram(lead["email"], lead["url"])
    conn.close()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ GLOBAL SEARCH COMPLETE.")

@app.route("/api/leads", methods=["GET"])
def api_leads():
    conn = sqlite3.connect("cloud_leads.db")
    c = conn.cursor()
    c.execute("SELECT id, company, url, students, pay, requirements, tags, date, status, draft_status FROM leads ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        "id": r[0], "company": r[1], "url": r[2], "students": r[3], "pay": r[4],
        "requirements": json.loads(r[5]) if r[5] else [], "tags": json.loads(r[6]) if r[6] else [],
        "date": r[7], "status": r[8], "draftStatus": r[9]
    } for r in rows])

@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.json or {}
        conn = sqlite3.connect("cloud_leads.db")
        c = conn.cursor()
        c.execute("""
            UPDATE settings SET subject = ?, body = ?, gmail_user = ?, gmail_pass = ?, telegram_token = ?, telegram_chat_id = ? WHERE id = 1
        """, (data.get("subject",""), data.get("body",""), data.get("gmail_user",""), data.get("gmail_pass",""), data.get("telegram_token",""), data.get("telegram_chat_id","")))
        conn.commit()
        conn.close()
        
        # Test Telegram
        token = data.get("telegram_token", "").strip()
        chat_id = data.get("telegram_chat_id", "").strip()
        if token and chat_id:
            try:
                requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": "✅ ESL Hunter Pro: System Connected to Global Search!"}, timeout=5)
            except: pass
            
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
    port = int(os.environ.get("PORT", 10000) if "PORT" in os.environ else 10000)
    app.run(host="0.0.0.0", port=port)
