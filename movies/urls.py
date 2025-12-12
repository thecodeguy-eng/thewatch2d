# movies/urls.py (app-level)
from django.urls import path
from django.views.generic import TemplateView
from .views import (
    HomeView,  # ✅ Add this back
    CategoryMoviesView, MovieDetailView,
    toggle_like, toggle_watchlist, SearchResultsView, ping_view, add_comment, add_reply, delete_comment
)

app_name = 'movies'

urlpatterns = [
    # ✅ Movies home page
    path('', HomeView.as_view(), name='home'),
    
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


     # Comment URLs
    path('movie/<int:pk>/comment/', add_comment, name='add_comment'),
    path('movie/<int:movie_pk>/comment/<int:comment_pk>/reply/', add_reply, name='add_reply'),
    path('comment/<int:pk>/delete/', delete_comment, name='delete_comment'),
]