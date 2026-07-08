from django.contrib.auth.hashers import make_password
from api.db import users, products


def seed_db():
    if users.count_documents({}) == 0:
        users.insert_many([
            {'username': 'admin', 'password': make_password('admin123'), 'role': 'admin',   'email': 'admin@tienda.com'},
            {'username': 'juan',  'password': make_password('juan123'),  'role': 'usuario', 'email': 'juan@correo.com'},
            {'username': 'maria', 'password': make_password('maria123'), 'role': 'usuario', 'email': 'maria@correo.com'},
        ])
        print('[DjangoServicios] Usuarios iniciales creados.')

    if products.count_documents({}) == 0:
        products.insert_many([
            {'id': 1, 'nombre': 'Laptop Gamer',      'precio': 25000.0, 'stock': 5},
            {'id': 2, 'nombre': 'Mouse Inalambrico',  'precio': 450.0,   'stock': 30},
            {'id': 3, 'nombre': 'Teclado Mecanico',   'precio': 1200.0,  'stock': 15},
            {'id': 4, 'nombre': 'Monitor 4K',         'precio': 8500.0,  'stock': 8},
        ])
        print('[DjangoServicios] Productos iniciales creados.')

    print('[DjangoServicios] MongoDB conectado correctamente.')
