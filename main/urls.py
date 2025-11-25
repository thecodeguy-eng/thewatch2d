from django.urls import path
from . import views

app_name = 'main'

urlpatterns = [
    # Change 'unified_home' to 'home' to match template references
    path('', views.UnifiedHomeView.as_view(), name='home'),
]