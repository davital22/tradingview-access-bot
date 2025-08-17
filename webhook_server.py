import os
from flask import Flask, request, jsonify
from celery_worker import async_grant_access

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return "Invalid JSON", 400

        tradingview_username = None
        tradingview_script_url = None

        # meta_data ברמת האובייקט
        for meta in data.get("meta_data", []):
            if meta.get("key") == "tradingview_username":
                tradingview_username = meta.get("value")
            elif meta.get("key") == "tradingview_script_url":
                tradingview_script_url = meta.get("value")

        # בתוך line_items
        if not tradingview_script_url:
            for item in data.get("line_items", []):
                for meta in item.get("meta_data", []):
                    if meta.get("key") == "tradingview_script_url":
                        tradingview_script_url = meta.get("value")

        # שדות פשוטים בשורש
        tradingview_username = tradingview_username or data.get("tradingview_username")
        tradingview_script_url = tradingview_script_url or data.get("tradingview_script_url")

        if not tradingview_username or not tradingview_script_url:
            return "Missing username or script URL", 400

        # שליחת משימה ל-Celery
        async_grant_access.delay(tradingview_username, tradingview_script_url)

        return jsonify({
            "status": "queued",
            "user": tradingview_username,
            "script": tradingview_script_url
        }), 202

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.getenv("PORT", "8080"))
    app.run(host=host, port=port)
