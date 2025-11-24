# main/templatetags/movie_extras.py
from django import template
from datetime import datetime, timedelta, timezone
from django.utils import timezone as dj_timezone

register = template.Library()

@register.filter
def is_recent(value, days=7):
    if not value:
        return False
    now = datetime.now(timezone.utc)
    return value >= now - timedelta(days=int(days))

@register.simple_tag
def trending_movies(count=10):
    from movies.models import Movie
    return Movie.objects.order_by('-views', '-created_at')[:int(count)]