import tomllib
import os
from types import SimpleNamespace
from typing import Dict, Any

_config_data = None
config = None

def load_config() -> Dict[str, Any]:
    global _config_data, config
    
    if _config_data is not None:
        return _config_data
    
    config_path = os.path.join(os.path.dirname(__file__), 'config.toml')
    
    try:
        with open(config_path, 'rb') as f:
            _config_data = tomllib.load(f)
        
        config = SimpleNamespace(**_config_data)
        return _config_data
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    except Exception as e:
        raise Exception(f"Error loading configuration: {e}")

def get_config() -> Dict[str, Any]:
    if _config_data is None:
        return load_config()
    return _config_data

try:
    _config_data = load_config()
except Exception as e:
    print(f"Warning: Could not load configuration: {e}")
    _config_data = {
        'bot': {'name': 'Orion'},
        'colors': {'embeds': '#9dd2ff'},
        'owners': {'ids': []}
    }
    config = SimpleNamespace(**_config_data)
