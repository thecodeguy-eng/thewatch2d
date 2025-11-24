from django.core.management.base import BaseCommand
from django.utils import timezone
from movies.models import Movie, Category, DownloadLink
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse, unquote

API_URL = 'http://nkiri.org/wp-json/wp/v2/posts/'

KNOWN_DOWNLOAD_DOMAINS = [
    'dl.downloadwella.com.ng', 'archive.org', 'mega.nz', 'drive.google.com',
    'mediafire.com', 'pixeldrain.com', 'terabox.com', 'onedrive.live.com',
    'downloadwella.com', 'netnaijafiles.xyz', 'loadedfiles.org',
    'sabishares.com', 'meetdownload.com'
]

FILE_EXTENSIONS = ['.mp4', '.mkv', '.zip', '.rar', '.srt']


def normalize_url(url):
    parsed = urlparse(url)
    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return unquote(clean_url).lower()


def extract_real_download_link(url):
    print(f"🔍 Extracting real link from: {url}")
    try:
        if 'downloadwella.com' in url:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'html.parser')
            tag = soup.find('a', {'id': 'download_link'})
            if tag:
                real_url = tag.get('href', '').split('?')[0]
                print(f"✅ Real link found: {real_url}")
                return real_url
            print("⚠️ No real link found in DOM.")
    except Exception as e:
        print(f"⚠️ Error: {e}")
    return url


class Command(BaseCommand):
    help = 'Scrape movie data from nkiri.org and update database'

    def clean_title_parts(self, title):
        title = re.sub(r'\s+', ' ', title).strip()
        title_lower = title.lower()
        is_complete = 'complete' in title_lower or 'completed' in title_lower

        # SERIES (e.g. “Something S01 Episode 12 | Korean Drama”)
        series_pattern = re.compile(r'(?i)(.*?\b(S\d{1,2}|Season\s?\d{1,2}))[\s\-–|:]*\s*(.*)')
        match = series_pattern.match(title)
        if match:
            base_title = match.group(1).strip()
            title_b = match.group(3).strip()

            # Add (Completed) to title if complete
            if is_complete and '(complete' not in base_title.lower():
                base_title += ' (Completed)' if 'completed' in title_lower else ' (Complete)'
            return base_title, title_b

        # MOVIE (e.g. “Karate Kid Legends (2025) | Hollywood Movie”)
        movie_year_match = re.search(r'^(.*?\(\d{4}\))', title)
        if movie_year_match:
            base_title = movie_year_match.group(1).strip()
            return base_title, ''  # No title_b for movies

        return title, ''

    def handle(self, *args, **options):
        page = 1
        while True:
            try:
                print(f"\n🌐 Fetching page {page}...")
                response = requests.get(API_URL, params={'page': page}, timeout=10)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.HTTPError as http_err:
                if response.status_code == 404:
                    print("✅ All pages processed.")
                    break
                print(f"🔥 HTTP error: {http_err}")
                return
            except Exception as e:
                print(f"🔥 Request failed: {e}")
                return

            if not data:
                print("✅ No data returned. Finished.")
                break

            for item in data:
                raw_title = item.get('title', {}).get('rendered', '').strip()
                if not raw_title:
                    print("⚠️ Skipped: empty title.")
                    continue

                print(f"\n🎬 Processing: {raw_title}")
                title, title_b = self.clean_title_parts(raw_title)
                is_complete = bool(re.search(r'\bcomplete(d)?\b', raw_title, re.IGNORECASE))

                description = BeautifulSoup(item.get('excerpt', {}).get('rendered', ''), 'html.parser').get_text()
                soup = BeautifulSoup(item.get('content', {}).get('rendered', ''), 'html.parser')

                # Video
                video_url = ''
                iframe = soup.find('iframe')
                if iframe and iframe.get('src'):
                    video_url = iframe['src']
                else:
                    video = soup.find('video')
                    if video:
                        src = video.find('source')
                        if src and src.get('src'):
                            video_url = src['src']
                if video_url:
                    print(f"🎥 Video URL: {video_url}")

                # Download links
                download_links = []
                print("🔗 Looking for download links...")
                for a in soup.find_all('a', href=True):
                    href = a['href'].strip()
                    label = ' '.join(a.stripped_strings).strip()
                    href_lower = href.lower()

                    if any(domain in href_lower for domain in KNOWN_DOWNLOAD_DOMAINS) or \
                       any(href_lower.endswith(ext) for ext in FILE_EXTENSIONS) or \
                       'dl' in href_lower or 'dl' in label.lower():
                        print(f"🔍 Found: {label} -> {href}")
                        real = extract_real_download_link(href)
                        download_links.append({'url': real, 'label': label})

                if not download_links:
                    print(f"⛔ No valid links for: {title}")
                    continue

                # Image
                image_url = ''
                media_id = item.get('featured_media')
                if media_id:
                    try:
                        img_res = requests.get(f"http://nkiri.org/wp-json/wp/v2/media/{media_id}")
                        img_res.raise_for_status()
                        image_url = img_res.json().get('source_url', '')
                        print(f"🖼️ Image: {image_url}")
                    except:
                        print("⚠️ Failed to get image")

                # Create or update
                variants = [title, f"{title} (Complete)", f"{title} (Completed)"]
                movie = Movie.objects.filter(title__in=variants).first()
                created = False

                if not movie:
                    movie = Movie.objects.create(
                        title=title,
                        title_b=title_b,
                        title_b_updated_at=timezone.now() if title_b else None,
                        description=description,
                        video_url=video_url,
                        download_url=download_links[0]['url'],
                        image_url=image_url,
                        completed=is_complete,
                        scraped=True
                    )
                    created = True
                    print(f"✅ Created new movie: {title}")
                else:
                    updated = False
                    print(f"✏️ Updating movie: {movie.title}")
                    if title_b and movie.title_b != title_b:
                        movie.title_b = title_b
                        movie.title_b_updated_at = timezone.now()
                        updated = True
                    if not movie.video_url and video_url:
                        movie.video_url = video_url
                        updated = True
                    if not movie.image_url and image_url:
                        movie.image_url = image_url
                        updated = True

                    if movie.download_url and normalize_url(movie.download_url) != normalize_url(download_links[0]['url']):
                        print("🔁 Updating main download_url...")
                        movie.download_url = download_links[0]['url']
                        updated = True

                    if movie.completed != is_complete:
                        movie.completed = is_complete
                        updated = True
                    if updated:
                        movie.save()
                        print("🔄 Updated movie info.")

                # Sync download links
                added, updated_labels, deleted = 0, 0, 0
                existing_links = {normalize_url(dl.url): dl for dl in movie.download_links.all()}
                current_links = {normalize_url(dl['url']): dl for dl in download_links}

                for norm_url, dl in current_links.items():
                    if norm_url in existing_links:
                        existing_dl = existing_links[norm_url]
                        if existing_dl.label != dl['label']:
                            existing_dl.label = dl['label']
                            existing_dl.save()
                            updated_labels += 1
                    else:
                        DownloadLink.objects.create(movie=movie, label=dl['label'], url=dl['url'])
                        added += 1

                for norm_url in set(existing_links.keys()) - set(current_links.keys()):
                    existing_links[norm_url].delete()
                    deleted += 1

                print(f"➕ {added} new link(s) added.")
                if updated_labels:
                    print(f"✏️ {updated_labels} label(s) updated.")
                if deleted:
                    print(f"🗑️ {deleted} outdated link(s) deleted.")

                # Categories
                for cat_id in item.get('categories', []):
                    try:
                        r = requests.get(f"http://nkiri.org/wp-json/wp/v2/categories/{cat_id}")
                        r.raise_for_status()
                        cat_name = r.json().get('name')
                        if cat_name:
                            cat_obj, _ = Category.objects.get_or_create(name=cat_name.capitalize())
                            movie.categories.add(cat_obj)
                            print(f"📁 Category added: {cat_name}")
                    except:
                        print("⚠️ Category fetch failed.")

                if not created and added == 0 and updated_labels == 0 and deleted == 0:
                    print("ℹ️ No updates.")

            page += 1
