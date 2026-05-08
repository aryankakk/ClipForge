-- This runs when the PostgreSQL container starts for the first time.
-- SQLAlchemy/Alembic will handle the actual table creation via init_db().
-- This file just ensures the database and extensions exist.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- The tables are created by FastAPI on startup via SQLAlchemy Base.metadata.create_all()
