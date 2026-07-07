from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        import firebase_admin
        from firebase_admin import credentials
        from django.conf import settings
        import os
        import logging

        logger = logging.getLogger(__name__)
        cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
        
        # Check if already initialized to avoid DuplicateAppError
        if not firebase_admin._apps:
            if cred_path and os.path.exists(cred_path):
                try:
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                    logger.info("Firebase Admin SDK initialized using credentials file.")
                except Exception as e:
                    logger.error(f"Error initializing Firebase Admin SDK with credentials file: {e}")
            else:
                try:
                    firebase_admin.initialize_app()
                    logger.info("Firebase Admin SDK initialized using application default credentials.")
                except Exception as e:
                    logger.warning(f"Firebase Admin SDK not initialized: credentials file not found at '{cred_path}' and default credentials failed ({e}). Native Push Notifications will be skipped.")

