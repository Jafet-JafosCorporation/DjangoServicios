from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings
import jwt

from api.data import USERS


class InMemoryUser:
    """Objeto que simula un usuario de Django sin base de datos."""

    def __init__(self, username, role):
        self.username = username
        self.role = role
        self.is_authenticated = True
        self.is_active = True

    def __str__(self):
        return self.username


class InMemoryJWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ', 1)[1]
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.SIMPLE_JWT['ALGORITHM']],
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token expirado.')
        except jwt.InvalidTokenError:
            raise AuthenticationFailed('Token inválido.')

        username = payload.get('username')
        if not username or username not in USERS:
            raise AuthenticationFailed('Usuario no encontrado.')

        user_data = USERS[username]
        user = InMemoryUser(username=username, role=user_data['role'])
        return (user, token)
