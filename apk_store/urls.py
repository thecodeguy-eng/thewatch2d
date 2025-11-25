from django.urls import path
from . import views

app_name = 'apk_store'

urlpatterns = [
    path('', views.home, name='home'),
    path('apks/', views.apk_list, name='apk_list'),
    path('games/', views.games_list, name='games_list'),
    path('apps/', views.apps_list, name='apps_list'),
    path('search/', views.search, name='search'),
    path('category/<slug:slug>/', views.category_detail, name='category_detail'),
    path('apk/<slug:slug>/', views.apk_detail, name='apk_detail'),
]