import os
import asyncio
from celery import Celery
from grant_access import grant_access

# --- קביעת broker URL ---
# עדיפות לפי הסדר: CELERY_BROKER_URL (אם הגדרת ידנית), REDIS_URL (מ-Heroku),
# ואם לא קיים – נפילה ל-localhost
BROKER_URL = (
    os.getenv("CELERY_BROKER_URL")
    or os.getenv("REDIS_URL")
    or "redis://localhost:6379/0"
)

# יצירת אפליקציית Celery
app = Celery("tasks", broker=BROKER_URL)

# ב-Celery 6 צריך להפעיל זאת כדי שהחיבור ינסה שוב בזמן עלייה
app.conf.broker_connection_retry_on_startup = True

# אם Heroku נותן rediss:// (SSL) צריך לאפשר TLS ללא בדיקת תעודות
if BROKER_URL.startswith("rediss://"):
    app.conf.broker_use_ssl = {"ssl_cert_reqs": "none"}


# --- הטסק עצמו ---
@app.task
def async_grant_access(username: str, script_url: str) -> bool:
    """
    מפעיל את grant_access אסינכרונית. מחזיר True/False לפי הצלחה.
    """
    return asyncio.run(grant_access(username, script_url))
