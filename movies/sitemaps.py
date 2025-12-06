from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.contrib.sites.models import Site
from .models import Movie, Category


class CustomSitemapMixin:
    def get_urls(self, site=None, **kwargs):
        # Force correct domain to prevent Google "URL not allowed" errors
        site = site or Site(domain='AlphaGL.store', name='AlphaGL')
        return super().get_urls(site=site, **kwargs)


class HomeSitemap(CustomSitemapMixin, Sitemap):
    changefreq = 'daily'
    priority = 1.0

    def items(self):
        return ['home']

    def location(self, item):
        return reverse(item)


class SearchSitemap(CustomSitemapMixin, Sitemap):
    changefreq = 'weekly'
    priority = 0.5

    def items(self):
        # Namespaced URL name for search results
        return ['movies:search_results']

    def location(self, item):
        return reverse(item)


class CategorySitemap(CustomSitemapMixin, Sitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        # Explicit ordering to avoid pagination warnings
        return Category.objects.all().order_by('name')

    def location(self, obj):
        return reverse('movies:category_movies', args=[obj.id])


class mastermap(CustomSitemapMixin, Sitemap):
    changefreq = 'daily'
    priority = 0.9

    def items(self):
        # Exclude movies without a valid video URL and order by primary key
        return (
            Movie.objects
            .exclude(video_url__isnull=True)
            .exclude(video_url__exact='')
            .order_by('pk')
        )

    def location(self, obj):
        return reverse('movies:movie_detail', args=[obj.pk])
