import os
import time
import sqlite3
import schedule
import requests
import imaplib
import json
import re
import xml.etree.ElementTree as ET
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

def send_telegram(company, url, email_found):
    settings = get_settings()
    token = settings.get("telegram_token", "").strip()
    chat_id = settings.get("telegram_chat_id", "").strip()
    if not token or not chat_id: return

    email_display = email_found if email_found else "No email found (Check link)"
    text = f"🎯 NEW JOB FOUND!\n\n🏢 Source: {company}\n📧 Email: {email_display}\n🔗 Link: {url}"
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
    if not target_email or "@" not in target_email: return "No Email"
    
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
        return "Draft Created"
    except Exception as e:
        print("Gmail Draft Error:", e, flush=True)
        return "Failed"

def global_web_scraper():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌐 Scraper Active - Pulling all postings...", flush=True)
    discovered_leads = []
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    email_regex = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"

    # 1. Scrape Reddit Communities
    reddit_sources = [
        "https://www.reddit.com/r/TEFL/search.json?q=hiring&restrict_sr=1&sort=new",
        "https://www.reddit.com/r/OnlineESLTeaching/search.json?q=hiring&restrict_sr=1&sort=new"
    ]
    for url in reddit_sources:
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                for child in res.json().get("data", {}).get("children", []):
                    post = child.get("data", {})
                    title = post.get("title", "")
                    text = post.get("selftext", "")
                    link = "https://www.reddit.com" + post.get("permalink", "")
                    
                    email = ""
                    match = re.search(email_regex, title + " " + text)
                    if match:
                        domain = match.group(0).split(".")[-1].lower()
                        if 2 <= len(domain) <= 4 and domain not in ['png', 'jpg', 'gif']:
                            email = match.group(0)
                            
                    discovered_leads.append({"company": title[:50], "url": link, "email": email})
        except Exception as e:
            print(f"Reddit Scrape Error: {e}", flush=True)

    # 2. Scrape Google News RSS
    rss_urls = [
        "https://news.google.com/rss/search?q=%22ESL+teacher%22+hiring&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=online+english+teacher+jobs&hl=en-US&gl=US&ceid=US:en"
    ]
    for rss_url in rss_urls:
        try:
            res = requests.get(rss_url, headers=headers, timeout=15)
            if res.status_code == 200:
                root = ET.fromstring(res.text)
                for item in root.findall('.//item'):
                    title = item.find('title').text if item.find('title') is not None else "Job Posting"
                    link = item.find('link').text if item.find('link') is not None else ""
                    desc = item.find('description').text if item.find('description') is not None else ""
                    
                    email = ""
                    match = re.search(email_regex, title + " " + desc)
                    if match:
                        domain = match.group(0).split(".")[-1].lower()
                        if 2 <= len(domain) <= 4 and domain not in ['png', 'jpg', 'gif']:
                            email = match.group(0)
                            
                    discovered_leads.append({"company": title[:50], "url": link, "email": email})
        except Exception as e:
            print(f"Google RSS Error: {e}", flush=True)

    # Database Saving - SAVES & SENDS EVERYTHING TO TELEGRAM
    conn = sqlite3.connect("cloud_leads.db")
    c = conn.cursor()
    new_leads = 0
    
    for lead in discovered_leads:
        if not lead["url"]: continue
        c.execute("SELECT id FROM leads WHERE url = ?", (lead["url"],))
        if not c.fetchone():
            draft_status = "Link Only (No Email)"
            
            if lead["email"]:
                draft_status = create_gmail_draft(lead["company"], lead["email"])
            
            # SEND EVERYTHING TO TELEGRAM (Whether email exists or not)
            send_telegram(lead["company"], lead["url"], lead["email"])
            
            c.execute(
                "INSERT INTO leads (company, url, students, pay, requirements, tags, date, status, draft_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (lead["company"], lead["url"], "ESL", "Check Link", '["Found"]', '["Scraped"]', datetime.now().strftime("%Y-%m-%d"), "Found", draft_status)
            )
            conn.commit()
            new_leads += 1
                
    conn.close()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Scrape Complete. Pushed {new_leads} leads to Dashboard & Telegram.", flush=True)

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
    print("▶️ FORCE SCAN CLICKED!", flush=True)
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
