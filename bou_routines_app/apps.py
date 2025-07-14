from django.apps import AppConfig


class BouRoutinesAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bou_routines_app'

    def ready(self):
        import bou_routines_app.signals
