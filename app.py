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
CUSTOMER_DATA_URL = "https://gist.githubusercontent.com/GrabCoolGadgets/e6fb83fa7e519aa7f872198186f2944e/raw/customers.json"
    
# स्टेटस को स्टोर करने के लिए एक फाइल का इस्तेमाल करेंगे
STATUS_FILE = 'ping_statuses.json'

# --- यह अब खाली शुरू होंगे और Gist से भरे जाएंगे ---
ALL_CUSTOMERS_BOTS = {}
ping_statuses = {}

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
        logging.error(f"CRITICAL: Failed to fetch customer data from GitHub: {e}")
        return ALL_CUSTOMERS_BOTS # अगर Gist न मिले, तो पुरानी लिस्ट ही इस्तेमाल करो

def update_customer_data_only():
    """यह फंक्शन सिर्फ Gist से डेटा लाएगा।"""
    global ALL_CUSTOMERS_BOTS
    
    logging.info("--- Checking for Gist updates... ---")
    new_customer_data = get_customers_from_gist()
    
    if new_customer_data and new_customer_data != ALL_CUSTOMERS_BOTS:
        ALL_CUSTOMERS_BOTS = new_customer_data
        logging.info("Customer data updated successfully!")
    else:
        logging.info("No changes in customer data.")

def ping_all_services():
    """यह फंक्शन सिर्फ पिंग करेगा।"""
    if not ALL_CUSTOMERS_BOTS:
        logging.warning("Customer list is empty. Skipping ping cycle.")
        return
        
    all_bots_to_ping = list(set([url for bots in ALL_CUSTOMERS_BOTS.values() for url in bots.values()]))
    
    if not lock.acquire(blocking=False): return
    try:
        logging.info(f"--- Ping cycle started for {len(all_bots_to_ping)} total bots... ---")
        pinger_dashboard_url = os.environ.get('RENDER_EXTERNAL_URL')
        if pinger_dashboard_url and pinger_dashboard_url not in all_bots_to_ping:
            all_bots_to_ping.append(pinger_dashboard_url)

        current_statuses = read_statuses()
        for url in all_bots_to_ping:
            timestamp = datetime.utcnow().isoformat() + "Z"
            previous_status = current_statuses.get(url, {}).get('status', 'waiting')
            try:
                response = requests.get(url, timeout=30)
                if response.ok:
                    new_status = 'live'
                    if previous_status == 'down': new_status = 'recovered'
                    current_statuses[url] = {'status': new_status, 'code': response.status_code, 'error': None, 'timestamp': timestamp}
                else:
                    current_statuses[url] = {'status': 'down', 'code': response.status_code, 'error': f"HTTP {response.status_code}", 'timestamp': timestamp}
            except requests.RequestException as e:
                current_statuses[url] = {'status': 'down', 'code': None, 'error': str(e.__class__.__name__), 'timestamp': timestamp}
            time.sleep(1)
        
        write_statuses(current_statuses)
        logging.info("--- Ping Cycle Finished and statuses saved. ---")
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
    statuses = read_statuses()
    return jsonify({'statuses': statuses})
    
# --- यह है सबसे बड़ा और सही बदलाव ---
scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
# अलार्म #1: पिंगर, जो हर 5 मिनट में चलेगा (सुरक्षित)
scheduler.add_job(ping_all_services, 'interval', minutes=5)
# अलार्म #2: डेटा चेकर, जो हर 10 सेकंड में चलेगा (सुपर फास्ट!)
scheduler.add_job(update_customer_data_only, 'interval', seconds=10)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    # सर्वर शुरू होते ही पहली बार डेटा लोड करो
    update_customer_data_only()
    serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
