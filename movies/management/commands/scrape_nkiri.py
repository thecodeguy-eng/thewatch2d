from django.core.management.base import BaseCommand
from django.utils import timezone
from movies.models import Movie, Category, DownloadLink
import requests
from bs4 import BeautifulSoup
import re
import cloudscraper 
from urllib.parse import urlparse, unquote

API_URL = 'https://nkiri.co.za/wp-json/wp/v2/posts/'

KNOWN_DOWNLOAD_DOMAINS = [
    'dl.downloadwella.com.ng', 'archive.org', 'mega.nz', 'drive.google.com',
    'mediafire.com', 'pixeldrain.com', 'terabox.com', 'onedrive.live.com',
    'downloadwella.com', 'netnaijafiles.xyz', 'loadedfiles.org',
    'sabishares.com', 'meetdownload.com', 'webloaded.com.ng'
]

FILE_EXTENSIONS = ['.mp4', '.mkv', '.zip', '.rar', '.srt']


def normalize_url(url):
    parsed = urlparse(url)
    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return unquote(clean_url).lower()
import ssl
import urllib3

# Add this at the top of your file to suppress warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extract_real_download_link(url):
    print(f"🔍 Extracting real link from: {url}")
    try:
        if 'downloadwella.com' in url:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://nkiri.co.za/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }

            # Try with cloudscraper first (with SSL verification)
            try:
                scraper = cloudscraper.create_scraper()
                res = scraper.get(url, headers=headers, timeout=15)
                res.raise_for_status()
            except requests.exceptions.SSLError as ssl_err:
                print(f"⚠️ SSL verification failed with cloudscraper")
                print("🔄 Retrying with regular requests (no SSL verification)...")
                # Fall back to regular requests without SSL verification
                res = requests.get(url, headers=headers, timeout=15, verify=False)
                res.raise_for_status()

            soup = BeautifulSoup(res.text, 'html.parser')
            
            page_title = soup.find('title')
            if page_title:
                print(f"📄 Page title: {page_title.get_text()}")
            
            bdpg_button = soup.find('a', class_='bdpg-button')
            if bdpg_button and bdpg_button.get('href'):
                real_url = bdpg_button.get('href').split('?')[0]
                print(f"✅ Real link found with bdpg-button: {real_url}")
                return real_url
            
            download_selectors = [
                {'class_': 'bdpg-button'},
                {'id': 'download_link'},
                {'class_': 'download-btn'},
                {'class_': 'btn-download'},
                {'class_': 'download_button'},
                {'class_': 'button'},
                {'class_': 'btn'},
            ]
            
            for selector in download_selectors:
                tag = soup.find('a', selector)
                if tag and tag.get('href'):
                    real_url = tag.get('href', '').split('?')[0]
                    print(f"✅ Real link found with selector {selector}: {real_url}")
                    return real_url
            
            all_links = soup.find_all('a', href=True)
            print(f"🔍 Found {len(all_links)} total links on page")
            
            for link in all_links:
                href = link.get('href', '')
                text = link.get_text().strip().lower()
                
                # Look for direct file links
                if 'downloadwella.com.ng' in href and ('.mkv' in href or '.mp4' in href or '.zip' in href):
                    print(f"🎯 Direct download link found: {text} -> {href}")
                    return href.split('?')[0]
                
                # Look for external hosting services
                if any(domain in href.lower() for domain in [
                    'mega.nz', 'mediafire.com', 'drive.google.com', 
                    'archive.org', 'pixeldrain.com', 'terabox.com'
                ]):
                    print(f"🎯 External download link: {text} -> {href}")
                    return href.split('?')[0]
            
            # Last resort: look for any button/link with "download" text that has a proper URL
            for link in all_links:
                href = link.get('href', '')
                text = link.get_text().strip().lower()
                parent_classes = ' '.join(link.parent.get('class', [])) if link.parent else ''
                
                # Must have "download" in text or parent element, and must be a real URL (not just homepage)
                if 'download' in text or 'download' in parent_classes:
                    # Make sure it's not just the homepage
                    if href and href not in ['https://downloadwella.com', 'https://downloadwella.com/', 'http://downloadwella.com', 'http://downloadwella.com/']:
                        # Check if it looks like a file path (has multiple path segments)
                        if href.count('/') > 3:  # e.g., https://downloadwella.com/path/to/file
                            print(f"🎯 Download button link: {text} -> {href}")
                            return href.split('?')[0]
            
            print("⚠️ No download link found with any method.")
    
    except requests.exceptions.SSLError as ssl_err:
        print(f"⚠️ SSL Error (unrecoverable): {ssl_err}")
        print("💡 Tip: The site may have certificate issues. Returning original URL.")
        return url
            
    except Exception as e:
        print(f"⚠️ Error extracting download link: {e}")
        import traceback
        print(f"🐛 Full traceback: {traceback.format_exc()}")
    
    return url

def extract_real_download_link_with_retry(url, max_retries=3):
    import time
    
    for attempt in range(max_retries):
        if attempt > 0:
            print(f"🔄 Retry attempt {attempt + 1}/{max_retries}")
            time.sleep(2)
        
        result = extract_real_download_link(url)
        if result != url:
            return result
    
    print(f"❌ Failed to extract download link after {max_retries} attempts")
    return url

def get_base_title_for_matching(title):
    base_title = re.sub(r'\s*\((complete|completed)\)\s*$', '', title, flags=re.IGNORECASE).strip()
    return base_title

def find_existing_movie(title, is_complete, max_retries=3):
    from django.db import connection
    import time
    
    base_title = get_base_title_for_matching(title)
    
    search_variants = [
        title,
        base_title,
        f"{base_title} (Complete)",
        f"{base_title} (Completed)",
    ]
    
    search_variants = list(dict.fromkeys(search_variants))
    
    print(f"🔍 Searching for existing movie with variants: {search_variants}")
    
    for attempt in range(max_retries):
        try:
            movie = Movie.objects.filter(title__in=search_variants).first()
            
            if movie:
                print(f"✅ Found existing movie: '{movie.title}' (completed: {movie.completed})")
            else:
                print(f"❌ No existing movie found for: '{title}'")
            
            return movie
            
        except Exception as e:
            print(f"⚠️ Database error on attempt {attempt + 1}/{max_retries}: {e}")
            
            if attempt < max_retries - 1:
                connection.close()
                wait_time = 2 ** attempt
                print(f"🔄 Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"❌ Failed to query database after {max_retries} attempts")
                raise
    
    return None
    
class Command(BaseCommand):
    help = 'Scrape movie data from nkiri.co.za and update database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--startpage',
            type=int,
            default=1,
            help='Page number to start scraping from (default: 1)'
        )
        parser.add_argument(
            '--endpage',
            type=int,
            default=None,
            help='Page number to end scraping at (optional, scrapes all pages if not specified)'
        )
        parser.add_argument(
            '--max-pages',
            type=int,
            default=None,
            help='Maximum number of pages to scrape (optional)'
        )

    def clean_title_parts(self, title):
        title = re.sub(r'\s+', ' ', title).strip()
        title_lower = title.lower()
        is_complete = 'complete' in title_lower or 'completed' in title_lower

        series_pattern = re.compile(r'(?i)(.*?\b(S\d{1,2}|Season\s?\d{1,2}))[\s\-–|:]*\s*(.*)')
        match = series_pattern.match(title)
        if match:
            base_title = match.group(1).strip()
            title_b = match.group(3).strip()

            if is_complete and '(complete' not in base_title.lower():
                base_title += ' (Completed)' if 'completed' in title_lower else ' (Complete)'
            return base_title, title_b

        movie_year_match = re.search(r'^(.*?\(\d{4}\))', title)
        if movie_year_match:
            base_title = movie_year_match.group(1).strip()
            return base_title, ''

        return title, ''

    def handle(self, *args, **options):
        from django.db import connection
        import time
        
        start_page = options['startpage']
        end_page = options['endpage']
        max_pages = options['max_pages']
        
        page = start_page
        pages_scraped = 0
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        print(f"🚀 Starting scrape from page {start_page}")
        if end_page:
            print(f"📄 Will stop at page {end_page}")
        if max_pages:
            print(f"📊 Will scrape maximum {max_pages} pages")
        
        while True:
            # Check if we should stop based on end_page
            if end_page and page > end_page:
                print(f"✅ Reached end page {end_page}. Stopping.")
                break
            
            # Check if we should stop based on max_pages
            if max_pages and pages_scraped >= max_pages:
                print(f"✅ Scraped {max_pages} pages. Stopping.")
                break
            
            try:
                print(f"\n🌐 Fetching page {page}...")
                scraper = cloudscraper.create_scraper()
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                }

                response = scraper.get(API_URL, params={'page': page}, headers=headers, timeout=10)
                
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.HTTPError as http_err:
                if response.status_code == 404:
                    print("✅ All pages processed (404 received).")
                    break
                print(f"🔥 HTTP error: {http_err}")
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print(f"❌ Too many consecutive errors ({consecutive_errors}). Stopping.")
                    return
                time.sleep(5)
                continue
            except Exception as e:
                print(f"🔥 Request failed: {e}")
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print(f"❌ Too many consecutive errors ({consecutive_errors}). Stopping.")
                    return
                connection.close()
                time.sleep(5)
                continue

            consecutive_errors = 0
            pages_scraped += 1

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

                image_url = ''
                media_id = item.get('featured_media')
                if media_id:
                    try:
                        img_res = scraper.get(f"https://nkiri.co.za/wp-json/wp/v2/media/{media_id}", headers=headers)
                        img_res.raise_for_status()
                        image_url = img_res.json().get('source_url', '')
                        print(f"🖼️ Image: {image_url}")
                    except:
                        print("⚠️ Failed to get image")

                try:
                    movie = find_existing_movie(title, is_complete)
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
                        print(f"✏️ Updating existing movie: {movie.title}")
                        
                        if movie.title != title:
                            print(f"📝 Updating title from '{movie.title}' to '{title}'")
                            movie.title = title
                            updated = True
                        
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
                            print(f"🏁 Updating completion status from {movie.completed} to {is_complete}")
                            movie.completed = is_complete
                            updated = True
                            
                        if updated:
                            movie.save()
                            print("🔄 Updated movie info.")

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

                    for cat_id in item.get('categories', []):
                        try:
                            r = scraper.get(f"https://nkiri.co.za/wp-json/wp/v2/categories/{cat_id}", headers=headers)
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
                        
                except Exception as db_error:
                    print(f"💥 Database error processing '{title}': {db_error}")
                    print("🔄 Closing database connection and continuing...")
                    from django.db import connection
                    connection.close()
                    continue

            page += 1
        
        print(f"\n🎉 Scraping complete! Processed {pages_scraped} pages (from page {start_page} to page {page-1})")