"""
In-memory store: users and products.
Passwords are stored in plain text only for this demo.
"""

USERS = {
    'admin': {
        'username': 'admin',
        'password': 'admin123',
        'role': 'admin',
        'email': 'admin@tienda.com',
    },
    'juan': {
        'username': 'juan',
        'password': 'juan123',
        'role': 'usuario',
        'email': 'juan@correo.com',
    },
    'maria': {
        'username': 'maria',
        'password': 'maria123',
        'role': 'usuario',
        'email': 'maria@correo.com',
    },
}

PRODUCTS = [
    {'id': 1, 'nombre': 'Laptop Gamer',   'precio': 25000.00, 'stock': 5},
    {'id': 2, 'nombre': 'Mouse Inalámbrico', 'precio': 450.00,  'stock': 30},
    {'id': 3, 'nombre': 'Teclado Mecánico',  'precio': 1200.00, 'stock': 15},
    {'id': 4, 'nombre': 'Monitor 4K',        'precio': 8500.00, 'stock': 8},
]

# orders[username] = [ {product_id, quantity, total} ]
ORDERS = {}
