from django.apps import AppConfig


class ProfilesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'profiles'

    def ready(self):
        """
        Este método se ejecuta cuando la aplicación 'profiles' está lista.
        Es el lugar recomendado para importar las señales.
        """
        import profiles.signals