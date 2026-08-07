"""
Point d'entree pour la connexion a la base de donnees.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import Config
from app.models import Base

engine = create_engine(Config.DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Cree toutes les tables si elles n'existent pas deja."""
    Base.metadata.create_all(engine)


def get_session():
    """Retourne une nouvelle session SQLAlchemy."""
    return SessionLocal()