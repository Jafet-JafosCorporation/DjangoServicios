from django.urls import path
from api.views import (
    index_page,
    LoginView,
    ProductosView,
    ComprasView,
    AdminUsuariosView,
    AdminUsuarioDetalleView,
    AdminOrdenesView,
    AdminProductosView,
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
    path('admin/productos/', AdminProductosView.as_view()),
    path('admin/productos/<int:pk>/', AdminProductosView.as_view()),
]
