import os
from dotenv import load_dotenv

load_dotenv()

_db_instance = None


def _get_db():
    global _db_instance
    if _db_instance is None:
        from pymongo import MongoClient
        uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
        _db_instance = MongoClient(uri)['djangoservicios']
    return _db_instance


class _LazyCollection:
    """Proxy que solo abre la conexion con MongoDB al primer uso."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, item):
        return getattr(_get_db()[self._name], item)


users    = _LazyCollection('users')
products = _LazyCollection('products')
orders   = _LazyCollection('orders')
