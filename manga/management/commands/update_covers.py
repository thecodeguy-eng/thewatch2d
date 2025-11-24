from django.core.management.base import BaseCommand
from manga.models import Manga
from bs4 import BeautifulSoup
import cloudscraper
import time
import random


class Command(BaseCommand):
    help = 'Update missing cover images for existing manga'

    def add_arguments(self, parser):
        parser.add_argument('--delay', type=float, default=2.0, help='Delay between requests')
        parser.add_argument('--limit', type=int, default=None, help='Limit number of manga to process')

    def create_scraper(self):
        """Create cloudscraper with proper headers"""
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        scraper.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        })
        return scraper

    def extract_image_url(self, img_element):
        """Extract actual image URL from img element"""
        if not img_element:
            return None
        
        url_attrs = ['data-src', 'data-lazy-src', 'data-original', 'src']
        
        for attr in url_attrs:
            url = img_element.get(attr, '').strip()
            if url:
                # Skip placeholder images
                skip_keywords = ['icon', 'logo', 'ad', 'banner', 'loading', 'placeholder', 'dflazy']
                if any(skip in url.lower() for skip in skip_keywords):
                    continue
                
                # Fix protocol-relative URLs
                if url.startswith('//'):
                    url = 'https:' + url
                
                # Validate it's an image
                if url.startswith('http'):
                    has_ext = any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif'])
                    from_upload = 'wp-content/uploads' in url
                    
                    if has_ext or from_upload:
                        return url
        
        return None

    def get_cover_from_source(self, scraper, manga):
        """Try to get cover from source URL"""
        # Try to construct ManhuaPlus URL
        possible_urls = []
        
        # If manga has wp_link, use that
        if manga.wp_link:
            possible_urls.append(manga.wp_link)
        
        # Try common URL patterns
        slug = manga.slug
        possible_urls.extend([
            f'https://manhuaplus.com/manga/{slug}/',
            f'https://manhuaplus.com/{slug}/',
        ])
        
        for url in possible_urls:
            try:
                self.stdout.write(f"   🌐 Trying: {url}")
                response = scraper.get(url, timeout=15)
                
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Try selectors in priority order
                selectors = [
                    '.summary_image img',
                    '.tab-summary img',
                    'div.summary_image img',
                    'img[data-src*="wp-content/uploads"]',
                ]
                
                for selector in selectors:
                    img = soup.select_one(selector)
                    if img:
                        cover_url = self.extract_image_url(img)
                        if cover_url:
                            self.stdout.write(f"   ✅ Found cover: {cover_url[:60]}...")
                            return cover_url
                
                # Fallback: Try all images with data-src
                all_imgs = soup.select('img[data-src]')
                for img in all_imgs:
                    # Skip small icons
                    if img.get('class') and any(c in str(img.get('class')) for c in ['logo', 'icon', 'avatar']):
                        continue
                    
                    cover_url = self.extract_image_url(img)
                    if cover_url and 'wp-content/uploads' in cover_url:
                        # Check if it looks like a cover (has size info)
                        if any(size in cover_url for size in ['193x278', '300x428', 'cover', 'thumb']):
                            self.stdout.write(f"   ✅ Found cover (fallback): {cover_url[:60]}...")
                            return cover_url
                
                self.stdout.write(self.style.WARNING(f"   ⚠️  No cover found at {url}"))
                
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"   ⚠️  Error: {e}"))
                continue
        
        return None

    def handle(self, *args, **options):
        delay = options['delay']
        limit = options['limit']
        
        self.stdout.write(self.style.SUCCESS("\n🎨 Starting Cover Updater...\n"))
        
        # Find manga without covers
        manga_without_covers = Manga.objects.filter(
            cover_url__in=['', None]
        ).order_by('-id')
        
        if limit:
            manga_without_covers = manga_without_covers[:limit]
        
        total_count = manga_without_covers.count()
        
        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("✅ All manga have covers!"))
            return
        
        self.stdout.write(f"📊 Found {total_count} manga without covers\n")
        
        scraper = self.create_scraper()
        updated = 0
        failed = 0
        
        for idx, manga in enumerate(manga_without_covers, 1):
            try:
                self.stdout.write(f"\n[{idx}/{total_count}] 📖 {manga.title}")
                
                # Get cover from source
                cover_url = self.get_cover_from_source(scraper, manga)
                
                if cover_url:
                    manga.cover_url = cover_url
                    manga.save(update_fields=['cover_url'])
                    updated += 1
                    self.stdout.write(self.style.SUCCESS(f"   ✅ Updated!"))
                else:
                    failed += 1
                    self.stdout.write(self.style.ERROR(f"   ❌ Could not find cover"))
                
                # Delay between requests
                if idx < total_count:
                    time.sleep(delay + random.uniform(0, 1))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ❌ Error: {e}"))
                failed += 1
                continue
        
        # Final report
        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS("🎉 COVER UPDATE COMPLETED!"))
        self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
        self.stdout.write(f"✅ Updated: {updated}")
        self.stdout.write(f"❌ Failed: {failed}")
        self.stdout.write(f"📊 Total processed: {updated + failed}\n")




# manual shell command

# python manage.py shell

# from manga.models import Manga
# from bs4 import BeautifulSoup
# import cloudscraper

# # Create scraper
# scraper = cloudscraper.create_scraper()
# scraper.headers.update({
#     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
# })

# # Get manga without covers
# manga_list = Manga.objects.filter(cover_url__in=['', None])[:5]
# print(f"Found {manga_list.count()} manga without covers\n")

# updated = 0
# for manga in manga_list:
#     print(f"📖 {manga.title}")
    
#     # Try to get the page
#     url = f'https://manhuaplus.com/manga/{manga.slug}/'
#     print(f"   🌐 {url}")
    
#     try:
#         response = scraper.get(url, timeout=15)
#         soup = BeautifulSoup(response.text, 'html.parser')
        
#         # Find cover
#         img = soup.select_one('.summary_image img')
#         if img:
#             cover_url = img.get('data-src') or img.get('src')
#             if cover_url and cover_url.startswith('http'):
#                 manga.cover_url = cover_url
#                 manga.save()
#                 updated += 1
#                 print(f"   ✅ Updated: {cover_url[:60]}...")
#             else:
#                 print(f"   ⚠️  No valid cover URL")
#         else:
#             print(f"   ⚠️  Image not found")
#     except Exception as e:
#         print(f"   ❌ Error: {e}")
    
#     print()

# print(f"\n✅ Updated {updated} manga")