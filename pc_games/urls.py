# urls.py
from django.urls import path
from . import views

app_name = 'pc_games'

urlpatterns = [
    path('', views.game_list, name='game_list'),
    path('latest/', views.latest_games, name='latest'),
    path('categories/', views.category_list, name='category_list'),
    path('search/', views.search_games, name='search'),
    path('game/<slug:slug>/', views.game_detail, name='game_detail'),
]