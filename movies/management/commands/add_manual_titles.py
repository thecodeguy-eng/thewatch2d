"""
Add hand-picked titles from sources the scheduled scrapers don't cover
(meetdownload, hiphopkit) — the page URL is stored as the download link because
both sites only hand out short-lived tokenised file links on click.

Safe to re-run: an existing title / link is reused, never duplicated. TMDB
enrichment (rating, trailer, cast, crew, poster, genres) runs only when
TMDB_API_KEY is set; posters are re-hosted on R2 only when R2 is configured.
"""
from django.core.management.base import BaseCommand
from decouple import config

from movies.models import Movie, DownloadLink
from movies import tmdb
from movies.genres import link_tmdb_genres
from movies.r2 import rehost_image, is_configured as r2_ready
from movies.management.commands.enrich_tmdb import _sync_cast, _sync_crew

TITLES = [
    dict(title='Meet the Parents', year='2000', language='English', subtitle='English', filesize='411.55MB',
         url='https://meetdownload.com/9794e67f838e47cea6d5804be2eb7fb3/meet-the-parents-2000-71110-mkv',
         label='Meet The Parents (2000) MKV 411.55MB', source='meetdownload'),
    dict(title='Little Fockers', year='2010', language='French', subtitle='', filesize='',
         url='https://www33.hiphopkit.com/movies/view-movie/little-fockers-version-francaise/'
             'MS96ekw5Vk5GM29UODhndnl1NE9oNENyd0RIUHdvUDhHQjc3dWZnV2ZBST0/',
         label='Little Fockers [Version française] (2010) MP4', source='hiphopkit'),
    # Stream-only: same streamimdb embed (by TMDB id) the scraper uses site-wide.
    dict(title='Meet the Fockers', year='2004', language='English', subtitle='', filesize='',
         url='', label='', source='', stream_url='https://streamimdb.ru/embed/movie/693'),
]


class Command(BaseCommand):
    help = "Add hand-picked titles not covered by the scheduled scrapers (idempotent)."

    def handle(self, *args, **opts):
        r2 = r2_ready()
        public = config('R2_PUBLIC_URL', default='').rstrip('/')

        for t in TITLES:
            m = Movie.objects.filter(title__iexact=t['title']).first()
            if not m:
                m = Movie.objects.create(title=t['title'], video_url='', download_url=t['url'] or None,
                                         stream_url=t.get('stream_url') or None, scraped=True,
                                         vi_year=t['year'], vi_language=t['language'],
                                         vi_subtitle=t['subtitle'], vi_filesize=t['filesize'])
            if t['url'] and not m.download_links.filter(url=t['url']).exists():
                DownloadLink.objects.create(movie=m, label=t['label'], url=t['url'],
                                            source=t['source'], priority=1)
            if t['url'] and not m.download_url:
                Movie.objects.filter(pk=m.id).update(download_url=t['url'])
            if t.get('stream_url') and not m.stream_url:
                Movie.objects.filter(pk=m.id).update(stream_url=t['stream_url'])

            # Same per-title enrichment enrich_tmdb runs, scoped to this title.
            match = tmdb.search(m.title, t['year'], False) if tmdb.is_configured() else None
            d = tmdb.details(*match) if match else None
            if d:
                upd = {'tmdb_synced': True, 'tmdb_id': match[0], 'genres_synced': True}
                if d['rating'] is not None:
                    upd['rating'] = d['rating']
                if d.get('imdb_id'):
                    upd['imdb_id'] = d['imdb_id']
                if d['trailer_url']:
                    upd['trailer_url'] = d['trailer_url']
                if not m.description and d['overview']:
                    upd['description'] = d['overview']
                if not m.vi_cast and d['cast']:
                    upd['vi_cast'] = d['cast']
                if not m.vi_genre and d['genres']:
                    upd['vi_genre'] = d['genres'][:200]
                if not m.vi_runtime and d['runtime']:
                    upd['vi_runtime'] = d['runtime'][:30]
                if d['poster_url'] and not (public and (m.image_url or '').startswith(public)):
                    upd['image_url'] = (r2 and rehost_image(d['poster_url'])) or d['poster_url']
                if d.get('backdrop_url') and not m.backdrop_url:
                    upd['backdrop_url'] = (r2 and rehost_image(d['backdrop_url'])) or d['backdrop_url']
                Movie.objects.filter(pk=m.id).update(**upd)
                _sync_cast(m.id, d.get('cast_list'), r2)
                _sync_crew(m.id, d.get('crew_list'), r2)
                if d['genres']:
                    link_tmdb_genres(m, d['genres'])

            m.refresh_from_db()
            self.stdout.write(self.style.SUCCESS(
                f"OK {m.id} {m.title} {m.get_absolute_url()} tmdb={m.tmdb_id}"))
