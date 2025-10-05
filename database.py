import os
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
import time

_database = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass 

def connect_database():
    global _database

    if _database is not None:
        return _database

    database_url = os.getenv('database')
    if not database_url:
        raise ValueError("Database URL not found in environment variables")

    try:
        client = MongoClient(database_url, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')

        _database = client.Arbor

        if 'Arbor' not in _database.list_collection_names():
            _database.create_collection('Arbor')

        if 'user_language_preferences' not in _database.list_collection_names():
            _database.create_collection('user_language_preferences')

        if 'reminders' not in _database.list_collection_names():
            _database.create_collection('reminders')

        if 'schedules' not in _database.list_collection_names():
            _database.create_collection('schedules')

        if 'afk' not in _database.list_collection_names():
            _database.create_collection('afk')

        if 'reputation' not in _database.list_collection_names():
            _database.create_collection('reputation')
        
        if 'rep_cooldowns' not in _database.list_collection_names():
            _database.create_collection('rep_cooldowns')

        if 'channel_locks' not in _database.list_collection_names():
            _database.create_collection('channel_locks')

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
        return round((end_time - start_time) * 1000)
    except Exception:
        return None