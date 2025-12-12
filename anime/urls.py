from django.urls import path
from . import views

app_name = 'anime'

urlpatterns = [
    # Main anime pages
    path('', views.AnimeListView.as_view(), name='list'),
    path('search/', views.AnimeSearchView.as_view(), name='search'),
    path('trending/', views.TrendingAnimeView.as_view(), name='trending'),
    path('featured/', views.FeaturedAnimeView.as_view(), name='featured'),
    path('recently-added/', views.RecentlyAddedAnimeView.as_view(), name='recently_added'),
    
    # Categories & Genres
    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    path('category/<slug:slug>/', views.CategoryDetailView.as_view(), name='category_detail'),

    
    # Anime details - Using enhanced view
    path('<slug:slug>/', views.EnhancedAnimeDetailView.as_view(), name='detail'),
    path('<slug:slug>/episodes/', views.AnimeEpisodesView.as_view(), name='episodes'),
    path('watch/<slug:anime_slug>/episode/<int:episode_number>/', views.EpisodeDetailView.as_view(), name='episode_detail'),
    
    # AJAX endpoints
    path('ajax/episode/<int:episode_id>/download-links/', views.GetDownloadLinksView.as_view(), name='ajax_download_links'),
    path('ajax/<int:anime_id>/like/', views.LikeAnimeView.as_view(), name='ajax_like_anime'),
    path('ajax/<int:anime_id>/increment-views/', views.IncrementViewsView.as_view(), name='ajax_increment_views'),

    # Comment endpoints
    path('ajax/submit-comment/', views.SubmitCommentView.as_view(), name='ajax_submit_comment'),
    path('ajax/submit-reply/', views.SubmitReplyView.as_view(), name='ajax_submit_reply'),
    
    # New enhanced AJAX endpoints
    path('ajax/<int:anime_id>/update-image/', views.UpdateAnimeImageView.as_view(), name='ajax_update_image'),
    path('ajax/resolve-stream/', views.StreamLinkResolverView.as_view(), name='ajax_resolve_stream'),
    
    # Admin/Management
    path('management/', views.ManagementDashboardView.as_view(), name='management'),
    path('management/scrape/', views.TriggerScrapeView.as_view(), name='trigger_scrape'),
    path('management/fetch-images/', views.FetchMissingImagesView.as_view(), name='fetch_images'),
]