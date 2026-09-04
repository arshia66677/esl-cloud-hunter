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
from flask import Flask, jsonify, request, render_template_string
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
        return {
            "subject": row[0], "body": row[1], 
            "gmail_user": row[2].strip() if row[2] else "", 
            "gmail_pass": row[3].strip() if row[3] else "", 
            "telegram_token": row[4].strip() if row[4] else "", 
            "telegram_chat_id": row[5].strip() if row[5] else ""
        }
    return {}

def send_telegram(company, url, pay, is_test=False):
    settings = get_settings()
    token = settings.get("telegram_token", "")
    chat_id = settings.get("telegram_chat_id", "")
    if not token or not chat_id: 
        print("Telegram Warning: Token or Chat ID is missing.")
        return False

    if is_test:
        text = "✅ *ESL Hunter Pro: System Connected!*\nYour Telegram is successfully linked to the Cloud Engine."
    else:
        text = f"🎯 *New Global ESL Opportunity!*\n\n🏢 *Company:* {company}\n💰 *Pay:* {pay}\n🔗 *Link:* {url}"
    
    try:
        res = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage", 
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, 
            timeout=10
        )
        # Fallback to plain text if Markdown fails due to weird characters in company name
        if res.status_code != 200:
            plain_text = f"New ESL Opportunity!\nCompany: {company}\nPay: {pay}\nLink: {url}"
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": plain_text}, timeout=10)
        return True
    except Exception as e:
        print("Telegram Send Error:", e)
        return False

def create_gmail_draft(company, target_email=""):
    settings = get_settings()
    user = settings.get("gmail_user", "")
    password = settings.get("gmail_pass", "")
    subject_template = settings.get("subject", "")
    body_template = settings.get("body", "")

    if not user or not password: 
        return "No Credentials"
    
    # 🚨 STRICT RULE: If email is empty, doesn't have @, doesn't have a dot, or is YOUR email -> DO NOT MAKE DRAFT
    if not target_email:
        return "Skipped (No Email Found)"
    
    target_email = target_email.strip()
    
    if "@" not in target_email or "." not in target_email.split("@")[-1]:
        return "Skipped (Invalid Email)"
        
    if target_email.lower() == user.lower():
        return "Skipped (Own Email)"
    
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
        return "Drafted Successfully"
    except Exception as e:
        print("Gmail Draft Error:", e)
        return "Gmail Login Error"

def global_web_scraper():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌐 Global Web & Social Crawler Active...")
    discovered_leads = []
    
    # We use a broad search strategy simulating global searches to hit FB, ESL Boards, and independent sites.
    search_queries = [
        "site:facebook.com 'English teacher' China hiring email @",
        "'ESL teacher' China hiring 'send email to' @",
        "site:eslcafe.com 'China' hiring email"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # regex for strict email finding
    email_regex = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    
    for query in search_queries:
        try:
            # Using a lightweight, scraper-friendly search endpoint (DuckDuckGo HTML) to find global links
            url = f"https://html.duckduckgo.com/html/?q={query}"
            res = requests.get(url, headers=headers, timeout=15)
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                results = soup.find_all("a", class_="result__url")
                snippets = soup.find_all("a", class_="result__snippet")
                
                for i in range(min(len(results), len(snippets))):
                    link = results[i].get("href", "")
                    if link.startswith("//"): link = "https:" + link
                    
                    text_snippet = snippets[i].get_text(strip=True)
                    title = "ESL Opportunity"
                    if "facebook" in link: title = "Facebook Group Post"
                    
                    # Extract email from the text snippet of the global web page
                    match = re.search(email_regex, text_snippet)
                    extracted_email = match.group(0) if match else ""
                    
                    if extracted_email:
                        company_name = extracted_email.split("@")[1].split(".")[0].capitalize() + " School"
                        discovered_leads.append({
                            "company": company_name, 
                            "url": link, 
                            "students": "Various", 
                            "pay": "Negotiable", 
                            "requirements": json.dumps(["Native/Fluent"]), 
                            "tags": json.dumps(["Global Web", "Verified Email"]), 
                            "status": "Actively Hiring",
                            "email": extracted_email
                        })
            time.sleep(2) # Respectful delay between global searches
        except Exception as e:
            print(f"Global Web Search Error: {e}")

    # Fallback to direct targeted sites (teast, etc) for maximum coverage
    direct_targets = ["https://teast.co/jobs"]
    for url in direct_targets:
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for link in soup.find_all("a", href=True):
                    title = link.get_text(strip=True)
                    if any(k in title.lower() for k in ["esl", "english", "teacher"]):
                        href = link["href"]
                        full_url = href if href.startswith("http") else f"https://teast.co{href}"
                        
                        match = re.search(email_regex, title)
                        extracted_email = match.group(0) if match else ""
                        
                        if extracted_email:
                            discovered_leads.append({
                                "company": title.split("-")[0].strip()[:35], "url": full_url, 
                                "students": "Various", "pay": "$20-$30/hr", 
                                "requirements": json.dumps(["BA Degree"]), "tags": json.dumps(["Job Board"]), 
                                "status": "Actively Hiring", "email": extracted_email
                            })
        except Exception as e:
            pass

    # Save to Database and Trigger Automation
    conn = sqlite3.connect("cloud_leads.db")
    c = conn.cursor()
    new_found = 0
    
    for lead in discovered_leads:
        try:
            # 🚨 STRICT RULE: Draft only happens if email exists and is valid
            draft_status = create_gmail_draft(lead["company"], lead.get("email", ""))
            
            c.execute(
                "INSERT INTO leads (company, url, students, pay, requirements, tags, date, status, draft_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (lead["company"], lead["url"], lead["students"], lead["pay"], lead["requirements"], lead["tags"], datetime.now().strftime("%Y-%m-%d"), lead["status"], draft_status)
            )
            conn.commit()
            new_found += 1
            
            # Send to Telegram only if successfully added to DB
            send_telegram(lead["company"], lead["url"], lead["pay"])
        except sqlite3.IntegrityError:
            pass # URL already exists in DB
    conn.close()
    print(f"✅ Global Scan Complete. Found {new_found} new verified leads.")

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
        
        # INSTANT TELEGRAM TEST WHEN SAVING SETTINGS
        Thread(target=send_telegram, args=("TEST", "TEST", "TEST", True)).start()
        
        return jsonify({"status": "success"})
    return jsonify(get_settings())

@app.route("/api/force_scan", methods=["POST"])
def force_scan():
    Thread(target=global_web_scraper).start()
    return jsonify({"status": "Global Scan started. Check Telegram in 1 minute."})

def run_loop():
    # Run once immediately on boot
    global_web_scraper()
    # Then run every 20 minutes automatically (24/7 without PC on)
    schedule.every(20).minutes.do(global_web_scraper)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    init_db()
    Thread(target=run_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000) if "PORT" in os.environ else 10000)
    app.run(host="0.0.0.0", port=port)
