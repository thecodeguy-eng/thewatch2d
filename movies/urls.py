# movies/urls.py (app-level)
from django.urls import path
from django.views.generic import TemplateView
from .views import (
    CategoryMoviesView, MovieDetailView,
    toggle_like, toggle_watchlist, SearchResultsView, ping_view,
    # Remove HomeView from here since it's now in main app
)

app_name = 'movies'  # Add this to properly namespace

urlpatterns = [
    # ⚠️ REMOVED: path('', HomeView.as_view(), name='home'),
    # This is now handled by main app
    
    path('category/<int:cat_id>/', CategoryMoviesView.as_view(), name='category_movies'),
    path('movie/<int:pk>/', MovieDetailView.as_view(), name='movie_detail'),
    path('movie/<int:pk>/like/', toggle_like, name='toggle_like'),
    path('movie/<int:pk>/watchlist/', toggle_watchlist, name='toggle_watchlist'),
    path('search/', SearchResultsView.as_view(), name='search_results'),

    path('google302ebddf493cb41d.html', TemplateView.as_view(
        template_name='movies/google302ebddf493cb41d.html',
        content_type='text/html'
    )),

    path('wp_auth_encrypt_ping/', ping_view, name='ping'),
]