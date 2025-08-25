# celery_worker.py
import os
import asyncio
from typing import Optional
from celery import Celery
from grant_access import grant_access

BROKER_URL = (
    os.getenv("CELERY_BROKER_URL")
    or os.getenv("REDIS_URL")
    or "redis://localhost:6379/0"
)

app = Celery("tasks", broker=BROKER_URL)
app.conf.broker_connection_retry_on_startup = True

if BROKER_URL.startswith("rediss://"):
    app.conf.broker_use_ssl = {"ssl_cert_reqs": "none"}

@app.task(name="celery_worker.async_grant_access")
def async_grant_access(username: str, script_url: str, trial_end_gmt: Optional[str] = None) -> bool:
    # חשוב: להעביר את trial_end_gmt לפונקציה
    return asyncio.run(grant_access(username, script_url, trial_end_gmt))
