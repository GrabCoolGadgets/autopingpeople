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
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

app = Flask(__name__)
lock = Lock()

# --- यह है तुम्हारी रेसिपी की किताब का पता ---
CUSTOMER_DATA_URL = "https://raw.githubusercontent.com/GrabCoolGadgets/Ping-Customer/main/customers.json"
    
# स्टेटस को स्टोर करने के लिए एक फाइल का इस्तेमाल करेंगे
STATUS_FILE = 'ping_statuses.json'

def read_statuses():
    try:
        with open(STATUS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def write_statuses(statuses):
    with open(STATUS_FILE, 'w') as f:
        json.dump(statuses, f)

def get_customers_from_gist():
    """यह फंक्शन हमेशा Gist से ताज़ा डेटा लाएगा। यह सबसे ज़रूरी फंक्शन है।"""
    try:
        # "कैश बस्टिंग" ताकि हमेशा ताज़ा डेटा मिले
        cache_buster_url = f"{CUSTOMER_DATA_URL}?v={int(time.time())}"
        headers = {'Cache-Control': 'no-cache'}
        response = requests.get(cache_buster_url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"CRITICAL: Failed to fetch customer data from GitHub: {e}")
        return {} # अगर Gist न मिले, तो खाली डेटा भेजो

def ping_all_services():
    all_customers_bots = get_customers_from_gist()
    if not all_customers_bots:
        logging.warning("Customer data is empty. Skipping ping cycle.")
        return

    all_bots_to_ping = list(set([url for bots in all_customers_bots.values() for url in bots.values()]))
    ping_statuses = read_statuses()
    
    if not lock.acquire(blocking=False): return
    try:
        logging.info(f"--- Ping cycle started for {len(all_bots_to_ping)} total bots... ---")
        pinger_dashboard_url = os.environ.get('RENDER_EXTERNAL_URL')
        if pinger_dashboard_url:
            all_bots_to_ping.append(pinger_dashboard_url)

        for url in all_bots_to_ping:
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
            time.sleep(1)
        
        write_statuses(ping_statuses)
        logging.info("--- Ping Cycle Finished and statuses saved. ---")
    finally:
        lock.release()

@app.route('/')
def landing_page():
    # --- यह है सबसे बड़ा और सही बदलाव ---
    # अब यह फंक्शन भी Gist से हमेशा ताज़ा डेटा पढ़ेगा
    all_customers_bots = get_customers_from_gist()
    admin_bots = all_customers_bots.get("admin", {})
    return render_template('index.html', bots_for_demo=admin_bots)

@app.route('/admin')
def admin_dashboard():
    all_customers_bots = get_customers_from_gist()
    all_bots = {name: url for customer_bots in all_customers_bots.values() for name, url in customer_bots.items()}
    return render_template('dashboard.html', bots_for_this_page=all_bots)

@app.route('/<customer_name>')
def customer_dashboard(customer_name):
    all_customers_bots = get_customers_from_gist()
    customer_bots = all_customers_bots.get(customer_name)
    if customer_bots is None:
        return "<h2>Customer Not Found!</h2><p>Please check the URL or wait a few minutes if you were just added.</p>", 404
    return render_template('dashboard.html', bots_for_this_page=customer_bots)

@app.route('/status')
def get_status():
    statuses = read_statuses()
    return jsonify({'statuses': statuses})
    
scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
scheduler.add_job(ping_all_services, 'interval', minutes=5)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
