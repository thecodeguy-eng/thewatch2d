from django.core.management.base import BaseCommand
from django.utils import timezone
from movies.models import Movie, Category, DownloadLink
import requests
from bs4 import BeautifulSoup
import re
import cloudscraper 
from urllib.parse import urlparse, unquote
import time

API_URL = 'https://mylulutv.com/wp-json/wp/v2/posts/'
PAGES_API_URL = 'https://mylulutv.com/wp-json/wp/v2/pages/'

KNOWN_DOWNLOAD_DOMAINS = [
    'dl.downloadwella.com.ng', 'archive.org', 'mega.nz', 'drive.google.com',
    'mediafire.com', 'pixeldrain.com', 'terabox.com', 'onedrive.live.com',
    'downloadwella.com', 'netnaijafiles.xyz', 'loadedfiles.org',
    'sabishares.com', 'meetdownload.com', 'webloaded.com.ng', 'dtagger.downloadwella.com.ng',
    'cdn.wakacloud.com'
]

FILE_EXTENSIONS = ['.mp4', '.mkv', '.zip', '.rar', '.srt']


def normalize_url(url):
    """Normalize URL for comparison by removing query params and lowercasing"""
    parsed = urlparse(url)
    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return unquote(clean_url).lower()


def extract_download_links_from_html(html_content):
    """Extract download links from HTML content"""
    print(f"🔍 Analyzing HTML content for download links...")
    links = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Method 1: Look for direct links with class="download" (primary class for episodes)
    download_links = soup.find_all('a', class_='download')
    if download_links:
        for link in download_links:
            href = link.get('href', '').strip()
            label_elem = link.find('strong')
            label = label_elem.get_text(strip=True) if label_elem else link.get_text(strip=True)
            
            if href and href not in ['#', '']:
                if href.startswith('http') or href.startswith('https'):
                    clean_url = href.split('?')[0]
                    print(f"✅ Found download link: {label} -> {clean_url}")
                    links.append({'url': clean_url, 'label': label})
    
    # Method 2: Look for download-btn class
    download_btn_links = soup.find_all('a', class_='download-btn')
    if download_btn_links:
        for link in download_btn_links:
            href = link.get('href', '').strip()
            label = link.get_text(strip=True)
            if href and href not in ['#', '']:
                if href.startswith('http') or href.startswith('https'):
                    clean_url = href.split('?')[0]
                    print(f"✅ Found download-btn link: {label} -> {clean_url}")
                    links.append({'url': clean_url, 'label': label})
    
    # Method 3: Look for button class links
    button_links = soup.find_all('a', class_='button')
    if button_links:
        for link in button_links:
            href = link.get('href', '').strip()
            label_elem = link.find('strong')
            label = label_elem.get_text(strip=True) if label_elem else link.get_text(strip=True)
            
            if href and href not in ['#', '']:
                if href.startswith('http') or href.startswith('https'):
                    clean_url = href.split('?')[0]
                    print(f"✅ Found button link: {label} -> {clean_url}")
                    links.append({'url': clean_url, 'label': label})
    
    # Method 4: Look for links with file extensions
    all_links = soup.find_all('a', href=True)
    for link in all_links:
        href = link.get('href', '').strip()
        text = link.get_text(strip=True).lower()
        
        if not href or href in ['#', '/', 'javascript:void(0)']:
            continue
        
        href_lower = href.lower()
        if any(normalize_url(href) == normalize_url(l['url']) for l in links):
            continue
        
        if any(domain in href_lower for domain in KNOWN_DOWNLOAD_DOMAINS):
            if any(ext in href_lower for ext in FILE_EXTENSIONS) or 'episode' in text or 'download' in text:
                clean_url = href.split('?')[0]
                print(f"✅ Found external link: {text} -> {clean_url}")
                links.append({'url': clean_url, 'label': text or 'Download'})
    
    # Remove duplicates
    seen = {}
    unique_links = []
    for link in links:
        norm_url = normalize_url(link['url'])
        if norm_url not in seen:
            seen[norm_url] = True
            unique_links.append(link)
    
    if not unique_links:
        print(f"⚠️ No download links found in HTML content")
    else:
        print(f"✅ Found {len(unique_links)} unique download link(s)")
    
    return unique_links


def get_base_title_for_matching(title):
    """Get base title without (Complete) suffix for matching"""
    base_title = re.sub(r'\s*\((complete|completed)\)\s*$', '', title, flags=re.IGNORECASE).strip()
    return base_title


def find_existing_movie(title, is_complete, max_retries=3):
    """Find existing movie in database with retry logic"""
    from django.db import connection
    
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
    help = 'Scrape movie data from mylulutv.com and update database'

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
        parser.add_argument(
            '--posts-only',
            action='store_true',
            help='Only scrape posts, skip pages'
        )
        parser.add_argument(
            '--pages-only',
            action='store_true',
            help='Only scrape pages, skip posts'
        )

    def clean_title_parts(self, title):
        """Clean and split title into base title and subtitle"""
        title = re.sub(r'\s+', ' ', title).strip()
        title_lower = title.lower()
        is_complete = 'complete' in title_lower or 'completed' in title_lower

        # Handle series with season/episode info
        series_pattern = re.compile(r'(?i)(.*?)[\s\-–|:]*\s*(S\d{1,2}|Season\s?\d{1,2})[\s\-–|:]*\s*(.*)')
        match = series_pattern.match(title)
        if match:
            base_title = match.group(1).strip()
            season_part = match.group(2).strip()
            title_b = match.group(3).strip()
            
            base_title = f"{base_title} {season_part}"

            if is_complete and '(complete' not in base_title.lower():
                base_title += ' (Completed)' if 'completed' in title_lower else ' (Complete)'
            return base_title, title_b

        # Handle movies with year
        movie_year_match = re.search(r'^(.*?\(\d{4}\))', title)
        if movie_year_match:
            base_title = movie_year_match.group(1).strip()
            return base_title, ''

        return title, ''

    def scrape_endpoint(self, api_url, endpoint_name, start_page, end_page, max_pages, scraper, headers):
        """Scrape a specific WordPress endpoint (posts or pages)"""
        from django.db import connection
        
        page = start_page
        pages_scraped = 0
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        print(f"\n{'='*50}")
        print(f"🚀 Scraping {endpoint_name} from page {start_page}")
        if end_page:
            print(f"📄 Will stop at page {end_page}")
        if max_pages:
            print(f"📊 Will scrape maximum {max_pages} pages")
        print(f"{'='*50}\n")
        
        while True:
            if end_page and page > end_page:
                print(f"✅ Reached end page {end_page}. Stopping.")
                break
            
            if max_pages and pages_scraped >= max_pages:
                print(f"✅ Scraped {max_pages} pages. Stopping.")
                break
            
            try:
                print(f"\n🌐 Fetching {endpoint_name} page {page}...")
                response = scraper.get(api_url, params={'page': page, 'per_page': 100}, headers=headers, timeout=10)
                
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.HTTPError as http_err:
                if response.status_code == 404:
                    print(f"✅ All {endpoint_name} pages processed (404 received).")
                    break
                print(f"🔥 HTTP error: {http_err}")
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print(f"❌ Too many consecutive errors ({consecutive_errors}). Stopping.")
                    return pages_scraped
                time.sleep(5)
                continue
            except Exception as e:
                print(f"🔥 Request failed: {e}")
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print(f"❌ Too many consecutive errors ({consecutive_errors}). Stopping.")
                    return pages_scraped
                connection.close()
                time.sleep(5)
                continue

            consecutive_errors = 0
            pages_scraped += 1

            if not data:
                print(f"✅ No data returned for {endpoint_name}. Finished.")
                break

            print(f"📦 Found {len(data)} items on page {page}")

            for item in data:
                raw_title = item.get('title', {}).get('rendered', '').strip()
                if not raw_title:
                    print("⚠️ Skipped: empty title.")
                    continue

                print(f"\n🎬 Processing: {raw_title}")
                
                # Detect if this is a series based on title or content
                is_series_post = any(keyword in raw_title.lower() for keyword in ['drama', 'series', 'season', 's01', 's02'])
                
                title, title_b = self.clean_title_parts(raw_title)
                is_complete = bool(re.search(r'\bcomplete(d)?\b', raw_title, re.IGNORECASE))

                description = BeautifulSoup(item.get('excerpt', {}).get('rendered', ''), 'html.parser').get_text()
                soup = BeautifulSoup(item.get('content', {}).get('rendered', ''), 'html.parser')

                # Extract video URL
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

                # Extract download links
                content_html = item.get('content', {}).get('rendered', '')
                download_links = extract_download_links_from_html(content_html)

                # If no download links, check for season/episode pages
                if not download_links:
                    print(f"🔍 No direct download links. Checking for season/episode pages...")
                    content_soup = BeautifulSoup(content_html, 'html.parser')
                    
                    season_links = []
                    for link in content_soup.find_all('a', href=True):
                        href = link.get('href', '').strip()
                        text = link.get_text(strip=True).lower()
                        
                        if any(keyword in text for keyword in ['season', 'episode', 'view full series', 's01', 's02', 's03', 'ep']):
                            if 'mylulutv.com' in href and href not in ['#', '/']:
                                season_links.append({'url': href, 'text': text})
                                print(f"🔗 Found season link: {text} -> {href}")
                    
                    if season_links:
                        print(f"📺 Found {len(season_links)} season/episode page(s). Fetching download links...")
                        for season_link in season_links:
                            try:
                                print(f"🌐 Fetching season page: {season_link['url']}")
                                season_response = scraper.get(season_link['url'], headers=headers, timeout=15)
                                season_response.raise_for_status()
                                season_soup = BeautifulSoup(season_response.text, 'html.parser')
                                
                                content_area = season_soup.find('div', class_='entry-content') or season_soup.find('article')
                                if content_area:
                                    season_html = str(content_area)
                                    season_downloads = extract_download_links_from_html(season_html)
                                    if season_downloads:
                                        download_links.extend(season_downloads)
                                        print(f"✅ Extracted {len(season_downloads)} link(s) from {season_link['text']}")
                                else:
                                    print(f"⚠️ Could not find content area in {season_link['url']}")
                                    
                            except Exception as e:
                                print(f"⚠️ Failed to fetch season page {season_link['url']}: {e}")
                                continue
                
                if not download_links:
                    print(f"⛔ No valid links found for: {title}")
                    continue

                # Extract featured image
                image_url = ''
                media_id = item.get('featured_media')
                if media_id:
                    try:
                        img_res = scraper.get(f"https://mylulutv.com/wp-json/wp/v2/media/{media_id}", headers=headers, timeout=10)
                        img_res.raise_for_status()
                        image_url = img_res.json().get('source_url', '')
                        print(f"🖼️ Image: {image_url}")
                    except Exception as e:
                        print(f"⚠️ Failed to get image: {e}")

                try:
                    movie = find_existing_movie(title, is_complete)
                    created = False
                    
                    # Determine if this should be treated as a series with episodes
                    has_multiple_episodes = len(download_links) > 1
                    episode_labels = [link['label'] for link in download_links if 'episode' in link['label'].lower() or 'ep' in link['label'].lower()]
                    
                    # Generate title_b for series with episodes
                    series_title_b = ''
                    if has_multiple_episodes and episode_labels:
                        # Create a summary of episodes
                        if len(episode_labels) <= 3:
                            series_title_b = ', '.join(episode_labels)
                        else:
                            series_title_b = f"{episode_labels[0]} - {episode_labels[-1]} ({len(episode_labels)} episodes)"
                        print(f"📺 Series detected with episodes: {series_title_b}")

                    if not movie:
                        movie = Movie.objects.create(
                            title=title,
                            title_b=series_title_b or title_b,
                            title_b_updated_at=timezone.now() if series_title_b or title_b else None,
                            description=description,
                            video_url=video_url,
                            download_url=download_links[0]['url'],
                            image_url=image_url,
                            completed=is_complete,
                            is_series=has_multiple_episodes,
                            scraped=True
                        )
                        created = True
                        print(f"✅ Created new {'series' if has_multiple_episodes else 'movie'}: {title}")
                    else:
                        updated = False
                        print(f"✏️ Updating existing movie: {movie.title}")
                        
                        if movie.title != title:
                            print(f"📝 Updating title from '{movie.title}' to '{title}'")
                            movie.title = title
                            updated = True
                        
                        # Update title_b with episode info if this is a series
                        if series_title_b:
                            if movie.title_b != series_title_b:
                                print(f"📺 Updating episodes: {series_title_b}")
                                movie.title_b = series_title_b
                                movie.title_b_updated_at = timezone.now()
                                movie.is_series = True
                                updated = True
                        elif title_b and movie.title_b != title_b:
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

                    # Update download links
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

                    if added:
                        print(f"➕ {added} new link(s) added.")
                    if updated_labels:
                        print(f"✏️ {updated_labels} label(s) updated.")
                    if deleted:
                        print(f"🗑️ {deleted} outdated link(s) deleted.")

                    # Update categories
                    for cat_id in item.get('categories', []):
                        try:
                            r = scraper.get(f"https://mylulutv.com/wp-json/wp/v2/categories/{cat_id}", headers=headers, timeout=10)
                            r.raise_for_status()
                            cat_name = r.json().get('name')
                            if cat_name:
                                cat_obj, _ = Category.objects.get_or_create(name=cat_name.capitalize())
                                movie.categories.add(cat_obj)
                                print(f"📁 Category added: {cat_name}")
                        except Exception as e:
                            print(f"⚠️ Category fetch failed: {e}")

                    if not created and added == 0 and updated_labels == 0 and deleted == 0:
                        print("ℹ️ No updates.")
                        
                except Exception as db_error:
                    print(f"💥 Database error processing '{title}': {db_error}")
                    print("🔄 Closing database connection and continuing...")
                    connection.close()
                    continue

            page += 1
        
        print(f"\n✅ {endpoint_name} scraping complete! Processed {pages_scraped} pages (from page {start_page} to page {page-1})")
        return pages_scraped

    def handle(self, *args, **options):
        start_page = options['startpage']
        end_page = options['endpage']
        max_pages = options['max_pages']
        posts_only = options['posts_only']
        pages_only = options['pages_only']
        
        scraper = cloudscraper.create_scraper()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        
        total_pages = 0
        posts_scraped = 0
        pages_scraped_count = 0
        
        # Scrape posts
        if not pages_only:
            print("\n" + "="*60)
            print("📰 SCRAPING POSTS")
            print("="*60)
            posts_scraped = self.scrape_endpoint(
                API_URL, 
                "posts", 
                start_page, 
                end_page, 
                max_pages, 
                scraper, 
                headers
            )
            total_pages += posts_scraped
        
        # Scrape pages
        if not posts_only:
            print("\n" + "="*60)
            print("📄 SCRAPING PAGES (Series/Episodes)")
            print("="*60)
            pages_scraped_count = self.scrape_endpoint(
                PAGES_API_URL, 
                "pages", 
                start_page, 
                end_page, 
                max_pages, 
                scraper, 
                headers
            )
            total_pages += pages_scraped_count
        
        print(f"\n{'='*60}")
        print(f"🎉 ALL SCRAPING COMPLETE!")
        print(f"📊 Total pages processed: {total_pages}")
        if not pages_only:
            print(f"   - Posts: {posts_scraped}")
        if not posts_only:
            print(f"   - Pages: {pages_scraped_count}")
        print(f"{'='*60}")