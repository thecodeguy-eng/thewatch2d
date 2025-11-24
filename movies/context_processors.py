# movies/context_processors.py
from .models import Category

def categories_processor(request):
    return {'categories': Category.objects.all()}
