from datetime import datetime, timezone

from django.conf import settings
from django.shortcuts import render
from django.contrib.auth.hashers import check_password, make_password
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import jwt

from datetime import date
from bson import ObjectId
from api.db import users as users_col, products as products_col, orders as orders_col, reviews as reviews_col
from api.permissions import IsAdmin, IsUsuario

PROJECTION = {'_id': 0}


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

        user_data = users_col.find_one({'username': username})
        if not user_data or not check_password(password, user_data['password']):
            return Response({'error': 'Credenciales incorrectas.'}, status=status.HTTP_401_UNAUTHORIZED)

        role = user_data['role']
        token = _make_token(username, role)

        if role == 'admin':
            welcome = {
                'mensaje': f'Bienvenido, administrador {username}.',
                'panel': 'Tienes acceso al panel de administracion.',
                'acciones_disponibles': ['GET /api/productos/', 'POST /api/admin/productos/', 'GET /api/admin/usuarios/', 'GET /api/admin/ordenes/'],
            }
        elif role == 'usuario':
            welcome = {
                'mensaje': f'Bienvenido, {username}.',
                'panel': 'Puedes explorar productos y realizar compras.',
                'acciones_disponibles': ['GET /api/productos/', 'POST /api/compras/', 'GET /api/mis-compras/'],
            }
        else:
            welcome = {
                'mensaje': 'Bienvenido, invitado.',
                'panel': 'Puedes ver los productos disponibles.',
                'acciones_disponibles': ['GET /api/productos/'],
            }

        return Response({'access_token': token, 'token_type': 'Bearer', 'rol': role, **welcome})


# ---------------------------------------------------------------------------
# Productos (acceso publico)
# ---------------------------------------------------------------------------

class ProductosView(APIView):
    def get(self, _request):
        prods = list(products_col.find({}, PROJECTION))
        return Response({'productos': prods})


# ---------------------------------------------------------------------------
# Compras (solo usuarios y admins)
# ---------------------------------------------------------------------------

class ComprasView(APIView):
    permission_classes = [IsUsuario]

    def get(self, request):
        compras = list(orders_col.find({'username': request.user.username}, PROJECTION))
        return Response({'compras': compras})

    def post(self, request):
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))

        product = products_col.find_one({'id': product_id}, PROJECTION)
        if not product:
            return Response({'error': 'Producto no encontrado.'}, status=404)
        if product['stock'] < quantity:
            return Response({'error': 'Stock insuficiente.'}, status=400)

        products_col.update_one({'id': product_id}, {'$inc': {'stock': -quantity}})
        order = {
            'username': request.user.username,
            'product_id': product_id,
            'nombre': product['nombre'],
            'quantity': quantity,
            'total': product['precio'] * quantity,
        }
        orders_col.insert_one(order)
        order.pop('_id', None)
        return Response({'mensaje': 'Compra realizada.', 'orden': order}, status=201)


# ---------------------------------------------------------------------------
# Admin: ordenes
# ---------------------------------------------------------------------------

class AdminOrdenesView(APIView):
    permission_classes = [IsAdmin]

    def get(self, _request):
        all_orders = list(orders_col.find({}, PROJECTION))
        grouped = {}
        for o in all_orders:
            grouped.setdefault(o['username'], []).append({k: v for k, v in o.items() if k != 'username'})
        return Response({'ordenes': grouped})


# ---------------------------------------------------------------------------
# Admin: productos
# ---------------------------------------------------------------------------

class AdminProductosView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        last = products_col.find_one(sort=[('id', -1)])
        new_id = (last['id'] + 1) if last else 1
        product = {
            'id': new_id,
            'nombre': request.data.get('nombre', ''),
            'precio': float(request.data.get('precio', 0)),
            'stock': int(request.data.get('stock', 0)),
        }
        products_col.insert_one(product)
        product.pop('_id', None)
        return Response({'mensaje': 'Producto creado.', 'producto': product}, status=201)

    def put(self, request, pk):
        product = products_col.find_one({'id': pk}, PROJECTION)
        if not product:
            return Response({'error': 'Producto no encontrado.'}, status=404)
        updates = {
            'nombre': request.data.get('nombre', product['nombre']),
            'precio': float(request.data.get('precio', product['precio'])),
            'stock': int(request.data.get('stock', product['stock'])),
        }
        products_col.update_one({'id': pk}, {'$set': updates})
        return Response({'mensaje': 'Producto actualizado.', 'producto': {**product, **updates}})

    def delete(self, request, pk):
        result = products_col.delete_one({'id': pk})
        if result.deleted_count == 0:
            return Response({'error': 'Producto no encontrado.'}, status=404)
        return Response({'mensaje': f'Producto {pk} eliminado.'})


# ---------------------------------------------------------------------------
# Admin: usuarios
# ---------------------------------------------------------------------------

class AdminUsuariosView(APIView):
    permission_classes = [IsAdmin]

    def get(self, _request):
        user_list = list(users_col.find({}, {'_id': 0, 'password': 0}))
        return Response({'usuarios': user_list})

    def post(self, request):
        username = request.data.get('username', '').strip()
        if not username:
            return Response({'error': 'El username es requerido.'}, status=400)
        if users_col.find_one({'username': username}):
            return Response({'error': 'El usuario ya existe.'}, status=400)
        new_user = {
            'username': username,
            'password': make_password(request.data.get('password', '')),
            'role': request.data.get('role', 'usuario'),
            'email': request.data.get('email', ''),
        }
        users_col.insert_one(new_user)
        return Response({'mensaje': 'Usuario creado.', 'usuario': {'username': username, 'role': new_user['role']}}, status=201)


class AdminUsuarioDetalleView(APIView):
    permission_classes = [IsAdmin]

    def delete(self, request, username):
        if username == request.user.username:
            return Response({'error': 'No puedes eliminar tu propia cuenta.'}, status=400)
        result = users_col.delete_one({'username': username})
        if result.deleted_count == 0:
            return Response({'error': 'Usuario no encontrado.'}, status=404)
        return Response({'mensaje': f'Usuario {username} eliminado.'})


# ---------------------------------------------------------------------------
# Reviews (GET publico, POST requiere usuario, DELETE requiere admin)
# ---------------------------------------------------------------------------

def _serialize_review(r):
    r['id'] = str(r.pop('_id'))
    return r


class ReviewsView(APIView):

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsUsuario()]
        return []

    def get(self, _request, pk):
        if not products_col.find_one({'id': pk}, PROJECTION):
            return Response({'error': 'Producto no encontrado.'}, status=404)
        result = [_serialize_review(r) for r in reviews_col.find({'product_id': pk})]
        return Response({'product_id': pk, 'total': len(result), 'reviews': result})

    def post(self, request, pk):
        if not products_col.find_one({'id': pk}, PROJECTION):
            return Response({'error': 'Producto no encontrado.'}, status=404)

        rating = request.data.get('rating')
        comment = request.data.get('comment', '').strip()

        if rating is None or not str(rating).isdigit() or not (1 <= int(rating) <= 5):
            return Response({'error': 'rating debe ser un numero entre 1 y 5.'}, status=400)
        if not comment:
            return Response({'error': 'El comentario no puede estar vacio.'}, status=400)

        review = {
            'product_id': pk,
            'username': request.user.username,
            'rating': int(rating),
            'comment': comment,
            'fecha': date.today().isoformat(),
        }
        reviews_col.insert_one(review)
        return Response({'mensaje': 'Review agregada.', 'review': _serialize_review(review)}, status=201)


class AdminReviewDetalleView(APIView):
    permission_classes = [IsAdmin]

    def delete(self, _request, review_id):
        try:
            result = reviews_col.delete_one({'_id': ObjectId(review_id)})
        except Exception:
            return Response({'error': 'ID de review invalido.'}, status=400)
        if result.deleted_count == 0:
            return Response({'error': 'Review no encontrada.'}, status=404)
        return Response({'mensaje': f'Review {review_id} eliminada.'})

# ---------------------------------------------------------------------------
# crear la ruta de tu asistente virtual.
# ---------------------------------------------------------------------------
import os
import json
import google.generativeai as genai
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# Leemos tu llave secreta de forma segura
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

@csrf_exempt
def asistente_ia(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            mensaje_usuario = data.get('mensaje', '')

            if not mensaje_usuario:
                return JsonResponse({'error': 'Falta enviar el mensaje'}, status=400)

            # Usamos el modelo Flash: es la versión más rápida y ligera de Google
            model = genai.GenerativeModel('gemini-3.5-flash')
            
            # Aquí le damos su "personalidad" al bot para impresionar a tu docente
            prompt = f"""
            Eres un asistente virtual experto en ventas para una tienda en línea. 
            Debes ser amable, profesional y dar respuestas concisas. 
            El cliente te acaba de decir esto: "{mensaje_usuario}"
            """

            respuesta = model.generate_content(prompt)

            return JsonResponse({'respuesta': respuesta.text}, status=200)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    return JsonResponse({'error': 'Método no permitido'}, status=405)