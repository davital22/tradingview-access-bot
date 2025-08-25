# webhook_server.py
import os
import json
from flask import Flask, request, jsonify
from celery_worker import async_grant_access

app = Flask(__name__)

def extract_fields(payload: dict):
    # פורמט “פשוט”
    if "tradingview_username" in payload and "tradingview_script_url" in payload:
        return (
            payload.get("tradingview_username"),
            payload.get("tradingview_script_url"),
            payload.get("trial_end_date_gmt") or payload.get("trial_end_gmt"),
        )

    # פורמט WooCommerce Subscriptions
    username = None
    for meta in payload.get("meta_data", []):
        if meta.get("key") == "tradingview_username":
            username = meta.get("value")
            break

    script_url = None
    for item in payload.get("line_items", []):
        for meta in item.get("meta_data", []):
            if meta.get("key") == "tradingview_script_url":
                script_url = meta.get("value")
                break
        if script_url:
            break

    trial_end = payload.get("trial_end_date_gmt") or payload.get("trial_end_gmt")
    return username, script_url, trial_end

@app.post("/webhook")
def webhook():
    try:
        data = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify({"error": "invalid json"}), 400

    username, script_url, trial_end = extract_fields(data)
    if not username or not script_url:
        return jsonify({"error": "missing username or script_url"}), 400

    # לוג עזר
    app.logger.warning(f"enqueue async_grant_access: user={username}, url={script_url}, trial_end_gmt={trial_end}")

    # קריאה עם 3 פרמטרים!
    async_grant_access.delay(username, script_url, trial_end)
    return jsonify({"status": "queued"}), 202

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=True)
