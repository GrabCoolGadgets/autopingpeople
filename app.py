import os
import requests
from flask import Flask, render_template, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from datetime import datetime
import atexit
from waitress import serve
from threading import Lock
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

app = Flask(__name__)
lock = Lock()

# --- यह है तुम्हारा कस्टमर डेटाबेस ---
ALL_CUSTOMERS_BOTS = {
    # तुम्हारा एडमिन डैशबोर्ड, जो सब कुछ दिखाएगा
    "admin": [
        "https://mdiskwebser.onrender.com",
        "https://sdwb234.onrender.com",
        # ... तुम यहाँ अपने पर्सनल बॉट भी डाल सकते हो
    ],
    # पहले ग्राहक का डैशबोर्ड
    "rahul": [
        "https://rahul-bot1.onrender.com",
    ],
    # दूसरे ग्राहक का डैशबोर्ड
    "priya": [
        "https://priya-bot.onrender.com",
    ]
}

# --- Status Storage ---
ALL_BOTS_TO_PING = list(set([url for customer_bots in ALL_CUSTOMERS_BOTS.values() for url in customer_bots]))
ping_statuses = {url: {'status': 'waiting'} for url in ALL_BOTS_TO_PING}

def ping_all_services():
    if not lock.acquire(blocking=False): return
    try:
        logging.info(f"--- Ping cycle started for {len(ALL_BOTS_TO_PING)} total bots... ---")
        pinger_dashboard_url = os.environ.get('RENDER_EXTERNAL_URL')
        urls_to_check = list(ALL_BOTS_TO_PING)
        if pinger_dashboard_url and pinger_dashboard_url not in urls_to_check:
            urls_to_check.append(pinger_dashboard_url)

        for url in urls_to_check:
            timestamp = datetime.utcnow().isoformat() + "Z"
            previous_status = ping_statuses.get(url, {}).get('status', 'waiting')
            try:
                response = requests.get(url, timeout=30)
                if response.ok:
                    new_status = 'live'
                    if previous_status == 'down': new_status = 'recovered'
                    ping_statuses[url] = {'status': new_status, 'code': response.status_code, 'error': None, 'timestamp': timestamp}
                else:
                    ping_statuses[url] = {'status': 'down', 'code': response.status_code, 'error': f"HTTP {response.status_code}", 'timestamp': timestamp}
            except requests.RequestException as e:
                ping_statuses[url] = {'status': 'down', 'code': None, 'error': str(e.__class__.__name__), 'timestamp': timestamp}
            time.sleep(2)
        logging.info("--- Ping Cycle Finished ---")
    finally:
        lock.release()

@app.route('/')
def landing_page():
    # मुख्य URL खोलने पर सुंदर लैंडिंग पेज दिखेगा
    return render_template('index.html')

@app.route('/admin')
def admin_dashboard():
    # /admin खोलने पर एडमिन डैशबोर्ड दिखेगा
    all_bots = [url for customer_bots in ALL_CUSTOMERS_BOTS.values() for url in customer_bots]
    return render_template('dashboard.html', bot_urls_for_this_page=all_bots)

@app.route('/<customer_name>')
def customer_dashboard(customer_name):
    # ग्राहक का नाम URL में डालने पर उसका डैशबोर्ड दिखेगा
    customer_urls = ALL_CUSTOMERS_BOTS.get(customer_name)
    if customer_urls is None:
        return "<h2>Customer Not Found!</h2><p>Please check the URL.</p>", 404
    return render_template('dashboard.html', bot_urls_for_this_page=customer_urls)

@app.route('/status')
def get_status():
    return jsonify({'statuses': ping_statuses})

# --- बैकग्राउंड पिंगर ---
scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
scheduler.add_job(ping_all_services, 'interval', minutes=5)
scheduler.start()

atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    ping_all_services()
    serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
