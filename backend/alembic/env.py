from sqlalchemy import create_engine, pool

from alembic import context
from app import models  # noqa: F401
from app.config import get_settings
from app.db import Base

settings = get_settings()
url = settings.migration_database_url or settings.database_url
if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
