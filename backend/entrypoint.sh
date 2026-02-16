#!/bin/sh

# If the database is not ready, wait for it
if [ "$DATABASE" = "postgres" ]
then
    echo "Waiting for postgres..."

    while ! nc -z $SQL_HOST $SQL_PORT; do
      sleep 0.1
    done

    echo "PostgreSQL started"
fi

# Run migrations if enabled
if [ "$SKIP_MIGRATIONS" != "true" ]
then
    echo "Running migrations..."
    python manage.py migrate --noinput
fi

# Collect static files if enabled
if [ "$SKIP_COLLECTSTATIC" != "true" ]
then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

# Run the command passed as CMD
exec "$@"
