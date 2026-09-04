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
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app)

def init_db():
    try:
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
    except Exception as e:
        print("Database Init Error:", e)

def get_settings():
    try:
        conn = sqlite3.connect("cloud_leads.db")
        c = conn.cursor()
        c.execute("SELECT subject, body, gmail_user, gmail_pass, telegram_token, telegram_chat_id FROM settings WHERE id = 1")
        row = c.fetchone()
        conn.close()
        if row:
            return {"subject": row[0], "body": row[1], "gmail_user": row[2], "gmail_pass": row[3], "telegram_token": row[4], "telegram_chat_id": row[5]}
    except Exception as e:
        print("Get Settings Error:", e)
    return {}

def send_telegram(title, url, email_found):
    settings = get_settings()
    token = settings.get("telegram_token", "").strip()
    chat_id = settings.get("telegram_chat_id", "").strip()
    if not token or not chat_id: 
        return

    # اگر ایمیل پیدا شود اطلاع می‌دهد که درفت ساخته شده، اگر نه می‌گوید فقط لینک است
    email_status = f"✅ {email_found} (Draft Created)" if email_found else "❌ No email found (Click link to apply)"
    
    text = f"🎯 NEW OPPORTUNITY FOUND!\n\n🏢 Source/Title: {title}\n📧 Email: {email_status}\n🔗 Link: {url}"
    
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        print("Telegram Send Error:", e)

def create_gmail_draft(company, target_email=""):
    settings = get_settings()
    user = settings.get("gmail_user", "").strip()
    password = settings.get("gmail_pass", "").strip()
    subject_template = settings.get("subject", "")
    body_template = settings.get("body", "")

    if not user or not password: return "No Credentials"
    
    # قانون سخت‌گیرانه: فقط اگر ایمیل معتبر پیدا شد درفت بساز
    if not target_email or "@" not in target_email:
        return "Skipped (No Email)"
        
    # جلوگیری از ارسال به ایمیل خودمان یا دامنه‌های اشتباه مثل .composition
    domain_ext = target_email.split(".")[-1]
    if target_email.lower() == user.lower() or len(domain_ext) > 7:
        return "Invalid Email format"
    
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(user, password)
        
        msg = EmailMessage()
        clean_company = company[:30].replace("\n", " ").strip()
        msg['Subject'] = subject_template.replace("{company}", clean_company)
        msg['From'] = user
        msg['To'] = target_email
        msg.set_content(body_template.replace("{company}", clean_company))
        
        mail.append('[Gmail]/Drafts', '', imaplib.Time2Internaldate(time.time()), str(msg).encode('utf-8'))
        mail.logout()
        return "Draft Created"
    except Exception as e:
        print("Gmail Draft Error:", e)
        return "Failed"

def global_web_scraper():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌐 Legal Global Engine Active...")
    discovered_leads = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    email_regex = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    
    # 1. جستجوی قانونی از طریق Google News RSS (دور زدن تحریم‌های آی‌پی سرور)
    google_queries = ['"English teacher" China hiring', 'teach English in China recruiter']
    for q in google_queries:
        try:
            url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for item in soup.find_all("item"):
                    title = item.title.text if item.title else "Google Result"
                    link = item.link.text if item.link else ""
                    desc = item.description.text if item.description else ""
                    
                    # جستجوی ایمیل در متن یا عنوان
                    full_text = title + " " + desc
                    match = re.search(email_regex, full_text)
                    email = match.group(0) if match else ""
                    
                    discovered_leads.append({
                        "company": title[:40], "url": link, "students": "Google Search", 
                        "pay": "Negotiable", "requirements": json.dumps(["Global Web"]), 
                        "tags": json.dumps(["Google RSS"]), "status": "Found", "email": email
                    })
        except Exception as e:
            print("Google RSS Error:", e)

    # 2. اتصال به API باز و قانونی Reddit (دسترسی به بزرگترین انجمن‌های مدرسین زبان)
    reddit_sources = [
        "https://www.reddit.com/r/TEFL/search.json?q=hiring+china&restrict_sr=1&sort=new",
        "https://www.reddit.com/r/ChinaJobs/new.json?limit=5"
    ]
    for url in reddit_sources:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                children = data.get("data", {}).get("children", [])
                for child in children:
                    post = child.get("data", {})
                    title = post.get("title", "")
                    selftext = post.get("selftext", "")
                    link = "https://www.reddit.com" + post.get("permalink", "")
                    
                    match = re.search(email_regex, selftext + " " + title)
                    email = match.group(0) if match else ""
                    
                    discovered_leads.append({
                        "company": title[:40], "url": link, "students": "Community", 
                        "pay": "Negotiable", "requirements": json.dumps(["Reddit"]), 
                        "tags": json.dumps(["Social Media"]), "status": "Found", "email": email
                    })
        except Exception as e:
            print("Reddit API Error:", e)

    conn = sqlite3.connect("cloud_leads.db")
    c = conn.cursor()
    
    new_leads_count = 0
    for lead in discovered_leads:
        # بررسی تکراری نبودن در دیتابیس
        c.execute("SELECT id FROM leads WHERE url = ?", (lead["url"],))
        if not c.fetchone():
            # ساخت پیش‌نویس (فقط اگر ایمیل وجود داشته باشد)
            draft_status = create_gmail_draft(lead["company"], lead["email"])
            
            # ذخیره در دیتابیس (همه موارد ذخیره می‌شوند تا دوباره ارسال نشوند)
            c.execute(
                "INSERT INTO leads (company, url, students, pay, requirements, tags, date, status, draft_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (lead["company"], lead["url"], lead["students"], lead["pay"], lead["requirements"], lead["tags"], datetime.now().strftime("%Y-%m-%d"), lead["status"], draft_status)
            )
            conn.commit()
            
            # ارسال همه‌چیز به تلگرام
            send_telegram(lead["company"], lead["url"], lead["email"])
            new_leads_count += 1
            
    conn.close()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Engine Scan Complete. Found {new_leads_count} new opportunities.")

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
        
        # ارسال پیام تست آنی به تلگرام
        token = data.get("telegram_token", "").strip()
        chat_id = data.get("telegram_chat_id", "").strip()
        if token and chat_id:
            try:
                requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": "✅ ESL Hunter Pro: System Connected to Legal Engine!"}, timeout=5)
            except: pass
            
        return jsonify({"status": "success"})
    return jsonify(get_settings())

@app.route("/api/force_scan", methods=["POST"])
def force_scan():
    Thread(target=global_web_scraper).start()
    return jsonify({"status": "Global Scan started"})

def run_loop():
    time.sleep(5) # صبر برای اطمینان از بوت شدن سرور
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
