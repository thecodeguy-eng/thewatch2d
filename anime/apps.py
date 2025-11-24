from django.apps import AppConfig

class AnimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'anime'
    verbose_name = 'Anime Management'
    
    def ready(self):
        import anime.signals  # Import signals when app is ready
