from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
from django.db import connection, reset_queries
from anime.models import Anime, Episode, AnimeCategory, AnimeGenre, DownloadLink
from django.db import models
import requests
from bs4 import BeautifulSoup
import re
import time
import random
from urllib.parse import urlparse, unquote, urljoin
import cloudscraper
import json
import os
import pickle

# ── Telegram helper ──────────────────────────────────────────
def _post_anime_to_telegram(anime, episode=None):
    try:
        from django.conf import settings
        from automation.telegram import send_photo, send_message

        channel = getattr(settings, 'TELEGRAM_ANIME_CHANNEL', '')
        site_url = getattr(settings, 'SITE_URL', 'https://watch2d.org')
        if not channel:
            return

        slug = getattr(anime, 'slug', None) or anime.pk

        title_lower = anime.title.lower()
        try:
            genre_names = ' '.join(g.name.lower() for g in (
                getattr(anime, 'genres', None) or
                getattr(anime, 'categories', None) or []
            ).all())
        except Exception:
            genre_names = ''
        combined = title_lower + ' ' + genre_names

        if any(kw in combined for kw in ['action', 'fighting', 'battle', 'war', 'demon', 'sword', 'ninja', 'shonen']):
            new_hashtags = "#Watch2D #Anime #ActionAnime #AnimeLovers #Shonen #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch #AnimeWorld #AnimeAlert"
            upd_hashtags = "#Watch2D #NewEpisode #Anime #ActionAnime #AnimeLovers #Shonen #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch"
        elif any(kw in combined for kw in ['romance', 'love', 'school', 'shoujo', 'slice of life', 'romantic']):
            new_hashtags = "#Watch2D #Anime #RomanceAnime #AnimeRomance #Shoujo #SliceOfLife #AnimeLovers #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch"
            upd_hashtags = "#Watch2D #NewEpisode #Anime #RomanceAnime #AnimeRomance #Shoujo #AnimeLovers #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch"
        elif any(kw in combined for kw in ['isekai', 'reincarnation', 'fantasy', 'magic', 'another world', 'overlord', 'sao']):
            new_hashtags = "#Watch2D #Anime #Isekai #FantasyAnime #AnimeLovers #IsekaiAnime #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch #AnimeWorld"
            upd_hashtags = "#Watch2D #NewEpisode #Anime #Isekai #FantasyAnime #IsekaiAnime #AnimeLovers #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch"
        elif any(kw in combined for kw in ['horror', 'thriller', 'mystery', 'psychological', 'dark', 'gore', 'seinen']):
            new_hashtags = "#Watch2D #Anime #HorrorAnime #DarkAnime #Seinen #AnimeThrilller #AnimeLovers #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch"
            upd_hashtags = "#Watch2D #NewEpisode #Anime #HorrorAnime #DarkAnime #Seinen #AnimeLovers #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch"
        elif any(kw in combined for kw in ['sport', 'soccer', 'basketball', 'boxing', 'volleyball', 'tennis', 'swimming']):
            new_hashtags = "#Watch2D #Anime #SportsAnime #AnimeLovers #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch #AnimeWorld #AnimeAlert"
            upd_hashtags = "#Watch2D #NewEpisode #Anime #SportsAnime #AnimeLovers #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch"
        elif any(kw in combined for kw in ['mecha', 'robot', 'gundam', 'sci-fi', 'science', 'space', 'future']):
            new_hashtags = "#Watch2D #Anime #MechaAnime #SciFiAnime #AnimeLovers #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch #AnimeWorld"
            upd_hashtags = "#Watch2D #NewEpisode #Anime #MechaAnime #SciFiAnime #AnimeLovers #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch"
        elif any(kw in combined for kw in ['comedy', 'funny', 'gag', 'parody', 'ecchi']):
            new_hashtags = "#Watch2D #Anime #ComedyAnime #FunnyAnime #AnimeLovers #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch #AnimeWorld"
            upd_hashtags = "#Watch2D #NewEpisode #Anime #ComedyAnime #FunnyAnime #AnimeLovers #AnimeCommunity #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch"
        else:
            new_hashtags = "#Watch2D #Anime #NewAnime #AnimeLovers #AnimeCommunity #AnimeWorld #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch #AnimeAlert #AnimeUpdate"
            upd_hashtags = "#Watch2D #NewEpisode #Anime #AnimeLovers #AnimeCommunity #AnimeUpdate #AnimeAlert #Otaku #FreeAnime #HDAnime #NowStreaming #MustWatch"

        if episode is None:
            url = f"{site_url}/anime/{slug}/"
            lines = [f"🎌 <b>{anime.title}</b>", ""]
            desc = getattr(anime, 'description', '') or getattr(anime, 'synopsis', '') or ''
            if desc:
                lines += [f"{desc[:200]}...", ""]
            ep_count = getattr(anime, 'total_episodes', None)
            if ep_count:
                lines.append(f"📺 <b>Episodes:</b> {ep_count}")
            status = getattr(anime, 'status', '') or getattr(anime, 'airing_status', '')
            if status:
                lines.append(f"📡 <b>Status:</b> {status}")
            if genre_names:
                display_genres = ', '.join(g.name for g in (
                    getattr(anime, 'genres', None) or
                    getattr(anime, 'categories', None) or []
                ).all()[:4])
                if display_genres:
                    lines.append(f"🏷 <b>Genre:</b> {display_genres}")
            lines += ["", f"🔗 <a href='{url}'>Watch on Watch2D</a>", "", new_hashtags]
            from automation.models import TelegramPost
            TelegramPost.objects.get_or_create(
                content_type='anime', content_id=anime.id,
                defaults={'content_title': anime.title, 'success': True},
            )
        else:
            ep_num = str(getattr(episode, 'episode_number', '') or getattr(episode, 'number', '') or '')
            url = f"{site_url}/anime/watch/{slug}/episode/{ep_num}/"
            ep_title = getattr(episode, 'title', '') or f"Episode {ep_num}"
            lines = [
                "🆕 <b>New Anime Episode!</b>", "",
                f"🎌 <b>{anime.title}</b>",
                f"▶️ <b>{ep_title}</b>", "",
                f"🔗 <a href='{url}'>Watch Now on Watch2D</a>", "",
                upd_hashtags,
            ]
            from automation.models import TelegramUpdate
            TelegramUpdate.objects.get_or_create(
                content_type='anime', content_id=anime.id,
                update_key=f"ep-{ep_num}",
                defaults={'content_title': anime.title, 'success': True},
            )

        caption = "\n".join(lines)
        cover = (
            getattr(anime, 'poster_url', '') or
            getattr(anime, 'cover_image', '') or
            getattr(anime, 'image_url', '') or ''
        )
        if cover:
            send_photo(channel, cover, caption)
        else:
            send_message(channel, caption)

        label = "NEW ANIME" if episode is None else f"EP {ep_num}"
        print(f"📢 Telegram: [{label}] {anime.title}")

    except Exception as e:
        print(f"⚠️ Telegram post failed (non-critical): {e}")
# ─────────────────────────────────────────────────────────────

API_URL = 'https://chia-anime.su/wp-json/wp/v2/posts/'

# All known anime video embed / streaming domains
VIDEO_DOMAINS = [
    'embedz', 'vidstream', 'streamtape', 'mixdrop', 'doodstream',
    'mega.nz', 'fypttvideos', 'gogoplay', 'playtaku', 'vidcdn',
    'animixplay', 'ok.ru', 'okru', 'mp4upload', 'yourupload',
    'fembed', 'jawcloud', 'cloudvideo', 'uservideo', 'sbplay',
    'sbembed', 'cloudembed', 'filemoon', 'voe.sx', 'upstream',
    'embed.su', 'alions', 'ani-stream', 'goload', 'gogoanime',
    'vidplay', 'megacloud', 'rapid-cloud', 'cache.rapid',
    'embtaku', 'gogohd', 'animefever', 'chiaanime',
    'fusevideo', 'vudeo', 'streamlare', 'streamwish',
    'filelions', 'dropload', 'smoothpre', 'hlsplay',
    'vidmoly', 'vidhide', 'vidhd', 'embedgram',
]


class Command(BaseCommand):
    help = 'Scrape ALL anime data from chia-anime.su and update database'

    def __init__(self):
        super().__init__()
        self.cache_file = 'scraped_pages_cache.pkl'
        self.scraped_pages = self.load_scraped_pages()
        self.debug_html_dir = 'debug_html'

    # ── Cache helpers ────────────────────────────────────────────

    def load_scraped_pages(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'rb') as f:
                    data = pickle.load(f)
                    print(f"📂 Loaded {len(data)} previously scraped pages from cache")
                    return data
            except Exception as e:
                print(f"⚠️ Could not load cache: {e}")
        return set()

    def save_scraped_pages(self):
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.scraped_pages, f)
            print(f"💾 Saved {len(self.scraped_pages)} scraped pages to cache")
        except Exception as e:
            print(f"⚠️ Could not save cache: {e}")

    def mark_page_as_scraped(self, page_number):
        self.scraped_pages.add(page_number)
        if len(self.scraped_pages) % 5 == 0:
            self.save_scraped_pages()

    def is_page_scraped(self, page_number):
        return page_number in self.scraped_pages

    # ── CLI arguments ────────────────────────────────────────────

    def add_arguments(self, parser):
        parser.add_argument('--max-pages', type=int, default=None)
        parser.add_argument('--start-page', type=int, default=1)
        parser.add_argument('--per-page', type=int, default=100)
        parser.add_argument('--delay-min', type=float, default=2.0)
        parser.add_argument('--delay-max', type=float, default=4.0)
        parser.add_argument('--force-rescrape', action='store_true',
                            help='Force rescrape of already scraped pages')
        parser.add_argument('--clear-cache', action='store_true',
                            help='Clear the scraped pages cache before starting')
        parser.add_argument('--debug-html', action='store_true',
                            help='Save fetched episode HTML to debug_html/ for inspection')
        parser.add_argument('--skip-no-links', action='store_true', default=False,
                            help='Skip episodes with no links (default: still create episode record)')

    # ── DB helpers ───────────────────────────────────────────────

    def refresh_db_connection(self):
        try:
            reset_queries()
            connection.close()
            print("  🔄 Database connection refreshed")
        except Exception as e:
            print(f"  ⚠️ Connection refresh warning: {e}")

    # ── Title parsing ────────────────────────────────────────────

    def clean_title(self, title):
        title = re.sub(r'\s+', ' ', title).strip()
        title = re.sub(r'\s*English Subbed$', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s*English Sub$', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s*\(Dub\)$', '', title, flags=re.IGNORECASE)
        episode_match = re.search(r'Episode\s+(\d+(?:\.\d+)?)', title, re.IGNORECASE)
        episode_number = float(episode_match.group(1)) if episode_match else None
        if episode_number and episode_number == int(episode_number):
            episode_number = int(episode_number)
        anime_title = re.sub(r'\s*Episode\s+\d+(?:\.\d+)?', '', title, flags=re.IGNORECASE).strip()
        return anime_title, episode_number

    # ── Poster extraction ────────────────────────────────────────

    def extract_anime_poster(self, post_content, anime_title):
        try:
            if post_content:
                soup = BeautifulSoup(post_content, 'html.parser')
                for img in soup.find_all('img'):
                    src = img.get('src', '').strip()
                    alt = img.get('alt', '').lower()
                    if any(skip in src.lower() for skip in ['logo', 'banner', 'ad', 'button']):
                        continue
                    if src and (anime_title.lower() in alt or 'poster' in alt or 'cover' in alt):
                        return src
                for img in soup.find_all('img'):
                    src = img.get('src', '').strip()
                    if src and not any(skip in src.lower() for skip in ['logo', 'banner', 'ad', 'button']):
                        return src
        except Exception as e:
            print(f"  ⚠️ Error extracting poster: {e}")
        return None

    # ── Quality detection ────────────────────────────────────────

    def extract_quality_from_text(self, text):
        if not text:
            return '720p'
        text = text.lower()
        if '1080p' in text or 'fhd' in text or '1080' in text:
            return '1080p'
        elif '720p' in text or 'hd' in text or '720' in text:
            return '720p'
        elif '480p' in text or 'sd' in text or '480' in text:
            return '480p'
        elif '360p' in text or '360' in text:
            return '360p'
        return '720p'

    # ── Host name ────────────────────────────────────────────────

    def get_host_name(self, url):
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace('www.', '')
            known = {
                'mega.nz': 'mega', 'fypttvideos.xyz': 'vidstreaming',
                'embedz.net': 'embedz', 'streamtape.com': 'streamtape',
                'mixdrop.co': 'mixdrop', 'doodstream.com': 'doodstream',
                'mp4upload.com': 'mp4upload', 'ok.ru': 'okru',
                'filemoon.sx': 'filemoon', 'voe.sx': 'voe',
                'streamwish.com': 'streamwish', 'filelions.com': 'filelions',
                'vidhide.com': 'vidhide', 'vidplay.online': 'vidplay',
            }
            for k, v in known.items():
                if k in domain:
                    return v
            return domain.split('.')[0] if domain else 'unknown'
        except Exception:
            return 'unknown'

    # ── Page fetcher ─────────────────────────────────────────────

    def make_scraper(self):
        """Create a fresh cloudscraper instance with browser-like headers."""
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        return scraper

    def fetch_episode_page(self, post_link, debug=False, slug='debug'):
        """Fetch the episode page and optionally save HTML for debugging."""
        try:
            scraper = self.make_scraper()
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://chia-anime.su/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            response = scraper.get(post_link, headers=headers, timeout=20)
            response.raise_for_status()
            html = response.text

            if debug:
                os.makedirs(self.debug_html_dir, exist_ok=True)
                safe_slug = re.sub(r'[^\w\-]', '_', slug)[:80]
                path = os.path.join(self.debug_html_dir, f"{safe_slug}.html")
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"  💾 Debug HTML saved: {path}")

            return html

        except Exception as e:
            print(f"  ⚠️ Error fetching episode page {post_link}: {e}")
            return None

    # ── Link extraction ──────────────────────────────────────────

    def extract_download_links(self, html_content, post_content=''):
        """
        Aggressively extract all video embed/stream links from page HTML.
        Covers iframes, <a> tags, inline scripts, data-* attributes.
        """
        links = []
        if not html_content:
            return links

        soup = BeautifulSoup(html_content, 'html.parser')

        # ── 1. Every <iframe> (including lazy-loaded data-src) ───
        for iframe in soup.find_all('iframe'):
            src = (
                iframe.get('src', '').strip() or
                iframe.get('data-src', '').strip() or
                iframe.get('data-lazy-src', '').strip()
            )
            if src:
                src = self._normalise_url(src, 'https://chia-anime.su')
                quality = self.extract_quality_from_text(iframe.get('title', '') + src)
                links.append({
                    'url': src,
                    'label': iframe.get('title', '') or 'Stream',
                    'quality': quality,
                    'source': 'iframe',
                })
                print(f"  🎥 iframe: {src}")

        # ── 2. <a> tags pointing at video hosts ──────────────────
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = a.get_text(strip=True)
            if href and any(d in href.lower() for d in VIDEO_DOMAINS):
                quality = self.extract_quality_from_text(text + href)
                links.append({
                    'url': href,
                    'label': text or 'Stream',
                    'quality': quality,
                    'source': 'a-tag',
                })
                print(f"  🔗 a-tag: {text} → {href}")

        # ── 3. Inline <script> URL mining ───────────────────────
        domain_pattern = '|'.join(re.escape(d) for d in VIDEO_DOMAINS)
        url_re = re.compile(
            r'["\`\']((?:https?:)?//(?:www\.)?(?:' + domain_pattern + r')[^\s"\'`<>\\]{3,})["\`\']',
            re.IGNORECASE
        )
        for script in soup.find_all('script'):
            script_text = script.string or ''
            for match in url_re.finditer(script_text):
                url = self._normalise_url(match.group(1), 'https://chia-anime.su')
                quality = self.extract_quality_from_text(url)
                links.append({
                    'url': url,
                    'label': 'Stream',
                    'quality': quality,
                    'source': 'script',
                })
                print(f"  📜 script url: {url}")

        # ── 4. data-* attributes on any element ─────────────────
        data_attrs = ['data-src', 'data-url', 'data-video', 'data-embed',
                      'data-stream', 'data-file', 'data-source', 'data-player']
        for el in soup.find_all(True):
            for attr in data_attrs:
                val = el.get(attr, '').strip()
                if val and any(d in val.lower() for d in VIDEO_DOMAINS):
                    val = self._normalise_url(val, 'https://chia-anime.su')
                    quality = self.extract_quality_from_text(val)
                    links.append({
                        'url': val,
                        'label': attr.replace('data-', '').capitalize(),
                        'quality': quality,
                        'source': 'data-attr',
                    })
                    print(f"  🗂️  {attr}: {val}")

        # ── 5. Plain-text URL scan (fallback) ───────────────────
        raw_urls = re.findall(
            r'https?://(?:www\.)?(?:' + domain_pattern + r')[^\s"\'<>\\]+',
            html_content, re.IGNORECASE
        )
        for url in raw_urls:
            quality = self.extract_quality_from_text(url)
            links.append({
                'url': url,
                'label': 'Stream',
                'quality': quality,
                'source': 'raw-text',
            })

        # ── 6. Deduplicate by URL ────────────────────────────────
        seen = set()
        unique = []
        for lnk in links:
            if lnk['url'] not in seen and lnk['url'].startswith('http'):
                seen.add(lnk['url'])
                unique.append(lnk)

        return unique

    def _normalise_url(self, url, base):
        """Turn protocol-relative or relative URLs into absolute ones."""
        url = url.strip()
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return base.rstrip('/') + url
        return url

    # ── Category helper ──────────────────────────────────────────

    def get_or_create_category(self, category_id):
        try:
            scraper = self.make_scraper()
            response = scraper.get(
                f"https://chia-anime.su/wp-json/wp/v2/categories/{category_id}",
                timeout=10
            )
            response.raise_for_status()
            category_data = response.json()
            category_name = category_data.get('name', 'Uncategorized')
            category, _ = AnimeCategory.objects.get_or_create(
                name=category_name,
                defaults={
                    'slug': slugify(category_name),
                    'description': category_data.get('description', ''),
                    'is_active': True,
                }
            )
            return category
        except Exception as e:
            print(f"  ⚠️ Error fetching category {category_id}: {e}")
            category, _ = AnimeCategory.objects.get_or_create(
                name='Anime',
                defaults={'slug': 'anime', 'is_active': True}
            )
            return category

    # ── Total posts ──────────────────────────────────────────────

    def get_total_posts(self):
        try:
            scraper = self.make_scraper()
            response = scraper.get(
                API_URL,
                params={'page': 1, 'per_page': 1, 'status': 'publish'},
                timeout=15
            )
            response.raise_for_status()
            return (
                int(response.headers.get('X-WP-Total', 0)),
                int(response.headers.get('X-WP-TotalPages', 0)),
            )
        except Exception as e:
            print(f"⚠️ Could not get total post count: {e}")
            return None, None

    # ── Main handle ──────────────────────────────────────────────

    def handle(self, *args, **options):
        max_pages      = options.get('max_pages')
        start_page     = options.get('start_page', 1)
        per_page       = min(options.get('per_page', 100), 100)
        delay_min      = options.get('delay_min', 2.0)
        delay_max      = options.get('delay_max', 4.0)
        force_rescrape = options.get('force_rescrape', False)
        clear_cache    = options.get('clear_cache', False)
        debug_html     = options.get('debug_html', False)
        skip_no_links  = options.get('skip_no_links', False)

        if clear_cache:
            self.scraped_pages.clear()
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            print("🗑️  Cleared scraped pages cache")

        print("🚀 Starting comprehensive scrape from chia-anime.su...")
        print(f"   📊 Starting from page : {start_page}")
        print(f"   📄 Posts per page     : {per_page}")
        print(f"   ⏱️  Request delay      : {delay_min}-{delay_max}s")
        print(f"   🔄 Force rescrape     : {force_rescrape}")
        print(f"   🐛 Debug HTML         : {debug_html}")
        print(f"   ⏭️  Skip no-link eps  : {skip_no_links}")
        print(f"   📂 Cached pages       : {len(self.scraped_pages)}")

        total_posts, total_pages = self.get_total_posts()
        if total_posts:
            print(f"   📈 Total posts        : {total_posts}")
            print(f"   📚 Total pages        : {total_pages}")

        page = start_page
        processed_posts = 0
        skipped_pages   = 0
        consecutive_empty = 0
        MAX_EMPTY = 3

        stats = {
            'new_animes': 0, 'existing_animes': 0,
            'new_episodes': 0, 'existing_episodes': 0,
            'new_links': 0, 'updated_links': 0, 'skipped_links': 0,
            'no_links_skipped': 0,
        }

        while True:
            # ── Page-limit guard ─────────────────────────────────
            if max_pages and page >= start_page + max_pages:
                print(f"✅ Reached max pages limit ({max_pages})")
                break

            # ── Skip already-scraped pages ───────────────────────
            if not force_rescrape and self.is_page_scraped(page):
                print(f"\n⏭️  Page {page} — ALREADY SCRAPED (skipping)")
                skipped_pages += 1
                page += 1
                continue

            # ── Periodic DB refresh ──────────────────────────────
            if (page - start_page) > 0 and (page - start_page) % 10 == 0:
                self.refresh_db_connection()

            try:
                print(f"\n🌐 Fetching API page {page}…")
                scraper = self.make_scraper()
                response = scraper.get(
                    API_URL,
                    params={
                        'page': page, 'per_page': per_page,
                        'status': 'publish', 'order': 'desc', 'orderby': 'date',
                    },
                    headers={"Accept": "application/json"},
                    timeout=20,
                )

                if response.status_code == 404:
                    print("✅ 404 — no more pages")
                    break
                if response.status_code == 400:
                    consecutive_empty += 1
                    print(f"⚠️ 400 Bad Request on page {page}")
                    if consecutive_empty >= MAX_EMPTY:
                        break
                    page += 1
                    continue

                response.raise_for_status()
                posts = response.json()

                if not posts:
                    consecutive_empty += 1
                    print(f"🔭 Empty page {page} ({consecutive_empty}/{MAX_EMPTY})")
                    if consecutive_empty >= MAX_EMPTY:
                        break
                    page += 1
                    time.sleep(random.uniform(delay_min, delay_max))
                    continue

                consecutive_empty = 0
                print(f"📄 Processing {len(posts)} posts from page {page}…")
                page_processed = 0

                for post in posts:
                    try:
                        raw_title = post.get('title', {}).get('rendered', '').strip()
                        if not raw_title:
                            continue

                        print(f"\n🎬 {raw_title}")
                        anime_title, episode_number = self.clean_title(raw_title)

                        if not episode_number:
                            print(f"  ⚠️ No episode number — skipping")
                            continue

                        post_link   = post.get('link', '')
                        content_raw = post.get('content', {}).get('rendered', '')
                        description = BeautifulSoup(
                            post.get('excerpt', {}).get('rendered', ''), 'html.parser'
                        ).get_text().strip()

                        # ── Fetch episode page HTML ───────────────
                        print(f"  🌍 Fetching: {post_link}")
                        episode_html = self.fetch_episode_page(
                            post_link,
                            debug=debug_html,
                            slug=post.get('slug', 'episode'),
                        )
                        time.sleep(random.uniform(1.0, 2.0))   # polite delay after page fetch

                        # ── Extract links ─────────────────────────
                        download_links = self.extract_download_links(episode_html, content_raw)

                        if not download_links:
                            print(f"  ⚠️ No links found for: {anime_title} Episode {episode_number}")
                            if skip_no_links:
                                stats['no_links_skipped'] += 1
                                continue
                            # Still create the anime/episode record without links

                        else:
                            print(f"  ✅ Found {len(download_links)} link(s)")

                        poster_url = self.extract_anime_poster(content_raw, anime_title)

                        # ── Get / create Anime ────────────────────
                        try:
                            anime, anime_created = Anime.objects.get_or_create(
                                title=anime_title,
                                defaults={
                                    'slug': slugify(anime_title),
                                    'description': description,
                                    'status': 'ongoing',
                                    'is_active': True,
                                    'anime_id': 0,
                                    'anime_session': f"chia_{slugify(anime_title)}",
                                    'poster_url': poster_url or '',
                                }
                            )

                            if anime_created:
                                print(f"  🆕 NEW anime: {anime_title}")
                                stats['new_animes'] += 1
                                _post_anime_to_telegram(anime, episode=None)
                            else:
                                print(f"  ♻️  Existing anime: {anime_title}")
                                stats['existing_animes'] += 1
                                # Update poster if missing
                                if poster_url and not anime.poster_url:
                                    anime.poster_url = poster_url
                                    anime.save(update_fields=['poster_url'])
                                    print(f"  🖼️  Updated poster")

                            if anime_created and post.get('categories'):
                                try:
                                    category = self.get_or_create_category(post['categories'][0])
                                    anime.category = category
                                    anime.save(update_fields=['category'])
                                except Exception:
                                    pass

                            # ── Get / create Episode ──────────────
                            episode, episode_created = Episode.objects.get_or_create(
                                anime=anime,
                                episode_number=episode_number,
                                defaults={
                                    'title': f"Episode {episode_number}",
                                    'episode_id': hash(f"{anime.id}_{episode_number}") % 2147483647,
                                    'session': f"chia_{anime.slug}_ep{episode_number}",
                                    'is_active': True,
                                    'is_completed': True,
                                    'post_url': post_link,
                                    'publish_date': timezone.now(),
                                }
                            )

                            if episode_created:
                                print(f"  🆕 NEW episode: {anime_title} Ep {episode_number}")
                                stats['new_episodes'] += 1
                                _post_anime_to_telegram(anime, episode=episode)
                            else:
                                print(f"  ♻️  Existing episode: {anime_title} Ep {episode_number}")
                                stats['existing_episodes'] += 1

                            # ── Save download links ───────────────
                            if download_links:
                                existing = {dl.url: dl for dl in episode.download_links.all()}
                                added = updated = skipped = 0

                                for ld in download_links:
                                    lurl = ld['url']
                                    if lurl in existing:
                                        ex = existing[lurl]
                                        changed = False
                                        if ex.quality != ld['quality']:
                                            ex.quality = ld['quality']
                                            changed = True
                                        if ex.label != ld['label']:
                                            ex.label = ld['label']
                                            changed = True
                                        if changed:
                                            ex.save()
                                            updated += 1
                                            stats['updated_links'] += 1
                                        else:
                                            skipped += 1
                                            stats['skipped_links'] += 1
                                    else:
                                        DownloadLink.objects.create(
                                            episode=episode,
                                            quality=ld['quality'],
                                            url=lurl,
                                            host_name=self.get_host_name(lurl),
                                            label=ld['label'],
                                            is_active=True,
                                        )
                                        added += 1
                                        stats['new_links'] += 1

                                print(f"  📊 Links: {added} new | {updated} updated | {skipped} unchanged")

                            # ── Keep total_episodes in sync ───────
                            max_ep = Episode.objects.filter(anime=anime).aggregate(
                                m=models.Max('episode_number')
                            )['m'] or 0
                            if max_ep > (anime.total_episodes or 0):
                                anime.total_episodes = max_ep
                                anime.save(update_fields=['total_episodes'])

                            processed_posts += 1
                            page_processed  += 1

                        except Exception as db_err:
                            print(f"  💥 DB error: {db_err}")
                            self.refresh_db_connection()
                            continue

                        time.sleep(random.uniform(delay_min, delay_max))

                    except Exception as post_err:
                        print(f"  💥 Post error: {post_err}")
                        continue

                # ── Mark page done ────────────────────────────────
                self.mark_page_as_scraped(page)
                print(f"\n✅ Page {page} done — {page_processed}/{len(posts)} posts processed")
                print(f"   📊 Total so far: {processed_posts} posts | {skipped_pages} pages skipped")
                if total_posts:
                    print(f"   🎯 Progress: {processed_posts/total_posts*100:.1f}%")

                page += 1
                time.sleep(random.uniform(delay_min * 1.5, delay_max * 1.5))

            except requests.exceptions.HTTPError as http_err:
                code = http_err.response.status_code if http_err.response else 0
                if code == 404:
                    print("✅ 404 — end of pages")
                    break
                elif code == 429:
                    wait = 60
                    print(f"⚠️ Rate limited — waiting {wait}s…")
                    time.sleep(wait)
                    continue
                else:
                    print(f"🔥 HTTP error {code}: {http_err}")
                    consecutive_empty += 1
                    if consecutive_empty >= MAX_EMPTY:
                        break
                    page += 1
                    continue

            except Exception as err:
                print(f"🔥 Unexpected error: {err}")
                consecutive_empty += 1
                if consecutive_empty >= MAX_EMPTY:
                    break
                page += 1
                continue

        # ── Final save & summary ─────────────────────────────────
        self.save_scraped_pages()
        self.refresh_db_connection()

        try:
            total_animes   = Anime.objects.count()
            total_episodes = Episode.objects.count()
            total_links    = DownloadLink.objects.count()
        except Exception:
            total_animes = total_episodes = total_links = "N/A"

        print("\n" + "═" * 55)
        print("🎉  SCRAPING COMPLETE")
        print("═" * 55)
        print(f"  Posts processed          : {processed_posts}")
        print(f"  Pages scraped this run   : {page - start_page - skipped_pages}")
        print(f"  Pages skipped (cached)   : {skipped_pages}")
        print(f"  Total cached pages       : {len(self.scraped_pages)}")
        print("─" * 55)
        print(f"  New animes               : {stats['new_animes']}")
        print(f"  Existing animes          : {stats['existing_animes']}")
        print(f"  Total animes in DB       : {total_animes}")
        print("─" * 55)
        print(f"  New episodes             : {stats['new_episodes']}")
        print(f"  Existing episodes        : {stats['existing_episodes']}")
        print(f"  No-link episodes skipped : {stats['no_links_skipped']}")
        print(f"  Total episodes in DB     : {total_episodes}")
        print("─" * 55)
        print(f"  New links                : {stats['new_links']}")
        print(f"  Updated links            : {stats['updated_links']}")
        print(f"  Unchanged links          : {stats['skipped_links']}")
        print(f"  Total links in DB        : {total_links}")
        print("═" * 55)
        print("💡 Tips:")
        print("   --debug-html       Save episode HTML for inspection")
        print("   --force-rescrape   Re-scrape cached pages")
        print("   --clear-cache      Start completely fresh")
        print("   --skip-no-links    Skip episodes with no embed links")