from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = 'api'

    def ready(self):
        import os
        from dotenv import load_dotenv
        load_dotenv()
        uri = os.environ.get('MONGO_URI', '')
        if not uri or 'xxxxx' in uri or '<password>' in uri:
            print('[DjangoServicios] MONGO_URI no configurado — omitiendo seed de MongoDB.')
            return
        try:
            from api.seed import seed_db
            seed_db()
        except Exception as e:
            print(f'[DjangoServicios] No se pudo conectar a MongoDB: {e}')
