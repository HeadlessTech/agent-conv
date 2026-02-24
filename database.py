from pymongo import MongoClient
from pymongo.database import Database
import os
from typing import Generator

# Database configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DATABASE_NAME = os.getenv("DATABASE_NAME", "voice_assistant")

# Create MongoDB client
client = MongoClient(MONGODB_URI)
database = client[DATABASE_NAME]


def init_db():
    """Initialize database - create indexes if needed"""
    # Create index on client id
    database.clients.create_index("clientId", unique=True)
    print(f"Connected to MongoDB: {DATABASE_NAME}")


def get_db() -> Generator[Database, None, None]:
    """Dependency to get database"""
    try:
        yield database
    finally:
        pass
