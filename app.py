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
# जब कोई नया ग्राहक आए, तो बस यहाँ उसका नाम और बॉट का URL जोड़ दो
ALL_CUSTOMERS_BOTS = {
    # तुम्हारा एडमिन डैशबोर्ड, जिसका लाइव डेमो लैंडिंग पेज पर दिखेगा
    "admin": {
        "MDisk Web Server": "https://mdiskwebser.onrender.com",
        "SD Web Bot 234": "https://sdwb234.onrender.com",
    },
    # पहले ग्राहक का डैशबोर्ड
    "rahul": {
        "Rahul's Movie Bot": "https://rahul-bot1.onrender.com",
        "Rahul's Second Bot": "https://rahul-bot2.onrender.com",
    },
    # दूसरे ग्राहक का डैशबोर्ड
    "priya": {
        "Priya's Main Bot": "https://priya-bot.onrender.com",
    }
    # नया ग्राहक जोड़ने के लिए बस यहाँ एक और लाइन जोड़ दो:
    # "customer_name": { "Bot Name": "bot_url" },
}

# --- Status Storage ---
ALL_BOTS_TO_PING = list(set([url for customer_bots in ALL_CUSTOMERS_BOTS.values() for url in customer_bots.values()]))
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
    admin_bots = ALL_CUSTOMERS_BOTS.get("admin", {})
    return render_template('index.html', bots_for_demo=admin_bots)

@app.route('/admin')
def admin_dashboard():
    all_bots = {name: url for customer_bots in ALL_CUSTOMERS_BOTS.values() for name, url in customer_bots.items()}
    return render_template('dashboard.html', bots_for_this_page=all_bots)

@app.route('/<customer_name>')
def customer_dashboard(customer_name):
    customer_bots = ALL_CUSTOMERS_BOTS.get(customer_name)
    if customer_bots is None:
        return "<h2>Customer Not Found!</h2><p>Please check the URL.</p>", 404
    return render_template('dashboard.html', bots_for_this_page=customer_bots)

@app.route('/status')
def get_status():
    return jsonify({'statuses': ping_statuses})

scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
scheduler.add_job(ping_all_services, 'interval', minutes=5)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    ping_all_services()
    serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
