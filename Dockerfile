# 1. Usamos una versión ligera de Python profesional
FROM python:3.11-slim

# 2. Evitamos que Python guarde archivos caché (.pyc) en el contenedor
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Creamos la carpeta de trabajo dentro del servidor de Google
WORKDIR /app

# 4. Instalamos librerías del sistema necesarias para conectarse a redes y MongoDB
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 5. Copiamos tu archivo de requerimientos primero para aprovechar la caché
COPY requirements.txt .

# 6. Instalamos gunicorn y django-cors-headers además de tus librerías actuales
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn django-cors-headers

# 7. Copiamos todo el código de Django al contenedor
COPY . .

# 8. Recopilamos los archivos estáticos si los hubiera
RUN python manage.py collectstatic --noinput || true

# 9. Cloud Run por defecto inyecta la variable de entorno $PORT (usualmente 8080)
EXPOSE 8080

# 10. Arrancamos el servidor usando Gunicorn apuntando al puerto dinámico de Google
CMD gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120