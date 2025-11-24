from django.core.management.base import BaseCommand
from django.utils.text import slugify
from manga.models import Manga, Chapter, MangaCategory, MangaPage
from django.db import models
from bs4 import BeautifulSoup
import re
import time
import random
import cloudscraper
from datetime import datetime

class Command(BaseCommand):
    help = 'Scrape manga from ManhuaPlus'

    def add_arguments(self, parser):
        parser.add_argument('--max-manga', type=int, default=10, help='Max manga to scrape')
        parser.add_argument('--max-chapters', type=int, default=5, help='Max chapters per manga')
        parser.add_argument('--start-page', type=int, default=1, help='Starting page')
        parser.add_argument('--delay-min', type=float, default=3.0, help='Min delay')
        parser.add_argument('--delay-max', type=float, default=6.0, help='Max delay')

    def create_scraper(self):
        """Create cloudscraper with proper headers"""
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        return scraper

    def get_manga_list(self, scraper, page=1):
        """Get list of manga from the homepage or category pages"""
        urls = [
            f'https://manhuaplus.com/page/{page}/',
            'https://manhuaplus.com/genres/manhua/',
            'https://manhuaplus.com/manga-list/',
        ]
        
        for url in urls:
            try:
                self.stdout.write(f"🌐 Trying: {url}")
                response = scraper.get(url, timeout=20)
                
                if response.status_code == 200:
                    self.stdout.write(self.style.SUCCESS(f"✅ Successfully accessed {url}"))
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Find manga links - adjust selectors based on site structure
                    manga_links = []
                    
                    # Try different common selectors
                    selectors = [
                        'article.manga-item a',
                        '.manga-box a',
                        '.post-title a',
                        'h2 a',
                        'h3 a',
                        'a[href*="/manga/"]',
                    ]
                    
                    for selector in selectors:
                        links = soup.select(selector)
                        if links:
                            for link in links:
                                href = link.get('href', '')
                                if href and '/manga/' in href and href not in manga_links:
                                    manga_links.append(href)
                    
                    if manga_links:
                        self.stdout.write(self.style.SUCCESS(f"✅ Found {len(manga_links)} manga links"))
                        return manga_links
                    
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️  Error with {url}: {e}"))
                continue
        
        return []

    def scrape_manga_page(self, scraper, manga_url):
        """Scrape individual manga page to get chapters"""
        try:
            self.stdout.write(f"\n📖 Scraping manga: {manga_url}")
            response = scraper.get(manga_url, timeout=20)
            
            if response.status_code != 200:
                self.stdout.write(self.style.ERROR(f"❌ Failed to access {manga_url}"))
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract manga info
            manga_data = {
                'url': manga_url,
                'chapters': []
            }
            
            # Get manga title
            title_selectors = ['h1', '.manga-title', '.entry-title', 'h1.title']
            manga_title = None
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    manga_title = title_elem.get_text().strip()
                    break
            
            if not manga_title:
                self.stdout.write(self.style.ERROR("❌ Could not find manga title"))
                return None
            
            manga_data['title'] = manga_title
            self.stdout.write(f"   📚 Title: {manga_title}")
            
            # Get cover image
            cover_selectors = ['.manga-cover img', '.summary_image img', '.post-thumb img', 'img.wp-post-image']
            for selector in cover_selectors:
                cover_elem = soup.select_one(selector)
                if cover_elem:
                    manga_data['cover'] = cover_elem.get('src') or cover_elem.get('data-src', '')
                    break
            
            # Get description
            desc_selectors = ['.manga-summary', '.description', '.entry-content', '.summary']
            for selector in desc_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    manga_data['description'] = desc_elem.get_text().strip()[:500]
                    break
            
            # Get chapters
            chapter_selectors = [
                '.chapter-list a',
                '.listing-chapters_wrap a',
                'ul.chapters-list a',
                'a[href*="/chapter-"]',
                '.wp-manga-chapter a',
            ]
            
            for selector in chapter_selectors:
                chapter_links = soup.select(selector)
                if chapter_links:
                    self.stdout.write(f"   📖 Found {len(chapter_links)} chapters")
                    
                    for link in chapter_links[:self.max_chapters]:
                        chapter_url = link.get('href', '')
                        chapter_text = link.get_text().strip()
                        
                        # Extract chapter number
                        chapter_match = re.search(r'chapter[- ]?(\d+(?:\.\d+)?)', chapter_text, re.IGNORECASE)
                        if not chapter_match:
                            chapter_match = re.search(r'chapter[- ]?(\d+(?:\.\d+)?)', chapter_url, re.IGNORECASE)
                        
                        if chapter_match and chapter_url:
                            chapter_num = float(chapter_match.group(1))
                            manga_data['chapters'].append({
                                'number': chapter_num,
                                'url': chapter_url,
                                'title': chapter_text
                            })
                    break
            
            return manga_data
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error scraping manga page: {e}"))
            import traceback
            traceback.print_exc()
            return None

    def scrape_chapter_pages(self, scraper, chapter_url):
        """Scrape chapter to get manga page images"""
        try:
            self.stdout.write(f"      📄 Scraping chapter: {chapter_url}")
            response = scraper.get(chapter_url, timeout=20)
            
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            pages = []
            
            # Find images - try multiple selectors
            image_selectors = [
                '.reading-content img',
                '.chapter-content img',
                '.page-break img',
                '#readerarea img',
                '.entry-content img',
            ]
            
            for selector in image_selectors:
                images = soup.select(selector)
                if images:
                    for idx, img in enumerate(images, 1):
                        img_url = (
                            img.get('data-src') or 
                            img.get('data-lazy-src') or 
                            img.get('src') or 
                            ''
                        ).strip()
                        
                        # Skip small images (ads, icons)
                        if not img_url or any(skip in img_url.lower() for skip in ['icon', 'logo', 'ad', 'banner']):
                            continue
                        
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        
                        pages.append({
                            'page_number': idx,
                            'image_url': img_url,
                        })
                    break
            
            self.stdout.write(f"      ✅ Found {len(pages)} pages")
            return pages
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"      ⚠️  Error: {e}"))
            return []

    def handle(self, *args, **options):
        self.max_chapters = options['max_chapters']
        max_manga = options['max_manga']
        delay_min = options['delay_min']
        delay_max = options['delay_max']
        
        self.stdout.write(self.style.SUCCESS("\n🚀 Starting ManhuaPlus Scraper...\n"))
        
        scraper = self.create_scraper()
        
        # Get manga list
        self.stdout.write("📋 Fetching manga list...")
        manga_links = self.get_manga_list(scraper)
        
        if not manga_links:
            self.stdout.write(self.style.ERROR("❌ Could not find any manga links"))
            self.stdout.write(self.style.WARNING("\n⚠️  The site might have Cloudflare protection."))
            self.stdout.write(self.style.WARNING("Try these alternatives:"))
            self.stdout.write("   1. Use a different manga source")
            self.stdout.write("   2. Manually enter manga URLs in code")
            self.stdout.write("   3. Use selenium/playwright for JS rendering")
            return
        
        # Process each manga
        processed = 0
        for manga_url in manga_links[:max_manga]:
            try:
                # Scrape manga page
                manga_data = self.scrape_manga_page(scraper, manga_url)
                
                if not manga_data:
                    continue
                
                # Create or get manga
                manga, created = Manga.objects.get_or_create(
                    title=manga_data['title'],
                    defaults={
                        'slug': slugify(manga_data['title']),
                        'manga_session': f"manga_{slugify(manga_data['title'])}",
                        'description': manga_data.get('description', ''),
                        'cover_url': manga_data.get('cover', ''),
                        'status': 'ongoing',
                        'manga_type': 'manhua',
                        'is_active': True,
                    }
                )
                
                if created:
                    self.stdout.write(self.style.SUCCESS(f"   ✅ Created manga: {manga_data['title']}"))
                
                # Process chapters
                for chapter_data in manga_data['chapters']:
                    chapter, ch_created = Chapter.objects.get_or_create(
                        manga=manga,
                        chapter_number=chapter_data['number'],
                        defaults={
                            'title': f"Chapter {chapter_data['number']}",
                            'chapter_id': hash(f"{manga.id}_{chapter_data['number']}") % 2147483647,
                            'session': f"chapter_{manga.slug}_{str(chapter_data['number']).replace('.', '_')}",
                            'source_url': chapter_data['url'],
                            'is_active': True,
                        }
                    )
                    
                    if ch_created:
                        self.stdout.write(f"      ✅ Chapter {chapter_data['number']}")
                        
                        # Get chapter pages
                        pages = self.scrape_chapter_pages(scraper, chapter_data['url'])
                        
                        if pages:
                            pages_created = 0
                            for page_data in pages:
                                try:
                                    page, created = MangaPage.objects.get_or_create(
                                        chapter=chapter,
                                        page_number=page_data['page_number'],
                                        defaults={
                                            'image_url': page_data['image_url'],
                                        }
                                    )
                                    if created:
                                        pages_created += 1
                                except Exception as e:
                                    self.stdout.write(self.style.WARNING(f"         ⚠️  Page {page_data['page_number']} error: {e}"))
                                    continue
                            
                            chapter.pages_count = pages_created
                            chapter.save()
                            self.stdout.write(f"         💾 Saved {pages_created} pages to database")
                        else:
                            self.stdout.write(self.style.WARNING(f"         ⚠️  No pages found for chapter {chapter_data['number']}"))
                        
                        # Delay between chapters
                        time.sleep(random.uniform(delay_min, delay_max))
                    else:
                        # Chapter exists, check if it has pages
                        page_count = MangaPage.objects.filter(chapter=chapter).count()
                        if page_count == 0:
                            self.stdout.write(f"      ℹ️  Chapter {chapter_data['number']} exists but has no pages, fetching...")
                            
                            # Get chapter pages
                            pages = self.scrape_chapter_pages(scraper, chapter_data['url'])
                            
                            if pages:
                                pages_created = 0
                                for page_data in pages:
                                    try:
                                        page, created = MangaPage.objects.get_or_create(
                                            chapter=chapter,
                                            page_number=page_data['page_number'],
                                            defaults={
                                                'image_url': page_data['image_url'],
                                            }
                                        )
                                        if created:
                                            pages_created += 1
                                    except Exception as e:
                                        continue
                                
                                chapter.pages_count = pages_created
                                chapter.save()
                                self.stdout.write(f"         💾 Added {pages_created} pages")
                            
                            time.sleep(random.uniform(delay_min, delay_max))
                        else:
                            self.stdout.write(f"      ℹ️  Chapter {chapter_data['number']} already has {page_count} pages")
                
                # Update manga stats
                max_chapter = Chapter.objects.filter(manga=manga).aggregate(
                    max_ch=models.Max('chapter_number')
                )['max_ch'] or 0
                
                manga.total_chapters = int(max_chapter)
                manga.save()
                
                processed += 1
                
                # Delay between manga
                time.sleep(random.uniform(delay_min * 1.5, delay_max * 1.5))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error processing manga: {e}"))
                continue
        
        # Final stats
        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS("🎉 SCRAPING COMPLETED!"))
        self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
        self.stdout.write(f"📊 Manga processed: {processed}")
        self.stdout.write(f"📚 Total manga: {Manga.objects.count()}")
        self.stdout.write(f"📖 Total chapters: {Chapter.objects.count()}")
        self.stdout.write(f"📄 Total pages: {MangaPage.objects.count()}\n")