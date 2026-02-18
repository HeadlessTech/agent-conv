from sqlalchemy import Column, Integer, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Client(Base):
    """Client model for storing client information"""

    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    info = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Client(id={self.id})>"
