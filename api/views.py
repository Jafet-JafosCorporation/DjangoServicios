from datetime import datetime, timezone

from django.conf import settings
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import jwt

from api.data import USERS, PRODUCTS, ORDERS
from api.permissions import IsAdmin, IsUsuario


# ---------------------------------------------------------------------------
# Frontend HTML
# ---------------------------------------------------------------------------

def index_page(request):
    return render(request, 'api/index.html')


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _make_token(username: str, role: str) -> str:
    cfg = settings.SIMPLE_JWT
    payload = {
        'username': username,
        'role': role,
        'exp': datetime.now(timezone.utc) + cfg['ACCESS_TOKEN_LIFETIME'],
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=cfg['ALGORITHM'])


class LoginView(APIView):
    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '').strip()

        user_data = USERS.get(username)
        if not user_data or user_data['password'] != password:
            return Response(
                {'error': 'Credenciales incorrectas.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        role = user_data['role']
        token = _make_token(username, role)

        # Mensaje de bienvenida diferente según rol
        if role == 'admin':
            welcome = {
                'mensaje': f'Bienvenido, administrador {username}.',
                'panel': 'Tienes acceso al panel de administración.',
                'acciones_disponibles': [
                    'GET  /api/productos/',
                    'POST /api/admin/productos/',
                    'GET  /api/admin/usuarios/',
                    'GET  /api/admin/ordenes/',
                ],
            }
        elif role == 'usuario':
            welcome = {
                'mensaje': f'Bienvenido, {username}.',
                'panel': 'Puedes explorar productos y realizar compras.',
                'acciones_disponibles': [
                    'GET  /api/productos/',
                    'POST /api/compras/',
                    'GET  /api/mis-compras/',
                ],
            }
        else:
            welcome = {
                'mensaje': 'Bienvenido, invitado.',
                'panel': 'Puedes ver los productos disponibles.',
                'acciones_disponibles': [
                    'GET  /api/productos/',
                ],
            }

        return Response({
            'access_token': token,
            'token_type': 'Bearer',
            'rol': role,
            **welcome,
        })


# ---------------------------------------------------------------------------
# Productos (acceso público)
# ---------------------------------------------------------------------------

class ProductosView(APIView):
    def get(self, _request):
        return Response({'productos': PRODUCTS})


# ---------------------------------------------------------------------------
# Compras (solo usuarios y admins)
# ---------------------------------------------------------------------------

class ComprasView(APIView):
    permission_classes = [IsUsuario]

    def get(self, request):
        orders = ORDERS.get(request.user.username, [])
        return Response({'compras': orders})

    def post(self, request):
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))

        product = next((p for p in PRODUCTS if p['id'] == product_id), None)
        if not product:
            return Response({'error': 'Producto no encontrado.'}, status=404)
        if product['stock'] < quantity:
            return Response({'error': 'Stock insuficiente.'}, status=400)

        product['stock'] -= quantity
        order = {
            'product_id': product_id,
            'nombre': product['nombre'],
            'quantity': quantity,
            'total': product['precio'] * quantity,
        }
        ORDERS.setdefault(request.user.username, []).append(order)
        return Response({'mensaje': 'Compra realizada.', 'orden': order}, status=201)


# ---------------------------------------------------------------------------
# Admin: todas las órdenes
# ---------------------------------------------------------------------------

class AdminOrdenesView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'ordenes': ORDERS})


# ---------------------------------------------------------------------------
# Admin: gestión de productos
# ---------------------------------------------------------------------------

class AdminProductosView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        new_id = max(p['id'] for p in PRODUCTS) + 1 if PRODUCTS else 1
        product = {
            'id': new_id,
            'nombre': request.data.get('nombre', ''),
            'precio': float(request.data.get('precio', 0)),
            'stock': int(request.data.get('stock', 0)),
        }
        PRODUCTS.append(product)
        return Response({'mensaje': 'Producto creado.', 'producto': product}, status=201)

    def put(self, request, pk):
        product = next((p for p in PRODUCTS if p['id'] == pk), None)
        if not product:
            return Response({'error': 'Producto no encontrado.'}, status=404)
        product['nombre'] = request.data.get('nombre', product['nombre'])
        product['precio'] = float(request.data.get('precio', product['precio']))
        product['stock'] = int(request.data.get('stock', product['stock']))
        return Response({'mensaje': 'Producto actualizado.', 'producto': product})

    def delete(self, request, pk):
        product = next((p for p in PRODUCTS if p['id'] == pk), None)
        if not product:
            return Response({'error': 'Producto no encontrado.'}, status=404)
        PRODUCTS.remove(product)
        return Response({'mensaje': f'Producto {pk} eliminado.'})


# ---------------------------------------------------------------------------
# Admin: gestión de usuarios
# ---------------------------------------------------------------------------

class AdminUsuarioDetalleView(APIView):
    permission_classes = [IsAdmin]

    def delete(self, request, username):
        if username not in USERS:
            return Response({'error': 'Usuario no encontrado.'}, status=404)
        if username == request.user.username:
            return Response({'error': 'No puedes eliminar tu propia cuenta.'}, status=400)
        del USERS[username]
        return Response({'mensaje': f'Usuario {username} eliminado.'})


class AdminUsuariosView(APIView):
    permission_classes = [IsAdmin]

    def get(self, _request):
        safe = [
            {'username': u['username'], 'role': u['role'], 'email': u['email']}
            for u in USERS.values()
        ]
        return Response({'usuarios': safe})

    def post(self, request):
        username = request.data.get('username', '').strip()
        if not username:
            return Response({'error': 'El username es requerido.'}, status=400)
        if username in USERS:
            return Response({'error': 'El usuario ya existe.'}, status=400)
        USERS[username] = {
            'username': username,
            'password': request.data.get('password', ''),
            'role': request.data.get('role', 'usuario'),
            'email': request.data.get('email', ''),
        }
        return Response({'mensaje': 'Usuario creado.', 'usuario': {'username': username, 'role': USERS[username]['role']}}, status=201)
