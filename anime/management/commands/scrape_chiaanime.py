from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
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

API_URL = 'https://chia-anime.su/wp-json/wp/v2/posts/'

class Command(BaseCommand):
    help = 'Scrape ALL anime data from chia-anime.su and update database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-pages',
            type=int,
            default=None,
            help='Maximum number of pages to scrape (default: unlimited)'
        )
        parser.add_argument(
            '--start-page',
            type=int,
            default=1,
            help='Page number to start scraping from (default: 1)'
        )
        parser.add_argument(
            '--per-page',
            type=int,
            default=20,
            help='Number of posts per page (default: 20, max: 100)'
        )
        parser.add_argument(
            '--delay-min',
            type=float,
            default=2.0,
            help='Minimum delay between requests in seconds (default: 2.0)'
        )
        parser.add_argument(
            '--delay-max',
            type=float,
            default=4.0,
            help='Maximum delay between requests in seconds (default: 4.0)'
        )

    def clean_title(self, title):
        """Extract anime title and episode info from post title"""
        title = re.sub(r'\s+', ' ', title).strip()
        
        # Remove "English Subbed" from the end
        title = re.sub(r'\s*English Subbed$', '', title, flags=re.IGNORECASE)
        
        # Extract episode number - patterns like "Episode 21", "Episode 7", etc.
        episode_match = re.search(r'Episode (\d+)', title, re.IGNORECASE)
        episode_number = int(episode_match.group(1)) if episode_match else None
        
        # Remove episode part to get anime title
        anime_title = re.sub(r'\s*Episode \d+', '', title, flags=re.IGNORECASE).strip()
        
        return anime_title, episode_number

    def extract_anime_poster(self, post_content, anime_title):
        """Extract anime poster/image from post content or search for it"""
        try:
            # First, try to find image in post content
            if post_content:
                soup = BeautifulSoup(post_content, 'html.parser')
                images = soup.find_all('img')
                
                for img in images:
                    src = img.get('src', '').strip()
                    alt = img.get('alt', '').lower()
                    
                    # Skip common non-poster images
                    if any(skip in src.lower() for skip in ['logo', 'banner', 'ad', 'button']):
                        continue
                        
                    # Look for images that might be posters
                    if src and (anime_title.lower() in alt or 'poster' in alt or 'cover' in alt):
                        return src
                
                # If no specific poster found, return the first decent-sized image
                for img in images:
                    src = img.get('src', '').strip()
                    if src and not any(skip in src.lower() for skip in ['logo', 'banner', 'ad', 'button']):
                        return src
                        
            # Fallback: Try to find poster from anime database APIs (optional)
            # You could integrate with MyAnimeList, AniDB, or other APIs here
            
        except Exception as e:
            print(f"Error extracting poster: {e}")
            
        return None

    def resolve_stream_link(self, fyptt_url):
        """Resolve fypttvideos.xyz links to actual stream URLs"""
        try:
            if 'fypttvideos.xyz' not in fyptt_url:
                return fyptt_url  # Return as-is if not a fyptt link
                
            print(f"  🔄 Resolving stream link: {fyptt_url}")
            
            scraper = cloudscraper.create_scraper()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://chia-anime.su/",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            }
            
            response = scraper.get(fyptt_url, headers=headers, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Method 1: Look for embedded iframe players (most common case)
            iframes = soup.find_all('iframe')
            for iframe in iframes:
                src = iframe.get('src')
                if src:
                    # Clean up the URL
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://fypttvideos.xyz' + src
                    
                    # Check if this is a valid streaming embed
                    embed_domains = ['embedz.net', 'vidstream', 'streamtape', 'mixdrop', 'doodstream']
                    if any(domain in src.lower() for domain in embed_domains):
                        print(f"  ✅ Found embedded player: {src}")
                        return src
                    
                    # If it's still an fyptt iframe, try to resolve it further
                    if 'fypttvideos.xyz' in src and src != fyptt_url:
                        print(f"  🔄 Following iframe redirect: {src}")
                        return self.resolve_stream_link(src)  # Recursive call
            
            # Method 2: Look for direct video sources
            video_tags = soup.find_all('video')
            for video in video_tags:
                sources = video.find_all('source')
                for source in sources:
                    src = source.get('src')
                    if src:
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            src = 'https://fypttvideos.xyz' + src
                        print(f"  ✅ Found direct video source: {src}")
                        return src
            
            # Method 3: Look for JavaScript redirects or embedded URLs
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    js_content = script.string
                    
                    # Look for iframe sources in JavaScript
                    iframe_patterns = [
                        r'iframe.*?src\s*=\s*["\']([^"\']+)["\']',
                        r'src\s*:\s*["\']([^"\']+)["\']',
                        r'["\']https?://[^"\']*(?:embedz\.net|vidstream|streamtape|mixdrop)[^"\']*["\']'
                    ]
                    
                    for pattern in iframe_patterns:
                        matches = re.findall(pattern, js_content, re.IGNORECASE | re.DOTALL)
                        for match in matches:
                            clean_url = match.strip('\'"')
                            if clean_url.startswith('//'):
                                clean_url = 'https:' + clean_url
                            
                            # Check if it's a valid streaming URL
                            if any(domain in clean_url.lower() for domain in ['embedz.net', 'vidstream', 'streamtape', 'mixdrop']):
                                print(f"  🎯 Found stream URL in JavaScript: {clean_url}")
                                return clean_url
                    
                    # Look for direct video URLs
                    video_patterns = [
                        r'["\']https?://[^"\']*\.(?:mp4|m3u8|mkv)[^"\']*["\']',
                        r'source\s*:\s*["\']([^"\']+)["\']',
                        r'file\s*:\s*["\']([^"\']+)["\']'
                    ]
                    
                    for pattern in video_patterns:
                        matches = re.findall(pattern, js_content, re.IGNORECASE)
                        for match in matches:
                            clean_url = match.strip('\'"')
                            if any(ext in clean_url.lower() for ext in ['.mp4', '.m3u8', '.mkv']):
                                if clean_url.startswith('//'):
                                    clean_url = 'https:' + clean_url
                                elif clean_url.startswith('/'):
                                    clean_url = 'https://fypttvideos.xyz' + clean_url
                                print(f"  🎯 Found direct video URL in JavaScript: {clean_url}")
                                return clean_url
            
            # Method 4: Look for meta refresh redirects
            meta_refresh = soup.find('meta', {'http-equiv': 'refresh'})
            if meta_refresh:
                content = meta_refresh.get('content', '')
                url_match = re.search(r'url=([^;]+)', content, re.IGNORECASE)
                if url_match:
                    redirect_url = url_match.group(1)
                    if redirect_url.startswith('/'):
                        redirect_url = 'https://fypttvideos.xyz' + redirect_url
                    print(f"  🔄 Found meta refresh redirect: {redirect_url}")
                    return self.resolve_stream_link(redirect_url)  # Recursive call
            
            # Method 5: Check for location.href redirects in JavaScript
            for script in scripts:
                if script.string:
                    js_content = script.string
                    redirect_patterns = [
                        r'location\.href\s*=\s*["\']([^"\']+)["\']',
                        r'window\.location\s*=\s*["\']([^"\']+)["\']',
                        r'window\.open\s*\(\s*["\']([^"\']+)["\']'
                    ]
                    
                    for pattern in redirect_patterns:
                        matches = re.findall(pattern, js_content, re.IGNORECASE)
                        for match in matches:
                            redirect_url = match.strip()
                            if redirect_url.startswith('/'):
                                redirect_url = 'https://fypttvideos.xyz' + redirect_url
                            elif redirect_url.startswith('//'):
                                redirect_url = 'https:' + redirect_url
                            
                            # Avoid infinite loops
                            if redirect_url != fyptt_url and 'fypttvideos.xyz' in redirect_url:
                                print(f"  🔄 Found JavaScript redirect: {redirect_url}")
                                return self.resolve_stream_link(redirect_url)
                            elif any(domain in redirect_url.lower() for domain in ['embedz.net', 'vidstream', 'streamtape']):
                                print(f"  ✅ Found JavaScript redirect to embed: {redirect_url}")
                                return redirect_url
            
            # Method 6: If we still haven't found anything, check if the current URL is actually an embed
            current_domain = urlparse(fyptt_url).netloc.lower()
            if any(domain in current_domain for domain in ['embedz.net', 'vidstream', 'streamtape', 'mixdrop', 'doodstream']):
                print(f"  ✅ URL is already an embed: {fyptt_url}")
                return fyptt_url
            
            # Method 7: Check response headers for location redirects
            if hasattr(response, 'history') and response.history:
                final_url = response.url
                if final_url != fyptt_url:
                    print(f"  🔄 HTTP redirect detected: {final_url}")
                    if any(domain in final_url.lower() for domain in ['embedz.net', 'vidstream', 'streamtape']):
                        return final_url
                    elif 'fypttvideos.xyz' in final_url:
                        return self.resolve_stream_link(final_url)
            
            print(f"  ❌ Could not resolve stream link for: {fyptt_url}")
            return None
            
        except Exception as e:
            print(f"  ❌ Error resolving stream link {fyptt_url}: {e}")
            return None
        
        finally:
            # Add delay to avoid overwhelming the server
            time.sleep(random.uniform(1, 3))

    def is_valid_streaming_url(self, url):
        """Check if URL is a valid streaming/download link"""
        url_lower = url.lower()
        
        # Exclude common static resources
        excluded_extensions = ['.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.woff2', '.ttf']
        excluded_paths = ['/wp-content/', '/wp-includes/', '/assets/', '/css/', '/js/', '/favicon']
        excluded_domains = ['fonts.googleapis.com', 'gravatar.com']
        
        # Don't exclude chia-anime.su completely as it might have valid episode links
        
        # Check for excluded file extensions
        for ext in excluded_extensions:
            if url_lower.endswith(ext) or f'{ext}?' in url_lower:
                return False
                
        # Check for excluded paths
        for path in excluded_paths:
            if path in url_lower:
                return False
                
        # Check for excluded domains
        for domain in excluded_domains:
            if domain in url_lower:
                return False
        
        # Valid streaming/download domains and patterns
        valid_domains = [
            'fypttvideos.xyz', 'embedz.net', 'vidstream', 'mega.nz', 'mediafire.com', 
            'drive.google.com', 'dropbox.com', 'dailymotion.com', 'streamtape.com', 
            'mixdrop.co', 'doodstream.com', 'streamlare.com', 'filelions.com', 
            'upstream.to', 'rapidvideo', 'mp4upload.com'
        ]
        
        # Check valid domains
        for domain in valid_domains:
            if domain in url_lower:
                return True
        
        # Check if it looks like a video file
        video_extensions = ['.mp4', '.mkv', '.avi', '.m3u8', '.webm']
        for ext in video_extensions:
            if ext in url_lower:
                return True
                
        return False

    def extract_download_links(self, html_content, post_content):
        """Extract and resolve download links from both post content and HTML"""
        links = []
        
        # Parse the full HTML content
        if html_content:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for episodeRepeater section (primary streaming links)
            episode_repeater = soup.find('div', class_='episodeRepeater')
            if episode_repeater:
                print("  🔍 Found episodeRepeater section")
                for a_tag in episode_repeater.find_all('a', href=True):
                    href = a_tag.get('href', '').strip()
                    text = a_tag.get_text().strip()
                    
                    if href and self.is_valid_streaming_url(href):
                        # Resolve fyptt links to actual stream URLs
                        original_href = href
                        if 'fypttvideos.xyz' in href:
                            resolved_url = self.resolve_stream_link(href)
                            if resolved_url and resolved_url != href:
                                href = resolved_url
                                print(f"  ✅ Resolved: {original_href} -> {href}")
                            elif not resolved_url:
                                print(f"  ⚠️ Could not resolve: {original_href}, keeping original")
                                # Keep the original URL as fallback
                        
                        quality = self.extract_quality_from_text(text)
                        
                        links.append({
                            'url': href,
                            'label': text if text else 'Stream Link',
                            'quality': quality
                        })
                        print(f"  🔹 Added stream link: {text} -> {href}")
            
            # Look for other streaming links in specific containers
            streaming_containers = soup.find_all(['div'], class_=['bixbox', 'player-area', 'video-player', 'show_adv_wrap'])
            for container in streaming_containers:
                # Check for iframes in containers (like show_adv_wrap)
                iframes = container.find_all('iframe', src=True)
                for iframe in iframes:
                    src = iframe.get('src', '').strip()
                    if src and self.is_valid_streaming_url(src):
                        if src not in [link['url'] for link in links]:
                            if src.startswith('//'):
                                src = 'https:' + src
                            
                            links.append({
                                'url': src,
                                'label': 'Embedded Player',
                                'quality': '720p'
                            })
                            print(f"  🔹 Found iframe in container: {src}")
                
                # Check for regular links in containers
                for a_tag in container.find_all('a', href=True):
                    href = a_tag.get('href', '').strip()
                    text = a_tag.get_text().strip()
                    
                    if href and self.is_valid_streaming_url(href):
                        if href not in [link['url'] for link in links]:
                            # Resolve fyptt links
                            if 'fypttvideos.xyz' in href:
                                resolved_url = self.resolve_stream_link(href)
                                if resolved_url:
                                    href = resolved_url
                            
                            quality = self.extract_quality_from_text(text)
                            links.append({
                                'url': href,
                                'label': text if text else 'Stream Link',
                                'quality': quality
                            })
                            print(f"  🔹 Found container link: {text} -> {href}")
            
            # Search for all iframes in the page
            all_iframes = soup.find_all('iframe', src=True)
            for iframe in all_iframes:
                src = iframe.get('src', '').strip()
                if src and self.is_valid_streaming_url(src):
                    if src not in [link['url'] for link in links]:
                        if src.startswith('//'):
                            src = 'https:' + src
                        
                        links.append({
                            'url': src,
                            'label': 'Embedded Player',
                            'quality': '720p'
                        })
                        print(f"  🔹 Found general iframe: {src}")
        
        # Also check post content (fallback method)
        if post_content:
            content_soup = BeautifulSoup(post_content, 'html.parser')
            for a_tag in content_soup.find_all('a', href=True):
                href = a_tag.get('href', '').strip()
                text = a_tag.get_text().strip()
                
                if href and self.is_valid_streaming_url(href):
                    if href not in [link['url'] for link in links]:
                        # Resolve fyptt links
                        if 'fypttvideos.xyz' in href:
                            resolved_url = self.resolve_stream_link(href)
                            if resolved_url:
                                href = resolved_url
                        
                        quality = self.extract_quality_from_text(text + ' ' + href)
                        links.append({
                            'url': href,
                            'label': text if text else 'Download Link',
                            'quality': quality
                        })
                        print(f"  💥 Found content link: {text} -> {href}")
        
        return links

    def extract_quality_from_text(self, text):
        """Extract video quality from text"""
        if not text:
            return '720p'
            
        text = text.lower()
        if '1080p' in text or '1080' in text:
            return '1080p'
        elif '720p' in text or '720' in text:
            return '720p'
        elif '480p' in text or '480' in text:
            return '480p'
        elif '360p' in text or '360' in text:
            return '360p'
        elif 'hd' in text:
            return '720p'
        else:
            return '720p'  # Default quality

    def fetch_episode_page(self, post_link):
        """Fetch the episode page HTML to extract download links"""
        try:
            scraper = cloudscraper.create_scraper()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            
            response = scraper.get(post_link, headers=headers, timeout=15)
            response.raise_for_status()
            return response.text
            
        except Exception as e:
            print(f"⚠️ Error fetching episode page {post_link}: {e}")
            return None

    def get_or_create_category(self, category_id):
        """Get or create anime category from WordPress category"""
        try:
            scraper = cloudscraper.create_scraper()
            response = scraper.get(
                f"https://chia-anime.su/wp-json/wp/v2/categories/{category_id}",
                timeout=10
            )
            response.raise_for_status()
            
            category_data = response.json()
            category_name = category_data.get('name', 'Uncategorized')
            
            category, created = AnimeCategory.objects.get_or_create(
                name=category_name,
                defaults={
                    'slug': slugify(category_name),
                    'description': category_data.get('description', ''),
                    'is_active': True
                }
            )
            
            if created:
                print(f"Created new category: {category_name}")
            
            return category
            
        except Exception as e:
            print(f"Error fetching category {category_id}: {e}")
            # Return default category
            category, _ = AnimeCategory.objects.get_or_create(
                name='Anime',
                defaults={'slug': 'anime', 'is_active': True}
            )
            return category

    def get_total_posts(self):
        """Get total number of posts from the API"""
        try:
            scraper = cloudscraper.create_scraper()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
            }

            response = scraper.get(
                API_URL,
                params={
                    'page': 1,
                    'per_page': 1,
                    'status': 'publish'
                },
                headers=headers,
                timeout=15
            )
            
            response.raise_for_status()
            
            # WordPress API includes total count in headers
            total_posts = response.headers.get('X-WP-Total', 0)
            total_pages = response.headers.get('X-WP-TotalPages', 0)
            
            return int(total_posts), int(total_pages)
            
        except Exception as e:
            print(f"⚠️ Could not get total post count: {e}")
            return None, None

    def handle(self, *args, **options):
        max_pages = options.get('max_pages')
        start_page = options.get('start_page', 1)
        per_page = min(options.get('per_page', 20), 100)  # WordPress API max is 100
        delay_min = options.get('delay_min', 2.0)
        delay_max = options.get('delay_max', 4.0)
        
        print(f"🚀 Starting comprehensive scrape from chia-anime.su...")
        print(f"   📊 Starting from page: {start_page}")
        print(f"   📄 Posts per page: {per_page}")
        print(f"   ⏱️  Request delay: {delay_min}-{delay_max} seconds")
        if max_pages:
            print(f"   🔢 Max pages limit: {max_pages}")
        else:
            print(f"   ∞  No page limit - scraping ALL posts")
        
        # Get total posts and pages count
        total_posts, total_pages = self.get_total_posts()
        if total_posts and total_pages:
            print(f"   📈 Total posts available: {total_posts}")
            print(f"   📚 Total pages available: {total_pages}")
            
            # Update max_pages if not set or exceeds available pages
            if max_pages is None:
                max_pages = total_pages
                print(f"   🎯 Will scrape all {total_pages} pages")
            elif max_pages > total_pages:
                max_pages = total_pages
                print(f"   ⚠️  Adjusted max pages to {total_pages} (actual available)")
        
        page = start_page
        processed_posts = 0
        consecutive_empty_pages = 0
        max_empty_pages = 3  # Stop after 3 consecutive empty pages
        
        while True:
            # Check if we've hit the max pages limit
            if max_pages and page > start_page + max_pages - 1:
                print(f"✅ Reached maximum pages limit ({max_pages})")
                break
                
            try:
                print(f"\n🌐 Fetching page {page}...")
                
                scraper = cloudscraper.create_scraper()
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                }

                response = scraper.get(
                    API_URL,
                    params={
                        'page': page,
                        'per_page': per_page,
                        'status': 'publish',
                        'order': 'desc',
                        'orderby': 'date'
                    },
                    headers=headers,
                    timeout=15
                )
                
                # Handle different HTTP status codes
                if response.status_code == 404:
                    print("✅ Page not found (404) - reached end of available pages")
                    break
                elif response.status_code == 400:
                    print("⚠️ Bad request (400) - possibly invalid page number")
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= max_empty_pages:
                        print(f"❌ Too many consecutive errors ({consecutive_empty_pages}), stopping")
                        break
                    page += 1
                    continue
                    
                response.raise_for_status()
                posts = response.json()
                
                if not posts or len(posts) == 0:
                    consecutive_empty_pages += 1
                    print(f"📭 Empty page {page} (consecutive empty: {consecutive_empty_pages})")
                    
                    if consecutive_empty_pages >= max_empty_pages:
                        print(f"✅ Reached {max_empty_pages} consecutive empty pages - stopping")
                        break
                        
                    page += 1
                    # Add delay before trying next page
                    time.sleep(random.uniform(delay_min, delay_max))
                    continue
                
                # Reset consecutive empty pages counter
                consecutive_empty_pages = 0
                
                print(f"📄 Processing {len(posts)} posts from page {page}...")
                posts_processed_this_page = 0

                for post in posts:
                    try:
                        raw_title = post.get('title', {}).get('rendered', '').strip()
                        if not raw_title:
                            continue

                        print(f"\n🎬 Processing: {raw_title}")
                        
                        # Clean title and extract episode info
                        anime_title, episode_number = self.clean_title(raw_title)
                        
                        if not episode_number:
                            print(f"⚠️ No episode number found, skipping: {anime_title}")
                            continue

                        # Get post content and description
                        content = post.get('content', {}).get('rendered', '')
                        description = BeautifulSoup(
                            post.get('excerpt', {}).get('rendered', ''), 
                            'html.parser'
                        ).get_text().strip()
                        
                        # Get the post link to fetch full HTML
                        post_link = post.get('link', '')
                        
                        # Fetch the full episode page HTML
                        print(f"  📄 Fetching episode page: {post_link}")
                        episode_html = self.fetch_episode_page(post_link)

                        # Extract download links from both content and full HTML
                        download_links = self.extract_download_links(episode_html, content)
                        
                        if not download_links:
                            print(f"⚠️ No download links found for: {anime_title} Episode {episode_number}")
                            continue
                        
                        print(f"✅ Found {len(download_links)} download links")

                        # Extract anime poster
                        poster_url = self.extract_anime_poster(content, anime_title)
                        if poster_url:
                            print(f"  🖼️ Found poster: {poster_url}")

                        # Get or create anime
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

                        # Update poster if we found a new one and anime doesn't have one
                        if not anime_created and poster_url and not anime.poster_url:
                            anime.poster_url = poster_url
                            anime.save()
                            print(f"  📸 Updated anime poster")

                        if anime_created:
                            print(f"✅ Created new anime: {anime_title}")
                            
                            # Set category if available
                            if post.get('categories') and len(post['categories']) > 0:
                                category = self.get_or_create_category(post['categories'][0])
                                anime.category = category
                                anime.save()

                        # Get or create episode
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
                                'publish_date': timezone.now()
                            }
                        )

                        if episode_created:
                            print(f"✅ Created new episode: {anime_title} Episode {episode_number}")
                        else:
                            print(f"ℹ️ Episode already exists: {anime_title} Episode {episode_number}")

                        # Update download links
                        existing_links = {dl.url: dl for dl in episode.download_links.all()}
                        added_links = 0
                        
                        for link_data in download_links:
                            if link_data['url'] not in existing_links:
                                DownloadLink.objects.create(
                                    episode=episode,
                                    quality=link_data['quality'],
                                    url=link_data['url'],
                                    host_name=self.get_host_name(link_data['url']),
                                    label=link_data['label'],
                                    is_active=True
                                )
                                added_links += 1

                        if added_links > 0:
                            print(f"➕ Added {added_links} new download links")

                        # Update anime episode count
                        max_episode = Episode.objects.filter(anime=anime).aggregate(
                            max_ep=models.Max('episode_number')
                        )['max_ep'] or 0
                        
                        if max_episode > anime.total_episodes:
                            anime.total_episodes = max_episode
                            anime.save()

                        processed_posts += 1
                        posts_processed_this_page += 1
                        
                        # Add delay between posts to avoid overwhelming the server
                        time.sleep(random.uniform(delay_min, delay_max))

                    except Exception as e:
                        print(f"💥 Error processing post: {e}")
                        import traceback
                        traceback.print_exc()
                        continue

                print(f"✅ Page {page} complete: processed {posts_processed_this_page}/{len(posts)} posts")
                print(f"📊 Total processed so far: {processed_posts} posts")
                
                # Calculate progress if we know total
                if total_posts:
                    progress = (processed_posts / total_posts) * 100
                    print(f"🎯 Progress: {progress:.1f}% ({processed_posts}/{total_posts})")
                
                page += 1
                
                # Add delay between pages
                time.sleep(random.uniform(delay_min * 1.5, delay_max * 1.5))

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    print("✅ No more pages available (404).")
                    break
                elif e.response.status_code == 429:
                    print("⚠️ Rate limited (429) - waiting longer...")
                    time.sleep(random.uniform(30, 60))  # Wait longer for rate limiting
                    continue
                elif e.response.status_code >= 500:
                    print(f"⚠️ Server error ({e.response.status_code}) - waiting and retrying...")
                    time.sleep(random.uniform(10, 20))
                    continue
                else:
                    print(f"🔥 HTTP error: {e}")
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= max_empty_pages:
                        print(f"❌ Too many consecutive errors, stopping")
                        break
                    continue
                    
            except requests.exceptions.Timeout:
                print("⚠️ Request timeout - retrying...")
                time.sleep(random.uniform(5, 10))
                continue
                
            except requests.exceptions.ConnectionError:
                print("⚠️ Connection error - retrying...")
                time.sleep(random.uniform(10, 20))
                continue
                
            except Exception as e:
                print(f"🔥 Unexpected error: {e}")
                import traceback
                traceback.print_exc()
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= max_empty_pages:
                    print(f"❌ Too many consecutive errors, stopping")
                    break
                continue

        # Final summary
        print(f"\n🎉 Scraping completed!")
        print(f"📊 Final Statistics:")
        print(f"   • Total posts processed: {processed_posts}")
        print(f"   • Pages scraped: {page - start_page}")
        print(f"   • Total animes in database: {Anime.objects.count()}")
        print(f"   • Total episodes in database: {Episode.objects.count()}")
        print(f"   • Total download links in database: {DownloadLink.objects.count()}")
        
        # Show some stats about what was scraped
        if processed_posts > 0:
            recent_animes = Anime.objects.order_by('-id')[:5]
            print(f"\n📺 Recently added animes:")
            for anime in recent_animes:
                episode_count = anime.episodes.count()
                print(f"   • {anime.title} ({episode_count} episodes)")

    def get_host_name(self, url):
        """Extract host name from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            if 'mega.nz' in domain:
                return 'mega'
            elif 'mediafire.com' in domain:
                return 'mediafire'
            elif 'drive.google.com' in domain:
                return 'gdrive'
            elif 'dailymotion.com' in domain:
                return 'dailymotion'
            elif 'streamtape.com' in domain:
                return 'streamtape'
            elif 'fypttvideos.xyz' in domain:
                return 'vidstreaming'
            elif 'mixdrop.co' in domain:
                return 'mixdrop'
            elif 'doodstream.com' in domain:
                return 'doodstream'
            elif 'mp4upload.com' in domain:
                return 'mp4upload'
            elif 'embedz.net' in domain:
                return 'embedz'
            else:
                return domain.replace('www.', '')
        except:
            return 'unknown'