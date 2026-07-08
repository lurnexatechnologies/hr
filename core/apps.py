from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from django.conf import settings
        import os
        import logging

        logger = logging.getLogger(__name__)
        
        try:
            import firebase_admin
            from firebase_admin import credentials
            import json
            
            # Check if already initialized to avoid DuplicateAppError
            if not firebase_admin._apps:
                cred_json_str = os.getenv('FIREBASE_CREDENTIALS_JSON')
                if cred_json_str:
                    try:
                        cred_info = json.loads(cred_json_str)
                        cred = credentials.Certificate(cred_info)
                        firebase_admin.initialize_app(cred)
                        logger.info("Firebase Admin SDK initialized using environment variable JSON.")
                    except Exception as e:
                        logger.error(f"Error initializing Firebase Admin SDK with JSON env var: {e}")
                else:
                    cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
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
                            logger.warning(f"Firebase Admin SDK not initialized: credentials file not found at '{cred_path}', JSON env var empty, and default credentials failed ({e}). Native Push Notifications will be skipped.")
        except ImportError:
            logger.warning("firebase-admin package is not installed in the current python environment. Native Push Notifications will be skipped.")

