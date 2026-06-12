#!/bin/sh
set -e

# New migrations are generated locally, reviewed, and committed - not at container
# startup. e.g. after changing a model:
#   alembic revision --autogenerate -m "create users table"
# Only the resulting committed migration files are applied here:
until alembic upgrade head; do
  echo "Migration failed, retrying in 2s..."
  sleep 2
done

exec "$@"
