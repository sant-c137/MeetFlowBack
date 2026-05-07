from django.apps import AppConfig


class Meetflowv1Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'MeetFlowV1'

    def ready(self):
        import MeetFlowV1.signals
