from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
from django.db import connection, reset_queries
from apk_store.models import APK, Category, Screenshot, APKVersion, DownloadFile
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
import html

API_URL = 'https://ristechy.com/wp-json/wp/v2/posts/'
CATEGORIES_URL = 'https://ristechy.com/wp-json/wp/v2/categories/'
MEDIA_URL = 'https://ristechy.com/wp-json/wp/v2/media/'

class Command(BaseCommand):
    help = 'Scrape APK/Game data from RisTechy and update database'

    def __init__(self):
        super().__init__()
        self.cache_file = 'scraped_pages_cache.pkl'
        self.scraped_pages = self.load_scraped_pages()
        self.category_map = {}
        self.media_cache = {}

    def load_scraped_pages(self):
        """Load previously scraped pages from cache file"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'rb') as f:
                    data = pickle.load(f)
                    print(f"📂 Loaded {len(data)} previously scraped pages from cache")
                    return data
            except Exception as e:
                print(f"⚠️ Could not load cache: {e}")
                return set()
        return set()

    def save_scraped_pages(self):
        """Save scraped pages to cache file"""
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.scraped_pages, f)
            print(f"💾 Saved {len(self.scraped_pages)} scraped pages to cache")
        except Exception as e:
            print(f"⚠️ Could not save cache: {e}")

    def mark_page_as_scraped(self, page_number):
        """Mark a page as scraped"""
        self.scraped_pages.add(page_number)
        if len(self.scraped_pages) % 5 == 0:
            self.save_scraped_pages()

    def is_page_scraped(self, page_number):
        """Check if a page has been scraped before"""
        return page_number in self.scraped_pages

    def add_arguments(self, parser):
        parser.add_argument('--max-pages', type=int, default=None)
        parser.add_argument('--start-page', type=int, default=1)
        parser.add_argument('--per-page', type=int, default=999999)
        parser.add_argument('--delay-min', type=float, default=2.0)
        parser.add_argument('--delay-max', type=float, default=4.0)
        parser.add_argument('--force-rescrape', action='store_true', 
                          help='Force rescrape of already scraped pages')
        parser.add_argument('--clear-cache', action='store_true',
                          help='Clear the scraped pages cache before starting')
        parser.add_argument('--categories', nargs='*', 
                          help='Only scrape specific category IDs (e.g., 33 36)')

    def refresh_db_connection(self):
        """Refresh database connection to prevent timeout"""
        try:
            reset_queries()
            connection.close()
            print("  🔄 Database connection refreshed")
        except Exception as e:
            print(f"  ⚠️ Connection refresh warning: {e}")

    def get_featured_image(self, media_id):
        """Fetch featured image URL from WordPress media API"""
        if not media_id or media_id == 0:
            return None
        
        if media_id in self.media_cache:
            return self.media_cache[media_id]
        
        try:
            scraper = cloudscraper.create_scraper()
            response = scraper.get(f"{MEDIA_URL}{media_id}", timeout=10)
            response.raise_for_status()
            
            media_data = response.json()
            image_url = media_data.get('source_url', '')
            
            # Also try to get a medium or large size
            if 'media_details' in media_data and 'sizes' in media_data['media_details']:
                sizes = media_data['media_details']['sizes']
                if 'large' in sizes:
                    image_url = sizes['large'].get('source_url', image_url)
                elif 'medium' in sizes:
                    image_url = sizes['medium'].get('source_url', image_url)
            
            self.media_cache[media_id] = image_url
            return image_url
        except Exception as e:
            print(f"  ⚠️ Error fetching media {media_id}: {e}")
            return None

    def get_category_name(self, category_id):
        """Fetch category name from WordPress API"""
        if category_id in self.category_map:
            return self.category_map[category_id]
        
        try:
            scraper = cloudscraper.create_scraper()
            response = scraper.get(f"{CATEGORIES_URL}{category_id}", timeout=10)
            response.raise_for_status()
            
            category_data = response.json()
            category_name = category_data.get('name', 'Uncategorized')
            self.category_map[category_id] = category_name
            
            return category_name
        except Exception as e:
            print(f"  ⚠️ Error fetching category {category_id}: {e}")
            return 'Uncategorized'

    def get_or_create_category(self, category_ids):
        """Get or create categories from WordPress category IDs"""
        categories = []
        
        for cat_id in category_ids:
            category_name = self.get_category_name(cat_id)
            
            category, created = Category.objects.get_or_create(
                name=category_name,
                defaults={
                    'slug': slugify(category_name),
                    'description': f'Category for {category_name}',
                }
            )
            
            if created:
                print(f"  🆕 Created category: {category_name}")
            
            categories.append(category)
        
        return categories

    def clean_html(self, text):
        """Clean HTML entities from text"""
        return html.unescape(text)

    def extract_images_from_content(self, content_html):
        """Extract image URLs from post content"""
        images = []
        
        try:
            soup = BeautifulSoup(content_html, 'html.parser')
            img_tags = soup.find_all('img')
            
            for img in img_tags:
                src = img.get('src', '').strip()
                
                # Skip common non-content images
                skip_keywords = ['logo', 'banner', 'ad', 'button', 'icon', 'avatar', 'gravatar']
                if src and not any(skip in src.lower() for skip in skip_keywords):
                    # Check if it's a reasonable size (not tiny icons)
                    width = img.get('width', '100')
                    height = img.get('height', '100')
                    
                    try:
                        if isinstance(width, str) and 'px' in width:
                            width = width.replace('px', '')
                        if isinstance(height, str) and 'px' in height:
                            height = height.replace('px', '')
                        
                        width = int(float(width)) if width else 100
                        height = int(float(height)) if height else 100
                        
                        # Only include images that are reasonably sized
                        if width >= 200 or height >= 200:
                            images.append(src)
                    except:
                        # If we can't parse size, include it anyway
                        images.append(src)
                
                if len(images) >= 10:  # Limit to 10 images max
                    break
        
        except Exception as e:
            print(f"  ⚠️ Error extracting images: {e}")
        
        return images
    
    # In scrape_ristechy.py, replace the extract_download_links method

    def extract_download_links(self, content_html, title):
        """IMPROVED: Extract and categorize download links from post content"""
        links = []
        
        try:
            soup = BeautifulSoup(content_html, 'html.parser')
            
            # EXPANDED download indicators
            download_indicators = [
                'download', 'mediafire', 'mega.nz', 'drive.google', 'mega.co.nz',
                'dropbox', 'apk', 'mod', 'obb', 'data', 'zip', 'rar', '7z',
                'zippyshare', 'uploaded', 'rapidgator', 'file', 'files.fm',
                'anonfiles', 'workupload', 'solidfiles', 'sendspace',
                'apkadmin', 'archive.org', 'is.gd', 'bit.ly', 'tinyurl'
            ]
            
            # Find ALL anchor tags with href
            for a_tag in soup.find_all('a', href=True):
                href = a_tag.get('href', '').strip()
                text = a_tag.get_text().strip()
                
                # Skip empty or very short hrefs
                if not href or len(href) < 10:
                    continue
                
                # Skip non-download links
                if href.endswith(('.jpg', '.png', '.gif', '.css', '.js', '.webp')):
                    continue
                
                # Check if it's a download link
                is_download = any(indicator in href.lower() or indicator in text.lower() 
                                for indicator in download_indicators)
                
                # ALSO check for common button/link classes
                link_class = ' '.join(a_tag.get('class', [])).lower()
                is_download = is_download or any(keyword in link_class for keyword in ['button', 'download', 'btn'])
                
                if not is_download:
                    continue
                
                # Determine file details
                file_type = 'apk'  # default
                file_name = text if text else 'Download'
                
                text_lower = text.lower()
                href_lower = href.lower()
                
                # Extract size
                size_match = re.search(r'\(([0-9.]+\s*(?:MB|GB|KB|mb|gb|kb))\)', text)
                size = size_match.group(1) if size_match else ''
                
                # Extract version
                version_match = re.search(r'v?(\d+\.[\d.]+)', text)
                version = version_match.group(1) if version_match else ''
                
                # Determine file type - IMPROVED LOGIC
                if 'obb' in text_lower or 'obb' in href_lower:
                    file_type = 'obb'
                elif 'data' in text_lower or 'data' in href_lower:
                    file_type = 'data'
                elif ('mod' in text_lower or 'mod' in href_lower) and 'apk' not in text_lower:
                    file_type = 'mod'
                elif 'patch' in text_lower:
                    file_type = 'patch'
                elif 'bios' in text_lower:
                    file_type = 'other'
                elif 'apk' in text_lower or 'apk' in href_lower:
                    file_type = 'apk'
                elif any(word in text_lower for word in ['download', 'file', 'get']):
                    file_type = 'apk'
                
                links.append({
                    'url': href,
                    'text': file_name,
                    'file_type': file_type,
                    'size': size,
                    'version': version
                })
            
            # Sort by priority
            type_priority = {'apk': 0, 'obb': 1, 'data': 2, 'mod': 3, 'patch': 4, 'other': 5}
            links.sort(key=lambda x: type_priority.get(x['file_type'], 99))
            
            # Remove duplicates
            seen = set()
            unique_links = []
            for link in links:
                if link['url'] not in seen:
                    seen.add(link['url'])
                    unique_links.append(link)
            
            return unique_links
            
        except Exception as e:
            print(f"  ⚠️ Error extracting download links: {e}")
            import traceback
            traceback.print_exc()
        
        return links

    def extract_version_and_size(self, content_html, title):
        """Extract version and size information from content"""
        version = ''
        size = ''
        
        try:
            soup = BeautifulSoup(content_html, 'html.parser')
            text_content = soup.get_text()
            
            # Extract version
            version_patterns = [
                r'[Vv]ersion[:\s]+(\d+\.[\d.]+)',
                r'[Vv](\d+\.[\d.]+)',
                r'(\d+\.[\d.]+)\s+[Aa]pk',
                r'[Mm]od\s+(\d+\.[\d.]+)',
            ]
            
            for pattern in version_patterns:
                match = re.search(pattern, text_content)
                if match:
                    version = match.group(1)
                    break
            
            # Also check title for version
            if not version:
                title_version = re.search(r'(\d+\.[\d.]+)', title)
                if title_version:
                    version = title_version.group(1)
            
            # Extract size
            size_patterns = [
                r'(?:Size|Download)[:\s]+([0-9.]+\s*(?:MB|GB|KB))',
                r'([0-9.]+\s*(?:MB|GB|KB))',
            ]
            
            for pattern in size_patterns:
                size_match = re.search(pattern, text_content, re.IGNORECASE)
                if size_match:
                    size = size_match.group(1).strip()
                    break
        
        except Exception as e:
            print(f"  ⚠️ Error extracting version/size: {e}")
        
        return version or '1.0.0', size or 'Unknown'

    def determine_apk_type(self, categories, title, content):
        """Determine if this is a game or app"""
        game_indicators = [
            'game', 'ppsspp', 'psp', 'emulator', 'play', 'soccer', 'football', 
            'racing', 'fight', 'adventure', 'rpg', 'simulation', 'wwe', 'fifa',
            'pes', 'nba', 'gta', 'minecraft', 'pubg', 'cod', 'sports'
        ]
        
        # Check categories
        for cat_name in [self.get_category_name(cat_id) for cat_id in categories]:
            if any(indicator in cat_name.lower() for indicator in game_indicators):
                return 'game'
        
        # Check title
        title_lower = title.lower()
        if any(indicator in title_lower for indicator in game_indicators):
            return 'game'
        
        # Check content
        content_lower = content.lower()
        if any(indicator in content_lower for indicator in game_indicators):
            return 'game'
        
        return 'app'

    def determine_status(self, title, content):
        """Determine APK status (modded, premium, etc.)"""
        content_lower = (title + ' ' + content).lower()
        
        if 'mod' in content_lower or 'unlimited' in content_lower or 'hack' in content_lower:
            return 'modded'
        elif 'premium' in content_lower or 'pro' in content_lower:
            return 'premium'
        elif 'unlocked' in content_lower:
            return 'unlocked'
        elif 'paid' in content_lower:
            return 'paid'
        else:
            return 'original'

    def extract_mod_features(self, content_html):
        """Extract mod features from content"""
        features = []
        
        try:
            soup = BeautifulSoup(content_html, 'html.parser')
            
            # Look for lists that might contain mod features
            for ul in soup.find_all(['ul', 'ol']):
                for li in ul.find_all('li'):
                    text = li.get_text().strip()
                    if text and any(keyword in text.lower() for keyword in [
                        'unlimited', 'unlocked', 'premium', 'mod', 'free', 
                        'hack', 'no ads', 'full', 'pro', 'vip'
                    ]):
                        features.append(text)
                        if len(features) >= 10:
                            break
                if len(features) >= 10:
                    break
            
            # If no features found in lists, look for common mod feature patterns
            if not features:
                text_content = soup.get_text()
                feature_patterns = [
                    r'(?:•|-)([^•\-\n]+(?:unlimited|unlocked|premium|mod|free|hack)[^•\-\n]+)',
                ]
                
                for pattern in feature_patterns:
                    matches = re.findall(pattern, text_content, re.IGNORECASE)
                    features.extend([m.strip() for m in matches[:10]])
                    if features:
                        break
        
        except Exception as e:
            print(f"  ⚠️ Error extracting mod features: {e}")
        
        return '\n'.join(features[:10]) if features else ''

    def extract_full_description(self, content_html, excerpt):
        """Extract FULL description from content, preserving formatting for up to 50,000 chars"""
        try:
            soup = BeautifulSoup(content_html, 'html.parser')
            
            # Remove script, style, and ad-related tags
            for script in soup(["script", "style", "ins"]):  # ins is for ads
                script.decompose()
            
            # Remove ad blocks and other junk
            for div in soup.find_all('div', class_=['code-block', 'adsbygoogle']):
                div.decompose()
            
            # Get text content with proper line breaks
            text = soup.get_text(separator='\n')
            
            # Clean up excessive whitespace while preserving paragraphs
            lines = [line.strip() for line in text.split('\n')]
            lines = [line for line in lines if line]  # Remove empty lines
            
            # Join lines back together with double line breaks for readability
            full_text = '\n\n'.join(lines)
            
            # If the text is too short or empty, use excerpt as fallback
            if len(full_text.strip()) < 100 and excerpt:
                return excerpt
            
            # Remove common footer/header junk
            junk_phrases = [
                'Share this:',
                'Like this:',
                'Related',
                'Filed Under:',
                'Tagged With:',
                'Click to share',
                'Click to print',
                'Jump To',
                'Table of Contents',
            ]
            
            for phrase in junk_phrases:
                if phrase in full_text:
                    full_text = full_text.split(phrase)[0]
            
            # Limit to 50,000 chars (enough for 30K+ words)
            return full_text.strip()[:50000]
            
        except Exception as e:
            print(f"  ⚠️ Error extracting full description: {e}")
            return excerpt or "No description available."

    
    def get_total_posts(self, category_filter=None):
        """Get total number of posts"""
        try:
            scraper = cloudscraper.create_scraper()
            params = {'page': 1, 'per_page': 1, 'status': 'publish'}
            
            if category_filter:
                params['categories'] = ','.join(map(str, category_filter))
            
            response = scraper.get(API_URL, params=params, timeout=15)
            response.raise_for_status()
            
            total_posts = response.headers.get('X-WP-Total', 0)
            total_pages = response.headers.get('X-WP-TotalPages', 0)
            
            return int(total_posts), int(total_pages)
        except Exception as e:
            print(f"⚠️ Could not get total post count: {e}")
            return None, None

    def handle(self, *args, **options):
        max_pages = options.get('max_pages')
        start_page = options.get('start_page', 1)
        per_page = min(options.get('per_page', 20), 100)
        delay_min = options.get('delay_min', 2.0)
        delay_max = options.get('delay_max', 4.0)
        force_rescrape = options.get('force_rescrape', False)
        clear_cache = options.get('clear_cache', False)
        category_filter = options.get('categories')
        
        if category_filter:
            category_filter = [int(cat) for cat in category_filter]
        
        if clear_cache:
            self.scraped_pages.clear()
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            print("🗑️ Cleared scraped pages cache")
        
        print(f"🚀 Starting scrape from RisTechy WordPress API...")
        print(f"   📊 Starting from page: {start_page}")
        print(f"   📄 Posts per page: {per_page}")
        print(f"   ⏱️  Request delay: {delay_min}-{delay_max} seconds")
        print(f"   🔄 Force rescrape: {force_rescrape}")
        print(f"   📂 Previously scraped pages: {len(self.scraped_pages)}")
        if category_filter:
            print(f"   🏷️  Filtering categories: {category_filter}")
        
        total_posts, total_pages = self.get_total_posts(category_filter)
        if total_posts and total_pages:
            print(f"   📈 Total posts available: {total_posts}")
            print(f"   📚 Total pages available: {total_pages}")
        
        page = start_page
        processed_posts = 0
        skipped_pages = 0
        consecutive_empty_pages = 0
        max_empty_pages = 3
        
        stats = {
            'new_apks': 0,
            'updated_apks': 0,
            'skipped_apks': 0,
            'new_categories': 0,
            'new_screenshots': 0,
        }
        
        while True:
            if max_pages and page > start_page + max_pages - 1:
                print(f"✅ Reached maximum pages limit ({max_pages})")
                break
            
            if not force_rescrape and self.is_page_scraped(page):
                print(f"\n⭐ Page {page} - ALREADY SCRAPED (skipping)")
                skipped_pages += 1
                page += 1
                continue
            
            if (page - start_page) % 10 == 0 and page != start_page:
                self.refresh_db_connection()
            
            try:
                print(f"\n🌐 Fetching page {page}...")
                
                scraper = cloudscraper.create_scraper()
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                }
                
                params = {
                    'page': page,
                    'per_page': per_page,
                    'status': 'publish',
                    'order': 'desc',
                    'orderby': 'date',
                    '_embed': 1  # This will embed featured media
                }
                
                if category_filter:
                    params['categories'] = ','.join(map(str, category_filter))
                
                response = scraper.get(API_URL, params=params, headers=headers, timeout=15)
                
                if response.status_code == 404:
                    print("✅ Page not found (404) - reached end")
                    break
                elif response.status_code == 400:
                    print("⚠️ Bad request (400)")
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= max_empty_pages:
                        break
                    page += 1
                    continue
                
                response.raise_for_status()
                posts = response.json()
                
                if not posts or len(posts) == 0:
                    consecutive_empty_pages += 1
                    print(f"🔭 Empty page {page}")
                    
                    if consecutive_empty_pages >= max_empty_pages:
                        print(f"✅ Reached {max_empty_pages} consecutive empty pages")
                        break
                    
                    page += 1
                    time.sleep(random.uniform(delay_min, delay_max))
                    continue
                
                consecutive_empty_pages = 0
                print(f"📄 Processing {len(posts)} posts from page {page}...")
                posts_processed_this_page = 0
                
                for post in posts:
                    try:
                        title = self.clean_html(post.get('title', {}).get('rendered', '')).strip()
                        if not title:
                            continue
                        
                        print(f"\n🎮 Processing: {title}")
                        
                        content_html = post.get('content', {}).get('rendered', '')
                        excerpt = BeautifulSoup(
                            post.get('excerpt', {}).get('rendered', ''), 
                            'html.parser'
                        ).get_text().strip()

                        # Extract full description (NEW - add this line)
                        full_description = self.extract_full_description(content_html, excerpt)
                                                
                        post_link = post.get('link', '')
                        post_date = post.get('date', '')
                        featured_media_id = post.get('featured_media', 0)
                        category_ids = post.get('categories', [])
                        
                        # Get featured image
                        icon_url = ''
                        
                        # Try to get from embedded data first
                        if '_embedded' in post and 'wp:featuredmedia' in post['_embedded']:
                            try:
                                featured_media = post['_embedded']['wp:featuredmedia'][0]
                                icon_url = featured_media.get('source_url', '')
                                print(f"  🖼️  Got featured image from embed: {icon_url[:50]}...")
                            except:
                                pass
                        
                        # If not found, fetch from media API
                        if not icon_url and featured_media_id:
                            icon_url = self.get_featured_image(featured_media_id)
                            if icon_url:
                                print(f"  🖼️  Got featured image from API: {icon_url[:50]}...")
                        
                        # Extract additional images from content
                        content_images = self.extract_images_from_content(content_html)
                        if content_images:
                            print(f"  🖼️  Found {len(content_images)} images in content")
                        
                        # Use first content image as icon if no featured image
                        if not icon_url and content_images:
                            icon_url = content_images[0]
                            print(f"  🖼️  Using first content image as icon")
                        
                        # Use second image as cover, or same as icon
                        cover_image = content_images[1] if len(content_images) > 1 else icon_url
                        
                        # Determine APK type and status
                        apk_type = self.determine_apk_type(category_ids, title, content_html)
                        status = self.determine_status(title, content_html)
                        
                        # Extract version and size
                        version, size = self.extract_version_and_size(content_html, title)
                        
                        # Extract download links - IMPROVED
                        download_links = self.extract_download_links(content_html, title)

                        # Primary download URL
                        apk_links = [link for link in download_links if link['file_type'] == 'apk']
                        download_url = apk_links[0]['url'] if apk_links else (download_links[0]['url'] if download_links else '')
           
                        if download_links:
                            print(f"  📥 Found {len(download_links)} download link(s)")
                            for link in download_links[:3]:  # Show first 3
                                print(f"     - {link['file_type']}: {link['text'][:50]}")
                        else:
                            print(f"  ⚠️ No download links found")
                        
                        # Extract mod features
                        mod_features = self.extract_mod_features(content_html)
                        
                        # Create or update APK
                        apk, created = APK.objects.update_or_create(
                            source_url=post_link,
                            defaults={
                                'title': title,
                                'slug': slugify(title),
                                'apk_type': apk_type,
                                'description': full_description,  # ✅ USE FULL DESCRIPTION
                                'icon_url': icon_url,
                                'cover_image_url': cover_image,
                                'version': version,
                                'size': size,
                                'status': status,
                                'mod_features': mod_features,
                                'download_url': download_url,
                                'is_active': True,
                            }
                        )
                        
                        if created:
                            print(f"  🆕 Created NEW APK: {title}")
                            stats['new_apks'] += 1
                        else:
                            print(f"  ♻️ Updated EXISTING APK: {title}")
                            stats['updated_apks'] += 1
                        
                        # Handle categories
                        if category_ids:
                            categories = self.get_or_create_category(category_ids)
                            apk.categories.set(categories)

                        
                        # Handle screenshots (skip first 2 as they're used for icon/cover)
                        screenshot_images = content_images[2:] if len(content_images) > 2 else []
                        
                        if screenshot_images:
                            # Clear existing screenshots
                            apk.screenshots.all().delete()
                            
                            for idx, img_url in enumerate(screenshot_images[:5]):  # Max 5 screenshots
                                Screenshot.objects.create(
                                    apk=apk,
                                    image_url=img_url,
                                    order=idx
                                )
                                stats['new_screenshots'] += 1
                            
                            print(f"  📸 Added {len(screenshot_images[:5])} screenshots")
                        
                        # Handle download files
                        if download_links:
                            # Clear existing download files
                            apk.download_files.all().delete()
                            
                            for idx, link_data in enumerate(download_links):
                                DownloadFile.objects.create(
                                    apk=apk,
                                    file_type=link_data['file_type'],
                                    file_name=link_data['text'],
                                    download_url=link_data['url'],
                                    size=link_data.get('size', size),
                                    version=link_data.get('version', version),
                                    order=idx,
                                    is_required=link_data['file_type'] in ['apk', 'obb'],  # APK and OBB are usually required
                                )
                                stats['new_download_files'] = stats.get('new_download_files', 0) + 1
                            
                            print(f"  📦 Added {len(download_links)} download file(s)")
                        
                        processed_posts += 1
                        posts_processed_this_page += 1
                        
                    except Exception as post_error:
                        print(f"💥 Error processing post: {post_error}")
                        import traceback
                        traceback.print_exc()
                        continue
                    
                    time.sleep(random.uniform(delay_min, delay_max))
                
                self.mark_page_as_scraped(page)
                
                print(f"✅ Page {page} complete: processed {posts_processed_this_page}/{len(posts)} posts")
                print(f"📊 Total processed so far: {processed_posts} posts")
                print(f"⭐ Total skipped pages: {skipped_pages}")
                
                if total_posts:
                    progress = (processed_posts / total_posts) * 100
                    print(f"🎯 Progress: {progress:.1f}% ({processed_posts}/{total_posts})")
                
                page += 1
                time.sleep(random.uniform(delay_min * 1.5, delay_max * 1.5))
            
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    print("✅ No more pages available")
                    break
                elif e.response.status_code == 429:
                    print("⚠️ Rate limited - waiting...")
                    time.sleep(60)
                    continue
                else:
                    print(f"🔥 HTTP error: {e}")
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= max_empty_pages:
                        break
                    continue
            
            except Exception as e:
                print(f"🔥 Unexpected error: {e}")
                import traceback
                traceback.print_exc()
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= max_empty_pages:
                    break
                continue
        
        self.save_scraped_pages()
        self.refresh_db_connection()
        
        try:
            total_apks = APK.objects.count()
            total_categories = Category.objects.count()
            total_screenshots = Screenshot.objects.count()
        except:
            total_apks = "Unknown"
            total_categories = "Unknown"
            total_screenshots = "Unknown"
        
        print(f"\n🎉 Scraping completed!")
        print(f"📊 Final Statistics:")
        print(f"   • Total posts processed: {processed_posts}")
        print(f"   • Pages scraped: {page - start_page}")
        print(f"   • Pages skipped (already scraped): {skipped_pages}")
        print(f"   • Total scraped pages in cache: {len(self.scraped_pages)}")
        print(f"\n📱 APK Statistics:")
        print(f"   • New APKs created: {stats['new_apks']}")
        print(f"   • Existing APKs updated: {stats['updated_apks']}")
        print(f"   • Total APKs in DB: {total_apks}")
        print(f"\n🏷️  Category Statistics:")
        print(f"   • Total categories in DB: {total_categories}")
        print(f"\n🖼️  Screenshot Statistics:")
        print(f"   • New screenshots added: {stats['new_screenshots']}")
        print(f"   • Total screenshots in DB: {total_screenshots}")
        print(f"\n💡 Tip: Use --force-rescrape to re-scrape already scraped pages")
        print(f"💡 Tip: Use --clear-cache to start fresh")
        print(f"💡 Tip: Use --categories 33 36 to scrape specific categories")