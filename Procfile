web: python manage.py migrate && gunicorn sweetbox_backend.wsgi --workers 2 --threads 2 --timeout 60 --max-requests 500 --max-requests-jitter 50 --log-file -
