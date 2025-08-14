import os
import requests
from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from datetime import datetime
import atexit
from waitress import serve
from threading import Lock, Thread
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

app = Flask(__name__)
lock = Lock()

# --- यह है तुम्हारा भरोसेमंद, ऑफलाइन कस्टमर डेटाबेस ---
ALL_CUSTOMERS_BOTS = {
    "admin": {
        "MDisk Web Server": "https://mdiskwebser.onrender.com",
        "SD Web Bot 234": "https://sdwb234.onrender.com",
    },
    "rahul": {
        "Rahul's Movie Bot": "https://rahul-bot1.onrender.com",
    },
    "priya": {
        "Priya's Main Bot": "https://priya-bot.onrender.com",
    }
}

# --- Status Storage ---
ALL_BOTS_TO_PING = list(set([url for customer_bots in ALL_CUSTOMERS_BOTS.values() for url in customer_bots.values()]))
ping_statuses = {url: {'status': 'waiting'} for url in ALL_BOTS_TO_PING}

def ping_all_services():
    if not lock.acquire(blocking=False):
        logging.warning("Ping cycle is already running. Skipping this run.")
        return
    try:
        logging.info(f"--- Ping cycle started for {len(ALL_BOTS_TO_PING)} bots ---")
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

@app.before_request
def before_request_func():
    if request.endpoint in ['admin_dashboard', 'customer_dashboard']:
        logging.info("--- Dashboard refresh triggered. Running immediate ping cycle in background. ---")
        thread = Thread(target=ping_all_services)
        thread.daemon = True
        thread.start()

@app.route('/')
def landing_page():
    return render_template('index.html', bots_for_demo=ALL_CUSTOMERS_BOTS.get("admin", {}))

@app.route('/admin')
def admin_dashboard():
    all_bots = {name: url for customer_bots in ALL_CUSTOMERS_BOTS.values() for name, url in customer_bots.items()}
    return render_template('dashboard.html', bots_for_this_page=all_bots)

@app.route('/<customer_name>')
def customer_dashboard(customer_name):
    customer_bots = ALL_CUSTOMERS_BOTS.get(customer_name)
    if customer_bots is None:
        return "<h2>Customer Not Found!</h2>", 404
    return render_template('dashboard.html', bots_for_this_page=customer_bots)

@app.route('/status')
def get_status():
    return jsonify({'statuses': ping_statuses})

scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
scheduler.add_job(ping_all_services, 'interval', minutes=5)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
