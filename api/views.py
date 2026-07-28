import os
import json
from datetime import datetime, timezone, date
from bson import ObjectId

from django.conf import settings
from django.shortcuts import render
from django.contrib.auth.hashers import check_password, make_password
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import jwt
import google.generativeai as genai

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
        # Aceptamos tanto la variable 'username' como 'correo' que viene del celular
        login_id = request.data.get('username', '') or request.data.get('correo', '')
        login_id = login_id.strip()
        password = request.data.get('password', '').strip()

        # BÚSQUEDA DUAL (OPCIÓN B): Busca si coincide con el username O con el email
        user_data = users_col.find_one({
            '$or': [
                {'username': login_id},
                {'email': login_id}
            ]
        })

        if not user_data or not check_password(password, user_data['password']):
            return Response({'error': 'Credenciales incorrectas.'}, status=status.HTTP_401_UNAUTHORIZED)
            
        # BLINDAJE: Bloquea si is_active es False O si el estado dice 'Inactivo'
        if user_data.get('is_active') is False or user_data.get('estado') == 'Inactivo':
            return Response({'error': 'Esta cuenta ha sido inactivada por el administrador.'}, status=status.HTTP_403_FORBIDDEN)

        role = user_data['role']
        # Usamos el username real del usuario para generar su token oficial
        token = _make_token(user_data['username'], role)

        if role == 'admin':
            welcome = {
                'mensaje': f'Bienvenido, administrador {user_data["username"]}.',
                'panel': 'Tienes acceso al panel de administracion.',
                'acciones_disponibles': ['GET /api/productos/', 'POST /api/admin/productos/', 'GET /api/admin/usuarios/', 'GET /api/admin/ordenes/'],
            }
        elif role == 'usuario':
            welcome = {
                'mensaje': f'Bienvenido, {user_data["username"]}.',
                'panel': 'Puedes explorar productos y realizar compras.',
                'acciones_disponibles': ['GET /api/productos/', 'POST /api/compras/', 'GET /api/mis-compras/'],
            }
        else:
            welcome = {
                'mensaje': 'Bienvenido, invitado.',
                'panel': 'Puedes ver los productos disponibles.',
                'acciones_disponibles': ['GET /api/productos/'],
            }

        return Response({'access_token': token, 'token_type': 'Bearer', 'rol': role, 'nombre': user_data['username'], **welcome})


class RegistroView(APIView):
    # Sin permission_classes para que sea público (cualquiera puede registrarse)
    def post(self, request):
        # Tomamos los datos del formulario móvil
        nombre = request.data.get('nombre', '').strip()
        email = request.data.get('correo', '') or request.data.get('email', '')
        email = email.strip()
        password = request.data.get('password', '').strip()

        if not email or not password:
            return Response({'error': 'Correo y contraseña son requeridos.'}, status=400)
            
        # Validamos que no exista ni el correo ni el nombre de usuario
        if users_col.find_one({'$or': [{'username': nombre}, {'email': email}]}):
            return Response({'error': 'Este correo o nombre de usuario ya está registrado.'}, status=400)
        
        # Si no puso nombre, usamos la primera parte de su correo
        username_final = nombre if nombre else email.split('@')[0]

        new_user = {
            'username': username_final,
            'password': make_password(password),
            'role': 'usuario', # Por defecto todos nacen como clientes normales
            'email': email,
            'estado': 'Activo',
            'is_active': True,
        }
        users_col.insert_one(new_user)
        
        # Le generamos un token para que inicie sesión automáticamente al registrarse
        token = _make_token(username_final, 'usuario')
        return Response({
            'mensaje': 'Cuenta creada con éxito.', 
            'access_token': token, 
            'nombre': username_final,
            'rol': 'usuario'
        }, status=201)

# ---------------------------------------------------------------------------
# Productos (acceso público)
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
            'estado': 'Activa',  # <-- Campo para filtrado de órdenes
        }
        orders_col.insert_one(order)
        order.pop('_id', None)
        return Response({'mensaje': 'Compra realizada.', 'orden': order}, status=201)


# ---------------------------------------------------------------------------
# Admin: órdenes y cancelación con devolución de stock
# ---------------------------------------------------------------------------

def _serialize_order(o):
    o['id'] = str(o.pop('_id'))
    return o

class AdminOrdenesView(APIView):
    permission_classes = [IsAdmin]

    def get(self, _request):
        all_orders = list(orders_col.find({}))
        grouped = {}
        for o in all_orders:
            o = _serialize_order(o)
            grouped.setdefault(o['username'], []).append({k: v for k, v in o.items() if k != 'username'})
        return Response({'ordenes': grouped})

# --- 2. GESTIÓN AVANZADA DE ESTADOS DE ÓRDENES ---
class AdminOrdenDetalleView(APIView):
    permission_classes = [IsAdmin]

    def put(self, request, orden_id):
        """Permite al administrador cambiar el estado de la orden (Ej. de Pagada a Enviada)"""
        try:
            nuevo_estado = request.data.get('estado')
            if not nuevo_estado:
                return Response({'error': 'Falta enviar el nuevo estado.'}, status=400)

            orden = orders_col.find_one({'_id': ObjectId(orden_id)})
            if not orden:
                return Response({'error': 'Orden no encontrada.'}, status=404)

            # Si el nuevo estado es Cancelada y antes no lo era, regresamos el stock
            if nuevo_estado == 'Cancelada' and orden.get('estado') != 'Cancelada':
                products_col.update_one(
                    {'id': orden['product_id']}, 
                    {'$inc': {'stock': orden['quantity']}}
                )
            # Si la orden estaba cancelada y la reactivamos, restamos el stock nuevamente
            elif orden.get('estado') == 'Cancelada' and nuevo_estado != 'Cancelada':
                products_col.update_one(
                    {'id': orden['product_id']}, 
                    {'$inc': {'stock': -orden['quantity']}}
                )

            orders_col.update_one({'_id': ObjectId(orden_id)}, {'$set': {'estado': nuevo_estado}})
            return Response({'mensaje': f'Estado de orden actualizado a {nuevo_estado}.'})
        except Exception:
            return Response({'error': 'ID de orden inválido.'}, status=400)

    def delete(self, _request, orden_id):
        # Mantenemos tu método delete por si acaso se sigue usando como atajo rápido
        try:
            orden = orders_col.find_one({'_id': ObjectId(orden_id)})
            if not orden: return Response({'error': 'Orden no encontrada.'}, status=404)
            if orden.get('estado') == 'Cancelada': return Response({'error': 'Ya estaba cancelada.'}, status=400)

            orders_col.update_one({'_id': ObjectId(orden_id)}, {'$set': {'estado': 'Cancelada'}})
            products_col.update_one({'id': orden['product_id']}, {'$inc': {'stock': orden['quantity']}})
            return Response({'mensaje': 'Orden cancelada y stock devuelto.'})
        except Exception: return Response({'error': 'ID inválido.'}, status=400)


# ---------------------------------------------------------------------------
# Admin: productos
# ---------------------------------------------------------------------------

# --- 1. ACTUALIZAR CREACIÓN Y EDICIÓN DE PRODUCTOS ---
class AdminProductosView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        last = products_col.find_one(sort=[('id', -1)])
        new_id = (last['id'] + 1) if last else 1
        product = {
            'id': new_id,
            'nombre': request.data.get('nombre', '').strip(),
            'precio': float(request.data.get('precio', 0)),
            'stock': int(request.data.get('stock', 0)),
            # NUEVOS CAMPOS PROFESIONALES:
            'categoria': request.data.get('categoria', 'General').strip(),
            'marca': request.data.get('marca', 'Genérica').strip(),
            'imagen': request.data.get('imagen', 'https://via.placeholder.com/150').strip(),
            'descripcion': request.data.get('descripcion', 'Sin descripción detallada.').strip(),
        }
        products_col.insert_one(product)
        product.pop('_id', None)
        return Response({'mensaje': 'Producto creado.', 'producto': product}, status=201)

    def put(self, request, pk):
        product = products_col.find_one({'id': pk}, PROJECTION)
        if not product:
            return Response({'error': 'Producto no encontrado.'}, status=404)
        updates = {
            'nombre': request.data.get('nombre', product['nombre']).strip(),
            'precio': float(request.data.get('precio', product['precio'])),
            'stock': int(request.data.get('stock', product['stock'])),
            'categoria': request.data.get('categoria', product.get('categoria', 'General')).strip(),
            'marca': request.data.get('marca', product.get('marca', 'Genérica')).strip(),
            'imagen': request.data.get('imagen', product.get('imagen', 'https://via.placeholder.com/150')).strip(),
            'descripcion': request.data.get('descripcion', product.get('descripcion', '')).strip(),
        }
        products_col.update_one({'id': pk}, {'$set': updates})
        return Response({'mensaje': 'Producto actualizado.', 'producto': {**product, **updates}})

    def delete(self, request, pk):
        result = products_col.delete_one({'id': pk})
        if result.deleted_count == 0:
            return Response({'error': 'Producto no encontrado.'}, status=404)
        return Response({'mensaje': f'Producto {pk} eliminado.'})


# ---------------------------------------------------------------------------
# Admin: usuarios (Estandarización de creación, inactivación y reactivación)
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
        
        # Estandarizado para que todos nazcan con las banderas correctas
        new_user = {
            'username': username,
            'password': make_password(request.data.get('password', '')),
            'role': request.data.get('role', 'usuario'),
            'email': request.data.get('email', ''),
            'estado': 'Activo',
            'is_active': True,
        }
        users_col.insert_one(new_user)
        return Response({'mensaje': 'Usuario creado.', 'usuario': {'username': username, 'role': new_user['role']}}, status=201)


class AdminUsuarioDetalleView(APIView):
    permission_classes = [IsAdmin]

    def delete(self, request, username):
        if username == request.user.username:
            return Response({'error': 'No puedes inactivar tu propia cuenta.'}, status=400)
            
        # Sincronizamos las dos variables al inactivar
        result = users_col.update_one(
            {'username': username}, 
            {'$set': {'estado': 'Inactivo', 'is_active': False}}
        )
        if result.matched_count == 0:
            return Response({'error': 'Usuario no encontrado.'}, status=404)
        return Response({'mensaje': f'Usuario {username} inactivado correctamente.'})

    def put(self, request, username):
        # Sincronizamos las dos variables al reactivar (o modificar estado)
        data = request.data
        if 'estado' in data:
            es_activo = (data['estado'] == 'Activo')
            users_col.update_one(
                {'username': username}, 
                {'$set': {'estado': data['estado'], 'is_active': es_activo}}
            )
            return Response({'mensaje': f'Estado actualizado a {data["estado"]}.'})
        return Response({'error': 'No se envió el parámetro estado.'}, status=400)


# ---------------------------------------------------------------------------
# Reviews (GET público, POST requiere usuario, DELETE requiere admin)
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
# Asistente IA (Google Gemini)
# ---------------------------------------------------------------------------

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

@csrf_exempt
def asistente_ia(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            mensaje_usuario = data.get('mensaje', '')

            if not mensaje_usuario:
                return JsonResponse({'error': 'Falta enviar el mensaje'}, status=400)

            model = genai.GenerativeModel('gemini-3.5-flash')
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