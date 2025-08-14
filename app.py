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
# यहाँ पर तुम अपनी पब्लिक रिपो का "Raw" URL डालोगे
# मैंने अभी के लिए एक उदाहरण डाल दिया है, तुम इसे बदल देना
CUSTOMER_DATA_URL = "https://raw.githubusercontent.com/GrabCoolGadgets/Ping-Customer/main/customers.json"

# --- यह अब खाली शुरू होंगे और URL से भरे जाएंगे ---
ALL_CUSTOMERS_BOTS = {}
ping_statuses = {}

def update_customer_data():
    global ALL_CUSTOMERS_BOTS, ping_statuses
    try:
        logging.info("Fetching latest customer data from Raw URL...")
        
        # "कैश बस्टिंग" ताकि हमेशा ताज़ा डेटा मिले
        cache_buster_url = f"{CUSTOMER_DATA_URL}?v={int(time.time())}"
        
        headers = {'Cache-Control': 'no-cache'}
        response = requests.get(cache_buster_url, headers=headers, timeout=15)
        response.raise_for_status()
        new_customer_data = response.json()
        
        if new_customer_data != ALL_CUSTOMERS_BOTS:
            ALL_CUSTOMERS_BOTS = new_customer_data
            all_bots = list(set([url for bots in ALL_CUSTOMERS_BOTS.values() for url in bots.values()]))
            
            for url in all_bots:
                if url not in ping_statuses:
                    ping_statuses[url] = {'status': 'waiting'}
            logging.info("Customer data updated successfully!")
        else:
            logging.info("No changes in customer data.")

    except Exception as e:
        logging.error(f"Failed to update customer data: {e}")

def ping_all_services():
    update_customer_data()
    
    if not lock.acquire(blocking=False): return
    try:
        all_bots_to_ping = list(set([url for bots in ALL_CUSTOMERS_BOTS.values() for url in bots.values()]))
        logging.info(f"--- Ping cycle started for {len(all_bots_to_ping)} total bots... ---")

        pinger_dashboard_url = os.environ.get('RENDER_EXTERNAL_URL')
        if pinger_dashboard_url and pinger_dashboard_url not in all_bots_to_ping:
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
    update_customer_data()
    serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
