from django.urls import path
from . import views

app_name = 'manga'

urlpatterns = [
    # Main manga pages
    path('', views.MangaListView.as_view(), name='list'),
    path('search/', views.MangaSearchView.as_view(), name='search'),
    path('trending/', views.TrendingMangaView.as_view(), name='trending'),
    path('featured/', views.FeaturedMangaView.as_view(), name='featured'),
    
    # Categories
    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    path('category/<slug:slug>/', views.CategoryDetailView.as_view(), name='category_detail'),
    
    # Manga details
    path('<slug:slug>/', views.MangaDetailView.as_view(), name='detail'),
    path('<slug:slug>/chapters/', views.MangaChaptersView.as_view(), name='chapters'),
    
    # Reader
    path('read/<slug:manga_slug>/chapter-<str:chapter_number>/', 
         views.ChapterReaderView.as_view(), name='chapter_detail'),
    
    # AJAX endpoints
    path('ajax/chapter/<int:chapter_id>/pages/', 
         views.GetChapterPagesView.as_view(), name='ajax_chapter_pages'),
    path('ajax/chapter/<int:chapter_id>/download-links/', 
         views.GetDownloadLinksView.as_view(), name='ajax_download_links'),
    path('ajax/download/<int:link_id>/track/', 
         views.TrackDownloadView.as_view(), name='ajax_track_download'),
    path('ajax/<int:manga_id>/like/', 
         views.LikeMangaView.as_view(), name='ajax_like_manga'),
    path('ajax/<int:manga_id>/bookmark/', 
         views.BookmarkMangaView.as_view(), name='ajax_bookmark_manga'),

     path('ajax/chapter/<int:chapter_id>/download/<str:format>/', 
          views.DownloadChapterView.as_view(), name='download_chapter'),

     # Comment endpoints
     path('ajax/comments/add/', views.AddCommentView.as_view(), name='ajax_add_comment'),
     path('ajax/comments/get/', views.GetCommentsView.as_view(), name='ajax_get_comments'),
    
    # Management
    path('management/', views.ManagementDashboardView.as_view(), name='management'),
]