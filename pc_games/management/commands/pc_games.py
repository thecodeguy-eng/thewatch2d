# management/commands/scrape_fitgirl.py
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
from datetime import datetime
import re
import time
import pytz
from pc_games.models import (
    Game, Category, Tag, Screenshot, DownloadMirror, 
    GameUpdate, SystemRequirements, ScrapingLog
)

class Command(BaseCommand):
    help = 'Scrape game repacks from FitGirl Repacks'

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.base_url = 'https://fitgirl-repacks.site'
        self.api_url = f'{self.base_url}/wp-json/wp/v2/posts'
        self.categories_cache = {}
        self.tags_cache = {}

    def add_arguments(self, parser):
        parser.add_argument('--pages', type=int, default=9999, help='Number of pages to scrape')
        parser.add_argument('--per-page', type=int, default=100, help='Posts per page')
        parser.add_argument('--delay', type=float, default=2.0, help='Delay between requests')
        parser.add_argument('--category', type=int, help='Specific category ID to scrape')

    def handle(self, *args, **options):
        pages = options['pages']
        per_page = options['per_page']
        delay = options['delay']
        category_filter = options.get('category')

        # Fetch categories and tags first
        self.fetch_categories()
        self.fetch_tags()

        self.stdout.write(self.style.SUCCESS(f'Starting scrape: {pages} pages'))

        total_processed = 0
        total_created = 0
        total_updated = 0

        for page in range(1, pages + 1):
            self.stdout.write(f'\nProcessing page {page}...')
            
            params = {
                'page': page,
                'per_page': per_page,
                'status': 'publish',
                'orderby': 'date',
                'order': 'desc',
                '_embed': 1
            }
            
            if category_filter:
                params['categories'] = category_filter

            try:
                response = self.session.get(self.api_url, params=params, timeout=30)
                response.raise_for_status()
                posts = response.json()

                if not posts:
                    self.stdout.write(self.style.WARNING('No more posts found'))
                    break

                for post in posts:
                    try:
                        created = self.process_post(post)
                        if created:
                            total_created += 1
                        else:
                            total_updated += 1
                        total_processed += 1
                        
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'Error processing post: {e}'))
                        self.log_error(post, str(e))

                time.sleep(delay)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error fetching page {page}: {e}'))

        self.stdout.write(self.style.SUCCESS(
            f'\nCompleted! Processed: {total_processed}, '
            f'Created: {total_created}, Updated: {total_updated}'
        ))

    def fetch_categories(self):
        """Fetch all categories from WordPress API"""
        try:
            response = self.session.get(
                f'{self.base_url}/wp-json/wp/v2/categories',
                params={'per_page': 100},
                timeout=30
            )
            response.raise_for_status()
            categories = response.json()
            
            for cat in categories:
                self.categories_cache[cat['id']] = {
                    'name': cat['name'],
                    'slug': cat['slug']
                }
            
            self.stdout.write(self.style.SUCCESS(f'Fetched {len(self.categories_cache)} categories'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Error fetching categories: {e}'))

    def fetch_tags(self):
        """Fetch all tags from WordPress API"""
        try:
            response = self.session.get(
                f'{self.base_url}/wp-json/wp/v2/tags',
                params={'per_page': 100},
                timeout=30
            )
            response.raise_for_status()
            tags = response.json()
            
            for tag in tags:
                self.tags_cache[tag['id']] = {
                    'name': tag['name'],
                    'slug': tag['slug']
                }
            
            self.stdout.write(self.style.SUCCESS(f'Fetched {len(self.tags_cache)} tags'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Error fetching tags: {e}'))

    def process_post(self, post):
        """Process a single post and create/update game entry"""
        
        # Extract basic info
        title_raw = post.get('title', {}).get('rendered', '')
        title = BeautifulSoup(title_raw, 'html.parser').get_text().strip()
        
        # Skip non-game posts
        if not title or 'Upcoming Repacks' in title or 'Updates Digest' in title:
            self.stdout.write(self.style.WARNING(f'Skipping non-game post: {title}'))
            return False
        
        post_id = post.get('id')
        post_url = post.get('link', '')
        post_date = self.parse_date(post.get('date'))
        modified_date = self.parse_date(post.get('modified'))
        
        # Extract content
        content_html = post.get('content', {}).get('rendered', '')
        soup = BeautifulSoup(content_html, 'html.parser')
        
        # Get excerpt for short description
        excerpt_raw = post.get('excerpt', {}).get('rendered', '')
        short_description = BeautifulSoup(excerpt_raw, 'html.parser').get_text().strip()[:500]
        
        # Parse title for version and repack number
        version_match = re.search(r'[–\-]\s*v?([\d.]+[\w.]*)', title)
        version = version_match.group(1) if version_match else ''
        # Truncate version to 500 chars
        version = version[:500] if version else ''
        
        repack_number_match = re.search(r'#(\d+)', content_html)
        repack_number = f"#{repack_number_match.group(1)}" if repack_number_match else ''
        
        # Create or update game (without using 'created' in defaults)
        game, created = Game.objects.update_or_create(
            post_id=post_id,
            defaults={
                'title': title[:500],  # Truncate to fit field
                'slug': slugify(title)[:500],
                'version': version,
                'repack_number': repack_number[:20],
                'short_description': short_description,
                'post_url': post_url,
                'post_date': post_date,
                'modified_date': modified_date,
            }
        )
        
        # Update status after creation
        game.status = 'new' if created else 'updated'
        game.save()
        
        # Extract and save detailed info
        self.extract_game_details(game, soup, content_html)
        
        # Extract categories and tags
        self.process_categories(game, post.get('categories', []))
        self.process_tags(game, post.get('tags', []))
        
        # Extract images
        self.extract_images(game, soup, post)
        
        # Extract download links
        self.extract_download_links(game, soup)
        
        # Log success
        ScrapingLog.objects.create(
            game=game,
            status='success',
            message=f'Successfully processed: {title[:200]}',
            page_url=post_url
        )
        
        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Updated'}: {title[:100]}"
        ))
        
        return created

    def extract_game_details(self, game, soup, content_html):
        """Extract detailed game information"""
        
        # Get full description from content
        # Remove scripts, styles, and download sections
        for element in soup.find_all(['script', 'style']):
            element.decompose()
        
        # Extract text content
        full_text = soup.get_text(separator='\n', strip=True)
        game.full_description = full_text[:5000]  # Limit size
        
        # Extract genres/tags section
        text_content = soup.get_text()
        
        # Extract companies
        company_match = re.search(r'Compan(?:y|ies):\s*(.+?)(?:\n|Language)', text_content, re.IGNORECASE)
        if company_match:
            game.companies = company_match.group(1).strip()[:500]
        
        # Extract languages
        lang_match = re.search(r'Languages?:\s*(.+?)(?:\n|Original)', text_content, re.IGNORECASE)
        if lang_match:
            game.languages = lang_match.group(1).strip()[:500]
        
        # Extract sizes
        orig_size_match = re.search(r'Original Size:\s*(.+?)(?:\n|Repack)', text_content, re.IGNORECASE)
        if orig_size_match:
            game.original_size = orig_size_match.group(1).strip()[:50]
        
        repack_size_match = re.search(r'Repack Size:\s*(.+?)(?:\n|$)', text_content, re.IGNORECASE)
        if repack_size_match:
            game.repack_size = repack_size_match.group(1).strip()[:50]
        
        # Extract repack features
        features_list = []
        features_section = soup.find(['h3', 'strong'], string=re.compile('Repack Features', re.I))
        if features_section:
            # Find next ul or list of items
            next_ul = features_section.find_next('ul')
            if next_ul:
                for li in next_ul.find_all('li'):
                    feature_text = li.get_text().strip()
                    features_list.append(feature_text)
                    
                    # Extract installation details
                    if 'Installation takes' in feature_text or 'install time' in feature_text.lower():
                        game.installation_time = feature_text[:200]
                    if 'HDD space' in feature_text or 'up to' in feature_text:
                        space_match = re.search(r'up to\s+(.+?)(?:\s+depending|\s+after|$)', feature_text, re.I)
                        if space_match:
                            game.installation_size = space_match.group(1).strip()[:100]
        
        if features_list:
            game.repack_features = '\n'.join(features_list)[:2000]
        
        # Extract game description from spoiler
        spoilers = soup.find_all('div', class_='su-spoiler-content')
        for spoiler in spoilers:
            spoiler_title = spoiler.find_previous('div', class_='su-spoiler-title')
            if spoiler_title and 'Game Description' in spoiler_title.get_text():
                game.game_description = spoiler.get_text().strip()[:5000]
                break
        
        game.save()
        self.stdout.write(f'  - Extracted details for: {game.title[:50]}')

    def process_categories(self, game, category_ids):
        """Process and assign categories"""
        game.categories.clear()
        for cat_id in category_ids:
            if cat_id in self.categories_cache:
                cat_data = self.categories_cache[cat_id]
                category, _ = Category.objects.get_or_create(
                    slug=cat_data['slug'],
                    defaults={'name': cat_data['name']}
                )
                game.categories.add(category)

    def process_tags(self, game, tag_ids):
        """Process and assign tags"""
        game.tags.clear()
        for tag_id in tag_ids:
            if tag_id in self.tags_cache:
                tag_data = self.tags_cache[tag_id]
                tag, _ = Tag.objects.get_or_create(
                    slug=tag_data['slug'],
                    defaults={'name': tag_data['name']}
                )
                game.tags.add(tag)

    def extract_images(self, game, soup, post):
        """Extract cover and screenshot images"""
        
        cover_found = False
        
        # Get featured image from _embedded
        if '_embedded' in post and 'wp:featuredmedia' in post['_embedded']:
            try:
                featured_media = post['_embedded']['wp:featuredmedia'][0]
                source_url = featured_media.get('source_url', '')
                
                if source_url:
                    game.cover_image = source_url
                    game.save()
                    cover_found = True
                    self.stdout.write(f'  - Found cover image: {source_url[:50]}...')
            except (KeyError, IndexError) as e:
                self.stdout.write(f'  - No featured media in _embedded: {e}')
        
        # Try to get featured image from post metadata
        if not cover_found and 'featured_media' in post and post['featured_media'] != 0:
            try:
                media_id = post['featured_media']
                media_response = self.session.get(
                    f'{self.base_url}/wp-json/wp/v2/media/{media_id}',
                    timeout=10
                )
                if media_response.status_code == 200:
                    media_data = media_response.json()
                    source_url = media_data.get('source_url', '')
                    if source_url:
                        game.cover_image = source_url
                        game.save()
                        cover_found = True
                        self.stdout.write(f'  - Found cover via media API: {source_url[:50]}...')
            except Exception as e:
                self.stdout.write(f'  - Error fetching media: {e}')
        
        # Fallback: try to find first good image in content
        if not cover_found:
            images = soup.find_all('img')
            for img in images:
                src = img.get('src', '') or img.get('data-src', '')
                
                # Look for a good cover image
                if src and not any(skip in src.lower() for skip in ['icon', 'logo', 'emoji']):
                    # Check if it's a reasonable size (not a tiny image)
                    if any(keyword in src.lower() for keyword in ['.jpg', '.png', '.jpeg', 'wp-content']):
                        game.cover_image = src
                        game.save()
                        cover_found = True
                        self.stdout.write(f'  - Found cover from content: {src[:50]}...')
                        break
        
        # Extract screenshots
        game.screenshots.all().delete()
        
        # Look for all images in content
        images = soup.find_all('img')
        order = 0
        
        for img in images:
            src = img.get('src', '') or img.get('data-src', '')
            
            # Skip small images and icons
            if not src or 'icon' in src.lower() or 'logo' in src.lower() or 'emoji' in src.lower():
                continue
            
            # Skip the cover image if we already have it
            if cover_found and src == game.cover_image:
                continue
            
            # Look for screenshot-like images
            if any(keyword in src.lower() for keyword in ['riotpixels', 'screenshot', 'screen', '.jpg', '.png', 'wp-content/uploads']):
                Screenshot.objects.create(
                    game=game,
                    image_url=src,
                    thumbnail_url=src,
                    order=order
                )
                order += 1
                
                if order >= 10:  # Limit to 10 screenshots
                    break
        
        if order > 0:
            self.stdout.write(f'  - Found {order} screenshots')
        
        if not cover_found:
            self.stdout.write(f'  - WARNING: No cover image found for {game.title[:50]}')

    def extract_download_links(self, game, soup):
        """Extract download mirrors and links"""
        
        # Clear existing mirrors
        game.download_mirrors.all().delete()
        
        order = 0
        
        # Find all links in the content
        all_links = soup.find_all('a')
        
        for link in all_links:
            href = link.get('href', '')
            text = link.get_text().strip().lower()
            
            if not href:
                continue
            
            # Detect torrent links
            if 'magnet:' in href:
                DownloadMirror.objects.create(
                    game=game,
                    mirror_type='magnet',
                    filehoster='multiupload',
                    magnet_link=href,
                    notes=text[:500] if text else '',
                    order=order
                )
                order += 1
                continue
            
            # Detect torrent sites
            if any(site in href.lower() for site in ['1337x', 'rutor', 'tapochek']):
                filehoster = '1337x' if '1337x' in href else 'rutor' if 'rutor' in href else 'tapochek'
                DownloadMirror.objects.create(
                    game=game,
                    mirror_type='torrent',
                    filehoster=filehoster,
                    torrent_url=href,
                    notes=text[:500] if text else '',
                    order=order
                )
                order += 1
                continue
            
            # Detect direct download links
            if any(host in href.lower() for host in ['datanodes', 'fuckingfast', 'upload', 'mega', 'gofile']):
                filehoster = 'multiupload'
                if 'datanodes' in href.lower():
                    filehoster = 'datanodes'
                elif 'fuckingfast' in href.lower():
                    filehoster = 'fuckingfast'
                
                DownloadMirror.objects.create(
                    game=game,
                    mirror_type='direct',
                    filehoster=filehoster,
                    parts=[href],
                    notes=text[:500] if text else '',
                    order=order
                )
                order += 1
        
        if order > 0:
            self.stdout.write(f'  - Found {order} download mirrors')

    def parse_date(self, date_str):
        """Parse WordPress date string to timezone-aware datetime"""
        if not date_str:
            return timezone.now()
        try:
            # Parse the date string
            dt = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
            # Make it timezone-aware
            return timezone.make_aware(dt, pytz.UTC)
        except Exception:
            return timezone.now()

    def log_error(self, post, error):
        """Log scraping error"""
        try:
            title = post.get('title', {}).get('rendered', 'Unknown')
            title = BeautifulSoup(title, 'html.parser').get_text().strip()
            
            ScrapingLog.objects.create(
                status='error',
                message=f"Error processing: {title[:200]}",
                page_url=post.get('link', '')[:1000],
                error_details=str(error)[:2000]
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error logging error: {e}'))