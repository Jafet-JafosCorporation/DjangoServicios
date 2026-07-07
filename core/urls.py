from django.urls import path, include
from api.views import index_page

urlpatterns = [
    path('', index_page),
    path('api/', include('api.urls')),
]
