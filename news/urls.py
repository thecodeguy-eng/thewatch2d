# news/urls.py
from django.urls import path
from . import views

app_name = 'news'

urlpatterns = [
    path('', views.news_home, name='home'),
    path('search/', views.news_search, name='search'),
    path('category/<slug:slug>/', views.news_category, name='category'),
    path('article/<slug:slug>/', views.article_detail, name='article_detail'),
    path('comment/delete/<int:comment_id>/', views.delete_comment, name='delete_comment'),
]