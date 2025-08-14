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
# यहाँ पर अपने GitHub Gist का "Raw" URL डालो
CUSTOMER_DATA_URL = "https://gist.githubusercontent.com/GrabCoolGadgets/8cf38c60341641a9db73f5ac6018a5f7/raw/customers.json"

# --- यह अब खाली शुरू होंगे ---
ALL_CUSTOMERS_BOTS = {}
ALL_BOTS_TO_PING = []
ping_statuses = {}

def update_customer_data():
    global ALL_CUSTOMERS_BOTS, ALL_BOTS_TO_PING, ping_statuses
    try:
        logging.info("Fetching latest customer data from Gist...")
        response = requests.get(CUSTOMER_DATA_URL)
        response.raise_for_status()
        new_customer_data = response.json()
        
        # अगर डेटा बदला है, तभी अपडेट करो
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
    
    if not lock.acquire(blocking=False): return
    try:
        # ... (पिंग करने वाला पूरा लॉजिक यहाँ आएगा, बिल्कुल पहले जैसा) ...
        # ... (time.sleep(2) के साथ) ...
    finally:
        lock.release()

# ... (सारे @app.route फंक्शन बिल्कुल वैसे ही रहेंगे) ...

# --- बैकग्राउंड शेड्यूलर ---
scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
scheduler.add_job(ping_all_services, 'interval', minutes=5)
scheduler.start()

atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
