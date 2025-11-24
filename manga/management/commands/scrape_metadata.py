from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.utils import timezone
from manga.models import Manga, MangaCategory
import requests
from datetime import datetime
import time

class Command(BaseCommand):
    help = 'Scrape manga from WordPress JSON API'

    def add_arguments(self, parser):
        parser.add_argument('--url', type=str, default='https://manhuaplus.com', help='Base site URL')
        parser.add_argument('--per-page', type=int, default=100, help='Posts per page')
        parser.add_argument('--max-pages', type=int, default=10, help='Maximum pages to fetch')
        parser.add_argument('--post-type', type=str, default='posts', help='WordPress post type (posts/manga/etc)')

    def handle(self, *args, **options):
        base_url = options['url'].rstrip('/')
        per_page = options['per_page']
        max_pages = options['max_pages']
        post_type = options['post_type']
        
        self.stdout.write(self.style.SUCCESS(f"\n🚀 Starting manga scrape from {base_url}"))
        self.stdout.write(f"📚 Posts per page: {per_page}")
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        })
        
        total_processed = 0
        
        for page in range(1, max_pages + 1):
            # Try different API endpoints
            api_endpoints = [
                f'{base_url}/wp-json/wp/v2/{post_type}?per_page={per_page}&page={page}',
                f'{base_url}/wp-json/wp/v2/manga?per_page={per_page}&page={page}',
                f'{base_url}/wp-json/wp/v2/posts?per_page={per_page}&page={page}&categories=manga',
            ]
            
            posts = None
            for api_url in api_endpoints:
                try:
                    self.stdout.write(f"🌐 Fetching page {page}...")
                    response = session.get(api_url, timeout=30)
                    
                    if response.status_code == 200:
                        posts = response.json()
                        if posts:
                            break
                    elif response.status_code == 400:
                        self.stdout.write(self.style.WARNING(f"✅ All pages processed (invalid page number)."))
                        return
                        
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"⚠️  Error with {api_url}: {e}"))
                    continue
            
            if not posts:
                self.stdout.write(self.style.WARNING(f"⚠️  No data found on page {page}"))
                break
            
            self.stdout.write(f"📦 Processing {len(posts)} posts from page {page}")
            
            for post in posts:
                try:
                    # Skip non-manga posts
                    title = post.get('title', {}).get('rendered', '').strip()
                    if not title or len(title) < 3:
                        continue
                    
                    self.stdout.write(f"📖 Processing: {title}")
                    
                    # Extract data
                    wp_post_id = post.get('id')
                    slug = post.get('slug', slugify(title))
                    
                    # Get content and excerpt
                    content = post.get('content', {}).get('rendered', '')
                    excerpt = post.get('excerpt', {}).get('rendered', '')
                    description = excerpt if excerpt else content[:500]
                    
                    # Clean HTML from description
                    from bs4 import BeautifulSoup
                    description = BeautifulSoup(description, 'html.parser').get_text().strip()
                    
                    # Get featured media URL
                    cover_url = ''
                    featured_media = post.get('featured_media')
                    if featured_media:
                        try:
                            media_response = session.get(
                                f"{base_url}/wp-json/wp/v2/media/{featured_media}",
                                timeout=10
                            )
                            if media_response.status_code == 200:
                                media_data = media_response.json()
                                cover_url = media_data.get('source_url', '')
                        except:
                            pass
                    
                    # Get meta data
                    meta_title = post.get('yoast_head_json', {}).get('og_title', title)
                    meta_description = post.get('yoast_head_json', {}).get('og_description', description)
                    
                    # Parse dates
                    wp_date = None
                    wp_modified = None
                    try:
                        date_str = post.get('date')
                        if date_str:
                            wp_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        
                        modified_str = post.get('modified')
                        if modified_str:
                            wp_modified = datetime.fromisoformat(modified_str.replace('Z', '+00:00'))
                    except:
                        pass
                    
                    # Create or update manga
                    manga, created = Manga.objects.update_or_create(
                        wp_post_id=wp_post_id,
                        defaults={
                            'title': title,
                            'slug': slug,
                            'description': description,
                            'cover_url': cover_url,
                            'wp_link': post.get('link', ''),
                            'wp_author_id': post.get('author'),
                            'wp_featured_media': featured_media,
                            'wp_date': wp_date,
                            'wp_modified': wp_modified,
                            'meta_title': meta_title,
                            'meta_description': meta_description,
                            'is_active': True,
                            'status': 'ongoing',
                        }
                    )
                    
                    if created:
                        self.stdout.write(self.style.SUCCESS(f"✅ Created new manga: {title}"))
                    else:
                        self.stdout.write(f"✏️  Updated existing manga: {title}")
                    
                    total_processed += 1
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"❌ Error processing post: {e}"))
                    continue
            
            # Small delay between pages
            time.sleep(1)
        
        self.stdout.write(self.style.SUCCESS(f"\n🎉 Scraping complete! Processed {total_processed} pages"))
        self.stdout.write(f"📊 Total manga in database: {Manga.objects.count()}")