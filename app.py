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
# मैंने तुम्हारा Gist का URL यहाँ डाल दिया है
CUSTOMER_DATA_URL = "https://gist.githubusercontent.com/GrabCoolGadgets/8cf38c60341641a9db73f5ac6018a5f7/raw/customers.json"

# --- यह अब खाली शुरू होंगे और Gist से भरे जाएंगे ---
ALL_CUSTOMERS_BOTS = {}
ALL_BOTS_TO_PING = []
ping_statuses = {}

def update_customer_data():
    global ALL_CUSTOMERS_BOTS, ALL_BOTS_TO_PING, ping_statuses
    try:
        logging.info("Fetching latest customer data from Gist...")
        # GitHub Gist को हमेशा नई जानकारी के लिए चेक करें
        headers = {'Cache-Control': 'no-cache'}
        response = requests.get(CUSTOMER_DATA_URL, headers=headers, timeout=15)
        response.raise_for_status()
        new_customer_data = response.json()
        
        if new_customer_data != ALL_CUSTOMERS_BOTS:
            ALL_CUSTOMERS_BOTS = new_customer_data
            ALL_BOTS_TO_PING = list(set([url for bots in ALL_CUSTOMERS_BOTS.values() for url in bots.values()]))
            
            # नए बॉट्स के लिए स्टेटस डिक्शनरी में जगह बनाओ
            for url in ALL_BOTS_TO_PING:
                if url not in ping_statuses:
                    ping_statuses[url] = {'status': 'waiting'}
            logging.info("Customer data updated successfully!")
        else:
            logging.info("No changes in customer data.")

    except Exception as e:
        logging.error(f"Failed to update customer data: {e}")

def ping_all_services():
    # पिंग करने से ठीक पहले, हमेशा नई ग्राहक लिस्ट चेक करो
    update_customer_data()
    
    if not lock.acquire(blocking=False):
        logging.warning("Ping cycle is already running. Skipping this run.")
        return
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
    # लैंडिंग पेज Gist से एडमिन बॉट्स की लिस्ट दिखाएगा
    admin_bots = ALL_CUSTOMERS_BOTS.get("admin", {})
    return render_template('index.html', bots_for_demo=admin_bots)

@app.route('/admin')
def admin_dashboard():
    # एडमिन डैशबोर्ड Gist से सारे बॉट्स की लिस्ट दिखाएगा
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

# --- बैकग्राउंड शेड्यूलर ---
scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
scheduler.add_job(ping_all_services, 'interval', minutes=5)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    # सर्वर शुरू होते ही पहली बार ग्राहक का डेटा लोड करें
    update_customer_data()
    # फिर पहली बार पिंग करें
    ping_all_services()
    serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
