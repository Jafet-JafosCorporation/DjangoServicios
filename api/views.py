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

from api.db import users as users_col, products as products_col, orders as orders_col, reviews as reviews_col, addresses as addresses_col, tarjetas as tarjetas_col
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
        login_id = request.data.get('username', '') or request.data.get('correo', '')
        login_id = login_id.strip()
        password = request.data.get('password', '').strip()

        user_data = users_col.find_one({
            '$or': [
                {'username': login_id},
                {'email': login_id}
            ]
        })

        if not user_data or not check_password(password, user_data['password']):
            return Response({'error': 'Credenciales incorrectas.'}, status=status.HTTP_401_UNAUTHORIZED)
            
        if user_data.get('is_active') is False or user_data.get('estado') == 'Inactivo':
            return Response({'error': 'Esta cuenta ha sido inactivada por el administrador.'}, status=status.HTTP_403_FORBIDDEN)

        role = user_data['role']
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
    def post(self, request):
        nombre = request.data.get('nombre', '').strip()
        email = request.data.get('correo', '') or request.data.get('email', '')
        email = email.strip()
        password = request.data.get('password', '').strip()

        if not email or not password:
            return Response({'error': 'Correo y contraseña son requeridos.'}, status=400)
            
        if users_col.find_one({'$or': [{'username': nombre}, {'email': email}]}):
            return Response({'error': 'Este correo o nombre de usuario ya está registrado.'}, status=400)
        
        username_final = nombre if nombre else email.split('@')[0]

        new_user = {
            'username': username_final,
            'password': make_password(password),
            'role': 'usuario',
            'email': email,
            'estado': 'Activo',
            'is_active': True,
        }
        users_col.insert_one(new_user)
        
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
        metodo_pago = request.data.get('metodo_pago', 'Efectivo')

        product = products_col.find_one({'id': product_id}, PROJECTION)
        if not product:
            return Response({'error': 'Producto no encontrado.'}, status=404)
        if product['stock'] < quantity:
            return Response({'error': 'Stock insuficiente.'}, status=400)

        products_col.update_one({'id': product_id}, {'$inc': {'stock': -quantity}})
        
        # SOLUCIÓN: Usamos .lower() para evitar errores si el frontend envía "tarjeta" o "Tarjeta"
        estado_inicial = "Pagada" if metodo_pago.lower() == "tarjeta" else "Pendiente"
        
        order = {
            'username': request.user.username,
            'product_id': product_id,
            'nombre': product['nombre'],
            'quantity': quantity,
            'total': product['precio'] * quantity,
            'metodo_pago': metodo_pago,
            'estado': estado_inicial,
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

class AdminOrdenDetalleView(APIView):
    permission_classes = [IsAdmin]

    def put(self, request, orden_id):
        try:
            nuevo_estado = request.data.get('estado')
            if not nuevo_estado:
                return Response({'error': 'Falta enviar el nuevo estado.'}, status=400)

            orden = orders_col.find_one({'_id': ObjectId(orden_id)})
            if not orden:
                return Response({'error': 'Orden no encontrada.'}, status=404)

            if nuevo_estado == 'Cancelada' and orden.get('estado') != 'Cancelada':
                products_col.update_one(
                    {'id': orden['product_id']}, 
                    {'$inc': {'stock': orden['quantity']}}
                )
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
            
        result = users_col.update_one(
            {'username': username}, 
            {'$set': {'estado': 'Inactivo', 'is_active': False}}
        )
        if result.matched_count == 0:
            return Response({'error': 'Usuario no encontrado.'}, status=404)
        return Response({'mensaje': f'Usuario {username} inactivado correctamente.'})

    def put(self, request, username):
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
# Reviews 
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

        review_data = {
            'product_id': pk,
            'username': request.user.username,
            'rating': int(rating),
            'comment': comment,
            'fecha': date.today().isoformat(),
        }
        
        reviews_col.update_one(
            {'product_id': pk, 'username': request.user.username},
            {'$set': review_data},
            upsert=True
        )
        
        saved_review = reviews_col.find_one({'product_id': pk, 'username': request.user.username})
        return Response({'mensaje': 'Reseña guardada o actualizada exitosamente.', 'review': _serialize_review(saved_review)}, status=200)


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
# Direcciones de Envío
# ---------------------------------------------------------------------------
class DireccionesView(APIView):
    permission_classes = [IsUsuario]

    def get(self, request):
        direcciones = list(addresses_col.find({'username': request.user.username}, PROJECTION))
        return Response({'direcciones': direcciones})

    def post(self, request):
        nombre = request.data.get('nombreDestinatario', '').strip()
        calle = request.data.get('calleNumero', '').strip()
        ciudad = request.data.get('ciudad', '').strip()
        cp = request.data.get('codigoPostal', '').strip()

        if not nombre or not calle or not ciudad or not cp:
            return Response({'error': 'Falta información obligatoria del domicilio.'}, status=400)

        conteo = addresses_col.count_documents({'username': request.user.username})
        
        last = addresses_col.find_one(sort=[('id', -1)])
        new_id = str(int(last['id']) + 1) if (last and last.get('id', '').isdigit()) else str(date.today().toordinal() + conteo + 1)

        nueva_dir = {
            'id': new_id,
            'username': request.user.username,
            'nombreDestinatario': nombre,
            'calleNumero': calle,
            'colonia': request.data.get('colonia', 'General').strip(),
            'ciudad': ciudad,
            'codigoPostal': cp,
            'esPredeterminada': conteo == 0
        }
        addresses_col.insert_one(nueva_dir)
        nueva_dir.pop('_id', None)
        return Response({'mensaje': 'Domicilio guardado.', 'direccion': nueva_dir}, status=201)

    def delete(self, request, pk):
        result = addresses_col.delete_one({'id': str(pk), 'username': request.user.username})
        if result.deleted_count == 0:
            return Response({'error': 'Dirección no encontrada.'}, status=404)
        return Response({'mensaje': 'Domicilio eliminado.'})

# ---------------------------------------------------------------------------
# Tarjetas de Pago 
# ---------------------------------------------------------------------------
class TarjetasView(APIView):
    permission_classes = [IsUsuario]

    def get(self, request):
        tarjetas = list(tarjetas_col.find({'username': request.user.username}, PROJECTION))
        for t in tarjetas:
            if '_id' in t: 
                t['id'] = str(t.pop('_id')) 
        return Response({'tarjetas': tarjetas})

    def post(self, request):
        data = request.data
        numero_completo = str(data.get('numero', ''))
        
        if not numero_completo or len(numero_completo) < 4:
            return Response({'error': 'Número de tarjeta inválido.'}, status=400)
            
        nueva_tarjeta = {
            'username': request.user.username,
            'numero_oculto': f"**** **** **** {numero_completo[-4:]}",
            'nombre_titular': data.get('nombre', '').strip(),
            'fecha_expiracion': data.get('fecha_expiracion', '')
        }
        
        tarjetas_col.insert_one(nueva_tarjeta)
        nueva_tarjeta.pop('_id', None)
        return Response({'mensaje': 'Tarjeta guardada.', 'tarjeta': nueva_tarjeta}, status=201)


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

            productos_db = list(products_col.find({}, {'_id': 0, 'nombre': 1, 'precio': 1, 'stock': 1, 'categoria': 1, 'marca': 1}))
            
            catalogo_texto = ""
            for p in productos_db:
                nombre = p.get('nombre', 'Producto')
                marca = p.get('marca', 'Genérica')
                precio = p.get('precio', 0)
                stock = p.get('stock', 0)
                cat = p.get('categoria', 'General')
                catalogo_texto += f"- {nombre} (Marca: {marca}) | Precio: ${precio} MXN | Stock disponible: {stock} unidades | Categoría: {cat}\n"

            model = genai.GenerativeModel('gemini-3.5-flash')
            
            prompt = f"""
            Eres el asistente virtual inteligente de ventas y soporte técnico de la tienda 'JafosTechnologies Store'.
            Debes ser amable, profesional, perspicaz y dar respuestas concisas (máximo 2 o 3 párrafos cortos).
            
            AQUÍ TIENES EL INVENTARIO Y CATÁLOGO EN TIEMPO REAL DE NUESTRA TIENDA:
            {catalogo_texto}
            
            REGLAS ESTRICTAS DE NEGOCIO:
            1. Solo recomienda, vende o menciona productos que aparezcan en la lista anterior.
            2. Si el cliente pregunta por el stock de un producto y su stock dice '0 unidades', avísale amablemente que por el momento está agotado.
            3. Si el cliente pregunta por un hardware o marca que no está en la lista, dile con educación que no lo manejamos por ahora y ofrécele una alternativa similar de nuestro inventario.
            4. Menciona siempre los precios exactos en MXN cuando hables de los productos.
            5. Si pregunta sobre envíos, recuerda que en pedidos mayores a $1,000 MXN el envío es ¡completamente GRATIS!
            
            El cliente te acaba de escribir este mensaje: "{mensaje_usuario}"
            """
            try:
                respuesta = model.generate_content(prompt)
                return JsonResponse({'respuesta': respuesta.text}, status=200)
            except Exception as e:
                error_str = str(e)
                if '429' in error_str or 'Quota' in error_str or 'rate' in error_str.lower():
                    return JsonResponse({
                        'respuesta': '¡Vaya! En este momento hay muchos clientes consultando nuestro catálogo al mismo tiempo. Por favor, dame unos segundos para procesar todo y vuelve a preguntarme. 🤖⏳'
                    }, status=200)
                
                return JsonResponse({
                    'respuesta': 'Una disculpa, tuve una breve intermitencia al consultar el inventario. ¿Podrías repetirme tu pregunta?'
                }, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    return JsonResponse({'error': 'Método no permitido'}, status=405)