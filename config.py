import tomllib
import os
from types import SimpleNamespace
from typing import Dict, Any
import database

_config_data = None
config_data = None

def _dict_to_namespace(data):
    if isinstance(data, dict):
        return SimpleNamespace(**{k: _dict_to_namespace(v) for k, v in data.items()})
    elif isinstance(data, list):
        return [_dict_to_namespace(item) for item in data]
    else:
        return data

def load_config() -> Dict[str, Any]:
    global _config_data, config_data
    
    if _config_data is not None:
        return _config_data
    
    config_path = os.path.join(os.path.dirname(__file__), 'config.toml')
    
    try:
        with open(config_path, 'rb') as f:
            _config_data = tomllib.load(f)
        
        config_data = _dict_to_namespace(_config_data)
        return _config_data
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    except Exception as e:
        raise Exception(f"Error loading configuration: {e}")

def get_config() -> Dict[str, Any]:
    if _config_data is None:
        return load_config()
    return _config_data

def get_database_ping():
    return database.ping_database()

try:
    load_config()
    db_ping = get_database_ping()
    if db_ping is not None:
        print(f"Loaded config: {config_data.bot.name} bot with {len(config_data.emojis.__dict__)} emojis, database ping: {db_ping}ms")
    else:
        print(f"Loaded config: {config_data.bot.name} bot with {len(config_data.emojis.__dict__)} emojis, database unavailable")
except Exception as e:
    print(f"Warning: Could not load configuration: {e}")
    _config_data = {
        'bot': {'name': 'Arbor'},
        'colors': {'embeds': '#9dd2ff'},
        'owners': {'ids': []},
        'emojis': {
            'moderation': '<:moderation:1424082709889810623>',
            'menu': '<:menu:1424082502053658644>',
            'down': '<:down:1424082358449209374>',
            'up': '<:up:1424082291973685268>',
            'right': '<:right:1424082178941124669>',
            'left': '<:left:1424082111253708820>',
            'error': '<:error:1424081965874806854>',
            'warning': '<:warning:1424081885772124340>',
            'add': '<:add:1424081808252993651>',
            'delete': '<:delete:1424081729467191416>',
            'edit': '<:edit:1424081620494713032>',
            'offline': '<:offline:1424081539016425602>',
            'online': '<:online:1424081456082325595>',
            'tick': '<:tick:1424079282946441419>',
            'home': '<:home:1424079222485549267>',
            'link': '<:link:1424079154713985024>',
            'info': '<:info:1424079090058526831>'
        }
    }
    config_data = _dict_to_namespace(_config_data)
