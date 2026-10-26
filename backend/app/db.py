from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

class Base(DeclarativeBase):
    pass

engine = create_engine(settings.database_url, pool_pre_ping=True, **(
    {'connect_args': {'check_same_thread': False}} if settings.database_url.startswith('sqlite')
    else {'pool_recycle': 1800, 'isolation_level': 'READ COMMITTED'}))
Session = sessionmaker(engine, expire_on_commit=False)

def get_db():
    with Session() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
