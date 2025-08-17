release: playwright install --with-deps chromium
web: gunicorn -w 2 -k gthread --threads 4 -t 120 webhook_server:app
worker: bash -c "playwright install chromium && celery -A celery_worker worker -l info -c 2 --prefetch-multiplier=1 --max-tasks-per-child=20"
