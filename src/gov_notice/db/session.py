from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gov_notice.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)
