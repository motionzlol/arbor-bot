import os
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
import time

_database = None

# Load environment variables for database
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, will rely on system env vars

def connect_database():
    global _database

    if _database is not None:
        return _database

    database_url = os.getenv('database')
    if not database_url:
        raise ValueError("Database URL not found in environment variables")

    try:
        client = MongoClient(database_url, serverSelectionTimeoutMS=5000)
        # Test the connection
        client.admin.command('ping')

        # Get or create database
        _database = client.Arbor

        # Create collection if it doesn't exist
        if 'Arbor' not in _database.list_collection_names():
            _database.create_collection('Arbor')

        return _database

    except (ServerSelectionTimeoutError, ConnectionFailure) as e:
        raise ConnectionError(f"Failed to connect to database: {e}")
    except Exception as e:
        raise Exception(f"Database connection error: {e}")

def get_database():
    if _database is None:
        return connect_database()
    return _database

def ping_database():
    try:
        db = get_database()
        start_time = time.time()
        db.command('ping')
        end_time = time.time()
        return round((end_time - start_time) * 1000)  # Return ping in milliseconds
    except Exception:
        return None
