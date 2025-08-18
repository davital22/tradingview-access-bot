import os
from flask import Flask, request, jsonify
from celery_worker import async_grant_access

# יצירת האפליקציה של Flask
app = Flask(__name__)

# Health check – בשביל Heroku / ניטור
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# Webhook – נקודת הקליטה לקריאות מה-TradingView / WooCommerce
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        # קריאת ה-JSON שהתקבל
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return "Invalid JSON", 400

        tradingview_username = None
        tradingview_script_url = None

        # חיפוש meta_data ברמת האובייקט הראשי
        for meta in data.get("meta_data", []):
            if meta.get("key") == "tradingview_username":
                tradingview_username = meta.get("value")
            elif meta.get("key") == "tradingview_script_url":
                tradingview_script_url = meta.get("value")

        # חיפוש בתוך line_items (פריטים בהזמנה)
        if not tradingview_script_url:
            for item in data.get("line_items", []):
                for meta in item.get("meta_data", []):
                    if meta.get("key") == "tradingview_script_url":
                        tradingview_script_url = meta.get("value")

        # fallback – שדות פשוטים בשורש JSON
        tradingview_username = tradingview_username or data.get("tradingview_username")
        tradingview_script_url = tradingview_script_url or data.get("tradingview_script_url")

        # ולידציה
        if not tradingview_username or not tradingview_script_url:
            return jsonify({"error": "Missing username or script URL"}), 400

        # שליחת משימה ל-Celery (הרצה אסינכרונית)
        async_grant_access.delay(tradingview_username, tradingview_script_url)

        return jsonify({
            "status": "queued",
            "user": tradingview_username,
            "script": tradingview_script_url
        }), 202

    except Exception as e:
        # טיפול בשגיאות כלליות
        return jsonify({"error": str(e)}), 500


# הפעלה מקומית (Heroku משתמש ב-Procfile כדי להריץ gunicorn)
if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.getenv("PORT", "8080"))
    app.run(host=host, port=port, debug=True)
