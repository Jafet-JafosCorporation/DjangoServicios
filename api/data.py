# Passwords stored as PBKDF2-SHA256 hashes (Django hashers).
# Plain text originals: admin=admin123, juan=juan123, maria=maria123

USERS = {
    'admin': {
        'username': 'admin',
        'password': 'pbkdf2_sha256$1200000$gjvn8ufH5eh83JqKwwpn93$LQkiXs7qzabCyKhXK9Ix/773Ahrq59Dg1RIap30VrEU=',
        'role': 'admin',
        'email': 'admin@tienda.com',
    },
    'juan': {
        'username': 'juan',
        'password': 'pbkdf2_sha256$1200000$5o4rHKO5KpDzwWGiPdRbLW$S/+5nTV0FVUwmGpm6JBMicwJbT0aZoFD7/s4y/J5RH4=',
        'role': 'usuario',
        'email': 'juan@correo.com',
    },
    'maria': {
        'username': 'maria',
        'password': 'pbkdf2_sha256$1200000$sUj7pXhX2zCrAT7ioHZ1O4$unj2TEJPqdYUQw8PMNwtgj5j27yxyqVy9nJPoF31k40=',
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
