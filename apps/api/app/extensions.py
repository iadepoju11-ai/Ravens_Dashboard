from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
# In-memory storage (the default) -- correct for how this app actually runs
# today (single gunicorn worker per container, same assumption already
# documented for Prometheus metrics in app/observability/metrics.py). A
# real multi-worker or multi-container deployment would need a shared
# backend (Redis) or these limits would be per-worker, not per-container.
limiter = Limiter(key_func=get_remote_address)
