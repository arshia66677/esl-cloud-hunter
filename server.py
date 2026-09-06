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

app = Flask(__name__)
CORS(app)

@app.route("/", methods=["GET"])
def home():
    return "ESL Hunter Pro Cloud Engine is Active 24/7!", 200

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

def send_telegram(company, url, pay, email_found):
    settings = get_settings()
    token = settings.get("telegram_token", "").strip()
    chat_id = settings.get("telegram_chat_id", "").strip()
    if not token or not chat_id: return

    text = f"🌟 آگهی جدید استخدام مدرس ESL 🌟\n\n🏢 شرکت: {company}\n💰 حقوق: {pay}\n📧 ایمیل: {email_found}\n🔗 لینک: {url}"
    try:
        for cid in chat_id.split(','):
            if cid.strip():
                requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": cid.strip(), "text": text}, timeout=10)
    except Exception as e:
        print("Telegram Send Error:", e, flush=True)

def create_gmail_draft(company, target_email=""):
    settings = get_settings()
    user = settings.get("gmail_user", "").strip()
    password = settings.get("gmail_pass", "").strip()
    subject_template = settings.get("subject", "")
    body_template = settings.get("body", "")

    if not user or not password: return "No Credentials"
    if not target_email or "@" not in target_email or target_email.lower() == user.lower():
        return "No Target Email"
    
    domain_ext = target_email.split(".")[-1]
    if len(domain_ext) < 2 or len(domain_ext) > 7:
        return "Invalid Email Domain"
    
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
        print("Gmail Draft Error:", e, flush=True)
        return "Failed"

def global_web_scraper():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🧠 Gemini AI Search Engine Active...", flush=True)
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment variables!", flush=True)
        return

    prompt = '''
    Search the live web (including job boards, Facebook public pages, and Chinese ESL sites) for recent, valid job postings matching: "Online ESL teacher for China students email apply". 
    CRITICAL INSTRUCTIONS: 
    1. YOU MUST USE THE GOOGLE SEARCH TOOL to find real, currently active websites. 
    2. ONLY extract jobs where a REAL email address is explicitly written in the webpage or search snippet.
    3. DO NOT make up or hallucinate URLs or emails. If you can't find real ones, return an empty array.
    
    Return the result STRICTLY as a JSON object with this format:
    {
      "jobs": [
        {
          "company": "Company Name (Real)",
          "url": "https://exact-real-link.com/job-post",
          "email": "hiring@realcompany.com",
          "salary": "$20-$30/hr or null if not mentioned"
        }
      ]
    }
    '''
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"googleSearch": {}}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

    try:
        print("🚀 Sending request to Google Gemini API...", flush=True)
        res = requests.post(url, json=payload, timeout=60)
        if res.status_code != 200:
            print(f"❌ Gemini API Request Failed. Status: {res.status_code}, Error: {res.text}", flush=True)
            return
        
        data = res.json()
        text_response = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        
        if not text_response:
            print("❌ Empty response from Gemini.", flush=True)
            return
            
        parsed_data = json.loads(text_response)
        jobs = parsed_data.get("jobs", [])
        print(f"✅ AI found {len(jobs)} valid opportunities!", flush=True)

        conn = sqlite3.connect("cloud_leads.db")
        c = conn.cursor()
        new_leads = 0
        for job in jobs:
            if not job.get("email"): continue
            
            try:
                draft_status = create_gmail_draft(job["company"], job["email"])
                c.execute(
                    "INSERT INTO leads (company, url, students, pay, requirements, tags, date, status, draft_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (job["company"], job["url"], "Chinese Students", job.get("salary", "N/A"), '["AI Verified"]', '["ESL"]', datetime.now().strftime("%Y-%m-%d"), "Found", draft_status)
                )
                conn.commit()
                send_telegram(job["company"], job["url"], job.get("salary", "N/A"), job["email"])
                new_leads += 1
            except sqlite3.IntegrityError:
                print(f"⏩ Skipped duplicate lead: {job['url']}", flush=True)
                
        conn.close()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Engine Scan Complete. Saved {new_leads} NEW opportunities to DB.", flush=True)
        
    except Exception as e:
        print("❌ AI Search Error:", e, flush=True)

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
        return jsonify({"status": "success"})
    return jsonify(get_settings())

@app.route("/api/force_scan", methods=["POST"])
def force_scan():
    print("▶️ FORCE SCAN BUTTON CLICKED FROM APP!", flush=True)
    Thread(target=global_web_scraper).start()
    return jsonify({"status": "Global Scan started"})

def run_loop():
    time.sleep(5)
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
