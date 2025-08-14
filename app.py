import os
import requests
from flask import Flask, render_template, jsonify, request
import logging
from datetime import datetime
from waitress import serve
import json
import time
from threading import Lock

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

app = Flask(__name__)
lock = Lock()

# --- यह है तुम्हारी रेसिपी की किताब का पता ---
CUSTOMER_DATA_URL = "https://gist.githubusercontent.com/GrabCoolGadgets/8cf38c60341641a9db73f5ac6018a5f7/raw/customers.json"

# स्टेटस को स्टोर करने के लिए एक फाइल का इस्तेमाल करेंगे
STATUS_FILE = 'ping_statuses.json'

# --- एक सीक्रेट चाबी बनाओ, इसे कोई गेस न कर पाए ---
SECRET_KEY = "CHANGE_THIS_TO_SOMETHING_RANDOM_12345"

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
    try:
        cache_buster_url = f"{CUSTOMER_DATA_URL}?v={int(time.time())}"
        headers = {'Cache-Control': 'no-cache'}
        response = requests.get(cache_buster_url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"CRITICAL: Failed to fetch customer data from Gist: {e}")
        return {}

def run_ping_cycle():
    if not lock.acquire(blocking=False):
        logging.warning("Ping cycle is already running. Skipping this run.")
        return "Ping cycle already in progress."

    try:
        logging.info(f"--- Ping cycle triggered! ---")
        
        all_customers_bots = get_customers_from_gist()
        if not all_customers_bots:
            logging.warning("Customer data is empty. Skipping ping cycle.")
            return "Customer data is empty."

        all_bots_to_ping = list(set([url for bots in all_customers_bots.values() for url in bots.values()]))
        ping_statuses = read_statuses()
        
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
            time.sleep(1) # थोड़ा गैप रखें
        
        write_statuses(ping_statuses)
        logging.info("--- Ping Cycle Finished and statuses saved. ---")
        return "Ping cycle completed."
    finally:
        lock.release()

# --- यह है वह सीक्रेट दरवाजा, जिसे सिर्फ UptimeRobot खटखटाएगा ---
@app.route('/trigger_ping')
def trigger_ping():
    key = request.args.get('key')
    if key == SECRET_KEY:
        return run_ping_cycle()
    else:
        return "Invalid secret key.", 403

@app.route('/')
def landing_page():
    # ... (यह फंक्शन वैसा ही रहेगा) ...

@app.route('/admin')
def admin_dashboard():
    # ... (यह फंक्शन वैसा ही रहेगा) ...

@app.route('/<customer_name>')
def customer_dashboard(customer_name):
    # ... (यह फंक्शन वैसा ही रहेगा) ...

@app.route('/status')
def get_status():
    statuses = read_statuses()
    return jsonify({'statuses': statuses})
    
if __name__ == '__main__':
    serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
