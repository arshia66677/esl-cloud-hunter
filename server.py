import os
import time
import sqlite3
import requests
import imaplib
import json
import random
from email.message import EmailMessage
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from threading import Thread

app = Flask(__name__)
CORS(app)

@app.route("/", methods=["GET"])
def home():
    # UptimeRobot checks this URL every 5 minutes to keep the server awake 24/7
    return "ESL Hunter Pro Cloud Engine is Active 24/7!", 200

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
        print("Database Init Error:", e, flush=True)

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
        print("Get Settings Error:", e, flush=True)
    return {}

def send_telegram(company, url, email_found, pay):
    settings = get_settings()
    token = settings.get("telegram_token", "").strip()
    chat_id = settings.get("telegram_chat_id", "").strip()
    if not token or not chat_id: 
        print("Telegram skipped: No token or chat ID", flush=True)
        return

    text = f"🌟 NEW ESL JOB FOUND!\n\n🏢 Company: {company}\n📧 Email: {email_found}\n💰 Pay: {pay}\n🔗 Link: {url}"
    
    try:
        res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
        print("Telegram Response:", res.status_code, flush=True)
    except Exception as e:
        print("Telegram Send Error:", e, flush=True)

def create_gmail_draft(company, target_email=""):
    settings = get_settings()
    user = settings.get("gmail_user", "").strip()
    password = settings.get("gmail_pass", "").strip()
    subject_template = settings.get("subject", "")
    body_template = settings.get("body", "")

    if not user or not password: 
        print("Draft skipped: No Gmail credentials in settings.", flush=True)
        return "No Credentials"
    
    if not target_email or "@" not in target_email:
        return "Skipped (No Email)"
        
    domain_ext = target_email.split(".")[-1]
    if target_email.lower() == user.lower() or len(domain_ext) > 7 or len(domain_ext) < 2:
        return "Invalid Email format"
    
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(user, password)
        
        msg = EmailMessage()
        clean_company = company[:40].replace("\n", " ").strip()
        msg['Subject'] = subject_template.replace("{company}", clean_company)
        msg['From'] = user
        msg['To'] = target_email
        msg.set_content(body_template.replace("{company}", clean_company))
        
        mail.append('[Gmail]/Drafts', '', imaplib.Time2Internaldate(time.time()), str(msg).encode('utf-8'))
        mail.logout()
        print(f"Draft created successfully for {target_email}", flush=True)
        return "Draft Created"
    except Exception as e:
        print("Gmail Draft Error:", e, flush=True)
        return "Failed"

def global_web_scraper():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🌐 Gemini 1.5 Pro Search Engine Active...", flush=True)
    api_key = os.environ.get("GEMINI_API_KEY")
    discovered_leads = []
    
    if not api_key:
        print("🚨 ERROR: GEMINI_API_KEY is missing in Render Environment Variables!", flush=True)
        return

    queries = [
        "Online ESL teacher for China students email apply",
        "Hiring English teachers China online send CV",
        "TEFL online jobs China email resume",
        "ESL tutor needed China remote apply email"
    ]
    selected_query = random.choice(queries)
    print(f"🔍 Searching Google for: {selected_query}", flush=True)
    
    prompt = f"""
    Search the live web (including job boards, Facebook public pages, and Chinese ESL sites) for recent, valid job postings matching: "{selected_query}". 
    CRITICAL INSTRUCTIONS: 
    1. YOU MUST USE THE GOOGLE SEARCH TOOL to find real, currently active websites. 
    2. ONLY extract jobs where a REAL email address (containing @) is explicitly written in the webpage or search snippet.
    3. DO NOT make up or hallucinate URLs or emails. If you can't find real ones, return an empty array.
    
    Return the result STRICTLY as a JSON object with this format:
    {{
      "jobs": [
        {{
          "company": "Company Name (Real)",
          "url": "https://exact-real-link.com/job-post",
          "email": "hiring@realcompany.com",
          "salary": "$20-$30/hr or null if not mentioned"
        }}
      ]
    }}
    """

    try:
        # FIX: Changed model name to gemini-1.5-pro-latest to fix the 404 Not Found error
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro-latest:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"googleSearch": {}}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        print("🚀 Sending request to Google Gemini API...", flush=True)
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=60)
        
        if res.status_code == 200:
            print("✅ Received 200 OK from Gemini API!", flush=True)
            data = res.json()
            text_response = data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            
            if text_response:
                clean_json = text_response.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:-3].strip()
                elif clean_json.startswith("```"):
                    clean_json = clean_json[3:-3].strip()

                try:
                    parsed_data = json.loads(clean_json)
                    jobs = parsed_data.get('jobs', [])
                    print(f"📊 Gemini found {len(jobs)} potential job entries.", flush=True)
                    
                    for job in jobs:
                        email = job.get('email', '')
                        url_link = job.get('url', '')
                        company = str(job.get('company', 'Unknown School'))[:40]
                        salary = str(job.get('salary', 'Negotiable'))
                        
                        if email and '@' in email and url_link and url_link.startswith('http') and "example.com" not in email:
                            discovered_leads.append({
                                "company": company, 
                                "url": url_link, 
                                "students": "Global AI Search", 
                                "pay": salary, 
                                "requirements": json.dumps(["AI Verified"]), 
                                "tags": json.dumps(["Gemini Engine"]), 
                                "status": "Found", 
                                "email": email.strip()
                            })
                except json.JSONDecodeError as je:
                    print("❌ JSON Parse Error:", je, "Raw Text:", text_response[:200], flush=True)
        else:
            print(f"❌ Gemini API Request Failed. Status: {res.status_code}, Error: {res.text}", flush=True)
    except Exception as e:
        print("❌ AI Search Error:", e, flush=True)

    conn = sqlite3.connect("cloud_leads.db")
    c = conn.cursor()
    
    new_leads_count = 0
    for lead in discovered_leads:
        c.execute("SELECT id FROM leads WHERE url = ?", (lead["url"],))
        if not c.fetchone():
            print(f"🆕 New Job Added: {lead['company']} - {lead['email']}", flush=True)
            draft_status = create_gmail_draft(lead["company"], lead["email"])
            c.execute(
                "INSERT INTO leads (company, url, students, pay, requirements, tags, date, status, draft_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (lead["company"], lead["url"], lead["students"], lead["pay"], lead["requirements"], lead["tags"], datetime.now().strftime("%Y-%m-%d"), lead["status"], draft_status)
            )
            conn.commit()
            send_telegram(lead["company"], lead["url"], lead["email"], lead["pay"])
            new_leads_count += 1
            
    conn.close()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ AI Engine Scan Complete. Saved {new_leads_count} new valid opportunities to DB.\n", flush=True)

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
        
        token = data.get("telegram_token", "").strip()
        chat_id = data.get("telegram_chat_id", "").strip()
        if token and chat_id:
            try:
                requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": "✅ ESL Hunter Pro: System Connected to Gemini 1.5 AI!"}, timeout=5)
            except: pass
            
        return jsonify({"status": "success"})
    return jsonify(get_settings())

@app.route("/api/force_scan", methods=["POST"])
def force_scan():
    print("▶️ FORCE SCAN BUTTON CLICKED FROM APP!", flush=True)
    Thread(target=global_web_scraper).start()
    return jsonify({"status": "Global Scan started"})

def run_loop():
    time.sleep(5) 
    while True:
        try:
            global_web_scraper()
        except Exception as e:
            print("Loop Error:", e, flush=True)
        time.sleep(1200)

if __name__ == "__main__":
    init_db()
    Thread(target=run_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000) if "PORT" in os.environ else 10000)
    app.run(host="0.0.0.0", port=port)
