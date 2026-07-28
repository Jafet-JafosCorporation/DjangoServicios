from django.urls import path
from api.views import (
    index_page,
    LoginView,
    RegistroView,
    ProductosView,
    ComprasView,
    AdminUsuariosView,
    AdminUsuarioDetalleView,
    AdminOrdenesView,
    AdminOrdenDetalleView,
    AdminProductosView,
    ReviewsView,
    AdminReviewDetalleView,
    DireccionesView,
    asistente_ia, # <--- 1. Agregamos nuestra función aquí
)

urlpatterns = [
    path('', index_page),
    path('login/', LoginView.as_view()),
    path('productos/', ProductosView.as_view()),
    path('compras/', ComprasView.as_view()),
    path('mis-compras/', ComprasView.as_view()),
    path('admin/usuarios/', AdminUsuariosView.as_view()),
    path('admin/usuarios/<str:username>/', AdminUsuarioDetalleView.as_view()),
    path('admin/ordenes/', AdminOrdenesView.as_view()),
    path('admin/ordenes/<str:orden_id>/', AdminOrdenDetalleView.as_view()),
    path('admin/productos/', AdminProductosView.as_view()),
    path('admin/productos/<int:pk>/', AdminProductosView.as_view()),
    path('productos/<int:pk>/reviews/', ReviewsView.as_view()),
    path('admin/reviews/<str:review_id>/', AdminReviewDetalleView.as_view()),
    path('registro/', RegistroView.as_view()),
    path('direcciones/', DireccionesView.as_view()),
    path('direcciones/<str:pk>/', DireccionesView.as_view()),
    # 2. Agregamos la ruta del chatbot al final
    path('chatbot/', asistente_ia, name='chatbot'),
]
