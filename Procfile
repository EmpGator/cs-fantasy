web: python manage.py collectstatic --noinput && gunicorn cs_fantasy.wsgi:application --bind 0.0.0.0:$PORT
worker: python manage.py qcluster
