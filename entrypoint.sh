#!/bin/sh
set -e

# Create all tables from current models, then stamp alembic as head.
# The migration chain is out of sync with current models, so we skip
# running migrations and let SQLAlchemy own the schema on a fresh DB.
python3 - <<'PYEOF'
from api.db.session import engine, Base
import api.models.setup
import api.models.payment
import api.models.users
Base.metadata.create_all(bind=engine, checkfirst=True)
print("Tables created/verified via SQLAlchemy")
PYEOF

# Mark all migrations as applied so alembic doesn't try to run them.
alembic stamp head

exec "$@"
