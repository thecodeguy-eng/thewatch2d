from django.core.management.base import BaseCommand
from django.utils.text import slugify
from manga.models import Manga, Chapter, MangaCategory, MangaPage
from django.db import models
from bs4 import BeautifulSoup
import re
import time
import random
import cloudscraper
import json
from datetime import datetime

class Command(BaseCommand):
    help = 'Scrape manga from ManhuaPlus with enhanced cover extraction'

    def add_arguments(self, parser):
        parser.add_argument('--max-manga', type=int, default=None, help='Max manga to scrape (None = all)')
        parser.add_argument('--max-chapters', type=int, default=9999, help='Max chapters per manga')
        parser.add_argument('--start-page', type=int, default=1, help='Starting page')
        parser.add_argument('--delay-min', type=float, default=2.0, help='Min delay between requests')
        parser.add_argument('--delay-max', type=float, default=4.0, help='Max delay between requests')
        parser.add_argument('--update-covers-only', action='store_true', help='Only update covers for existing manga')
        parser.add_argument('--fix-missing-covers', action='store_true', help='Fix covers for manga without them')

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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        })
        return scraper

    def extract_cover_url(self, img):
        """Extract cover URL from img element - ENHANCED VERSION"""
        if not img:
            return None
        
        # Try data-src first (lazy loading), then src
        url = img.get('data-src') or img.get('data-lazy-src') or img.get('data-original') or img.get('src')
        
        if url:
            # Skip placeholder images
            if any(skip in url.lower() for skip in ['dflazy', 'placeholder', 'loading', 'icon', 'logo', 'avatar']):
                return None
            
            # Fix protocol-relative URLs
            if url.startswith('//'):
                url = 'https:' + url
            
            # Must be valid image URL from wp-content/uploads
            if url.startswith('http') and 'wp-content/uploads' in url:
                return url
        
        return None

    def scrape_cover_with_retry(self, scraper, manga_url, manga_slug):
        """
        Enhanced cover scraping with multiple strategies
        This combines the shell script logic with retry mechanisms
        """
        cover_url = None
        
        # Build list of URLs to try
        urls_to_try = [
            manga_url,  # Original URL
            f'https://manhuaplus.com/manga/{manga_slug}/',  # Constructed URL
        ]
        
        for url in urls_to_try:
            if cover_url:
                break
            
            try:
                self.stdout.write(f"      🔍 Searching for cover at: {url[:60]}...")
                response = scraper.get(url, timeout=15)
                
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # STRATEGY 1: Direct selectors (HIGHEST PRIORITY)
                cover_selectors = [
                    '.summary_image img',
                    '.tab-summary img',
                    'div.summary_image img',
                    'img[data-src*="wp-content/uploads"]',
                ]
                
                for selector in cover_selectors:
                    if cover_url:
                        break
                    img = soup.select_one(selector)
                    if img:
                        extracted = self.extract_cover_url(img)
                        if extracted:
                            cover_url = extracted
                            self.stdout.write(self.style.SUCCESS(f"      ✅ Cover found: {cover_url[:50]}..."))
                            break
                
                # STRATEGY 2: Scan all images with data-src
                if not cover_url:
                    all_imgs = soup.select('img[data-src]')
                    for img in all_imgs:
                        extracted = self.extract_cover_url(img)
                        if extracted:
                            # Check if it looks like a cover (has size indicators)
                            if any(s in extracted for s in ['193x278', '300x428', 'thumb', 'cover', '-scaled']):
                                cover_url = extracted
                                self.stdout.write(self.style.SUCCESS(f"      ✅ Cover found (fallback): {cover_url[:50]}..."))
                                break
                
                # STRATEGY 3: Check regular src attributes as last resort
                if not cover_url:
                    all_imgs = soup.select('img[src*="wp-content/uploads"]')
                    for img in all_imgs:
                        src = img.get('src', '')
                        if src and 'wp-content/uploads' in src:
                            if any(s in src for s in ['193x278', '300x428', 'cover']):
                                if not any(skip in src.lower() for skip in ['icon', 'logo', 'avatar']):
                                    cover_url = src
                                    self.stdout.write(self.style.SUCCESS(f"      ✅ Cover found (src): {cover_url[:50]}..."))
                                    break
                
                if cover_url:
                    break
                    
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"      ⚠️ Error fetching cover: {e}"))
                continue
        
        return cover_url

    def try_wordpress_api(self, scraper, page=1, per_page=100):
        """Try to fetch manga from WordPress REST API"""
        api_urls = [
            f'https://manhuaplus.com/wp-json/wp/v2/posts?per_page={per_page}&page={page}',
            f'https://manhuaplus.com/wp-json/wp/v2/manga?per_page={per_page}&page={page}',
        ]
        
        for api_url in api_urls:
            try:
                self.stdout.write(f"🔎 Trying WordPress API: {api_url}")
                response = scraper.get(api_url, timeout=20)
                
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        self.stdout.write(self.style.SUCCESS(f"✅ Found {len(data)} items via API"))
                        return data
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ API error: {e}"))
                continue
        
        return None

    def get_manga_list(self, scraper, page=1):
        """Get list of manga from various sources"""
        # Try WordPress API first
        api_data = self.try_wordpress_api(scraper, page)
        if api_data:
            manga_links = []
            for post in api_data:
                if 'link' in post:
                    manga_links.append(post['link'])
            if manga_links:
                return manga_links
        
        # Fallback to HTML scraping
        urls = [
            f'https://manhuaplus.com/page/{page}/',
            f'https://manhuaplus.com/manga-list/page/{page}/',
            'https://manhuaplus.com/genres/manhua/',
        ]
        
        for url in urls:
            try:
                self.stdout.write(f"🌐 Trying: {url}")
                response = scraper.get(url, timeout=20)
                
                if response.status_code == 200:
                    self.stdout.write(self.style.SUCCESS(f"✅ Successfully accessed {url}"))
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    manga_links = []
                    
                    # Try different selectors
                    selectors = [
                        'article.item-summary a[href*="/manga/"]',
                        '.page-item-detail a',
                        'article a[href*="/manga/"]',
                        '.manga-item a',
                        '.post-title a',
                        'h3 a[href*="/manga/"]',
                        'h2 a[href*="/manga/"]',
                    ]
                    
                    for selector in selectors:
                        links = soup.select(selector)
                        if links:
                            for link in links:
                                href = link.get('href', '')
                                if href and '/manga/' in href and '/chapter' not in href:
                                    base_url = href.split('/chapter')[0]
                                    if base_url not in manga_links:
                                        manga_links.append(base_url)
                    
                    if manga_links:
                        self.stdout.write(self.style.SUCCESS(f"✅ Found {len(manga_links)} manga links"))
                        return list(set(manga_links))
                    
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Error with {url}: {e}"))
                continue
        
        return []

    def scrape_manga_page(self, scraper, manga_url):
        """Scrape individual manga page to get chapters and cover"""
        try:
            self.stdout.write(f"\n📖 Scraping manga: {manga_url}")
            response = scraper.get(manga_url, timeout=20)
            
            if response.status_code != 200:
                self.stdout.write(self.style.ERROR(f"❌ Failed to access {manga_url}"))
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            manga_data = {
                'url': manga_url,
                'chapters': []
            }
            
            # Get manga title
            title_selectors = [
                'h1.entry-title',
                '.post-title h1',
                'h1',
                '.manga-title',
            ]
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
            manga_data['slug'] = slugify(manga_title)
            self.stdout.write(f"   📚 Title: {manga_title}")
            
            # ===== ENHANCED COVER EXTRACTION =====
            cover_url = self.scrape_cover_with_retry(scraper, manga_url, manga_data['slug'])
            
            if cover_url:
                manga_data['cover'] = cover_url
            else:
                self.stdout.write(self.style.WARNING("   ⚠️ No cover found after all attempts"))
            
            # Get description
            desc_selectors = [
                '.summary__content p',
                '.manga-summary',
                '.description-summary .summary__content',
                '.entry-content p',
            ]
            for selector in desc_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    desc_text = desc_elem.get_text().strip()
                    if len(desc_text) > 20:
                        manga_data['description'] = desc_text[:500]
                        break
            
            # Get chapters
            chapter_selectors = [
                '.wp-manga-chapter a',
                '.listing-chapters_wrap li a',
                '.chapter-list a',
                'ul.main li a',
                'li.wp-manga-chapter a',
            ]
            
            for selector in chapter_selectors:
                chapter_links = soup.select(selector)
                if chapter_links:
                    self.stdout.write(f"   📖 Found {len(chapter_links)} chapters")
                    
                    for link in chapter_links[:self.max_chapters]:
                        chapter_url = link.get('href', '')
                        chapter_text = link.get_text().strip()
                        
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
            
            # Try script tags first
            script_tags = soup.find_all('script')
            for script in script_tags:
                script_text = script.string if script.string else ''
                if 'images' in script_text.lower() or 'pages' in script_text.lower():
                    img_matches = re.findall(r'https?://[^\s"\']+\.(?:jpg|jpeg|png|webp|gif)', script_text)
                    if img_matches:
                        for idx, img_url in enumerate(img_matches, 1):
                            if not any(skip in img_url.lower() for skip in ['icon', 'logo', 'ad', 'banner']):
                                pages.append({
                                    'page_number': idx,
                                    'image_url': img_url.strip(),
                                })
                        if pages:
                            self.stdout.write(f"      ✅ Found {len(pages)} pages from JS")
                            return pages
            
            # Fallback to HTML selectors
            image_selectors = [
                '.reading-content img',
                '#readerarea img',
                '.chapter-content img',
                '.page-break img',
                '.entry-content img',
                'div[id*="chapter"] img',
                'div[class*="chapter"] img',
            ]
            
            for selector in image_selectors:
                images = soup.select(selector)
                if images:
                    for idx, img in enumerate(images, 1):
                        img_url = img.get('data-src') or img.get('src')
                        if img_url and img_url.startswith('http'):
                            pages.append({
                                'page_number': idx,
                                'image_url': img_url,
                            })
                    if pages:
                        break
            
            # Remove duplicates
            seen = set()
            unique_pages = []
            for page in pages:
                if page['image_url'] not in seen:
                    seen.add(page['image_url'])
                    unique_pages.append(page)
            
            self.stdout.write(f"      ✅ Found {len(unique_pages)} unique pages")
            return unique_pages
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"      ⚠️ Error: {e}"))
            return []

    def fix_missing_covers(self, scraper, delay_min, delay_max):
        """Fix covers for existing manga without covers"""
        self.stdout.write(self.style.SUCCESS("\n🎨 FIXING MISSING COVERS FOR EXISTING MANGA\n"))
        
        manga_list = Manga.objects.filter(cover_url__in=['', None]).order_by('id')
        total = manga_list.count()
        
        self.stdout.write(f"📊 Found {total} manga without covers")
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS("✅ All manga have covers!"))
            return
        
        updated = 0
        failed = 0
        
        for idx, manga in enumerate(manga_list, 1):
            self.stdout.write(f"\n[{idx}/{total}] 📖 {manga.title}")
            
            # Try to scrape cover
            cover_url = self.scrape_cover_with_retry(scraper, manga.wp_link or f'https://manhuaplus.com/manga/{manga.slug}/', manga.slug)
            
            if cover_url:
                manga.cover_url = cover_url
                manga.save(update_fields=['cover_url'])
                updated += 1
                self.stdout.write(self.style.SUCCESS(f"   ✅ Cover updated!"))
            else:
                failed += 1
                self.stdout.write(self.style.WARNING(f"   ❌ No cover found"))
            
            # Rate limiting
            if idx < total:
                delay = random.uniform(delay_min, delay_max)
                time.sleep(delay)
        
        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS("🎉 COVER FIX COMPLETED!"))
        self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
        self.stdout.write(f"✅ Updated: {updated}")
        self.stdout.write(f"❌ Failed: {failed}")
        self.stdout.write(f"📈 Success rate: {(updated / total * 100):.1f}%\n")

    def handle(self, *args, **options):
        self.max_chapters = options['max_chapters']
        max_manga = options['max_manga']  # Can be None for unlimited
        start_page = options['start_page']
        delay_min = options['delay_min']
        delay_max = options['delay_max']
        update_covers_only = options['update_covers_only']
        fix_missing_covers = options['fix_missing_covers']
        
        scraper = self.create_scraper()
        
        # If fix_missing_covers flag is set, only fix covers
        if fix_missing_covers:
            self.fix_missing_covers(scraper, delay_min, delay_max)
            return
        
        self.stdout.write(self.style.SUCCESS("\n🚀 Starting ManhuaPlus Scraper (Enhanced Cover Detection)...\n"))
        
        if max_manga is None:
            self.stdout.write(self.style.WARNING("⚠️ MAX MANGA = UNLIMITED - Will scrape everything!"))
        else:
            self.stdout.write(f"📊 Max manga to scrape: {max_manga}")
        
        # Process stats
        processed = 0
        covers_found = 0
        covers_updated = 0
        current_page = start_page
        processed_urls = set()  # Track processed URLs to avoid duplicates
        
        # Process page by page
        while True:
            self.stdout.write(f"\n{'='*70}")
            self.stdout.write(f"📋 FETCHING MANGA LIST FROM PAGE {current_page}")
            self.stdout.write(f"{'='*70}\n")
            
            manga_links = self.get_manga_list(scraper, current_page)
            
            if not manga_links:
                self.stdout.write(self.style.WARNING(f"⚠️ No manga found on page {current_page}, stopping..."))
                break
            
            # Remove duplicates from this page and filter already processed
            unique_links = []
            for link in manga_links:
                if link not in processed_urls:
                    unique_links.append(link)
                    processed_urls.add(link)
            
            if not unique_links:
                self.stdout.write(self.style.WARNING(f"⚠️ All manga on page {current_page} already processed, moving to next page..."))
                current_page += 1
                time.sleep(random.uniform(delay_min, delay_max))
                continue
            
            self.stdout.write(self.style.SUCCESS(f"📚 Found {len(unique_links)} new manga on page {current_page}"))
            self.stdout.write(f"🔄 Processing manga from page {current_page}...\n")
            
            # Process each manga from this page immediately
            # Process each manga from this page immediately
            for idx, manga_url in enumerate(unique_links, 1):
                try:
                    self.stdout.write(f"\n[Page {current_page} - Manga {idx}/{len(unique_links)}]")
                    
                    manga_data = self.scrape_manga_page(scraper, manga_url)
                    
                    if not manga_data:
                        continue
                    
                    # Create or update manga
                    manga, created = Manga.objects.get_or_create(
                        title=manga_data['title'],
                        defaults={
                            'slug': manga_data['slug'],
                            'manga_session': f"manga_{manga_data['slug']}",
                            'description': manga_data.get('description', ''),
                            'cover_url': manga_data.get('cover', ''),
                            'status': 'ongoing',
                            'manga_type': 'manhua',
                            'is_active': True,
                        }
                    )
                    
                    if created:
                        self.stdout.write(self.style.SUCCESS(f"   ✅ Created manga: {manga_data['title']}"))
                        if manga_data.get('cover'):
                            covers_found += 1
                            self.stdout.write(f"   🎨 Cover saved!")
                        else:
                            self.stdout.write(self.style.WARNING("   ⚠️ No cover"))
                    else:
                        # Update cover if missing
                        if not manga.cover_url and manga_data.get('cover'):
                            manga.cover_url = manga_data.get('cover')
                            manga.save(update_fields=['cover_url'])
                            covers_updated += 1
                            self.stdout.write(f"   🎨 Cover updated!")
                        self.stdout.write(f"   ℹ️ Manga exists: {manga_data['title']}")
                    
                    # Skip chapters if only updating covers
                    if not update_covers_only:
                        # Process chapters
                        chapters_added = 0
                        for chapter_data in manga_data['chapters']:
                            chapter, ch_created = Chapter.objects.get_or_create(
                                manga=manga,
                                chapter_number=chapter_data['number'],
                                defaults={
                                    'title': f"Chapter {chapter_data['number']}",
                                    'chapter_id': abs(hash(f"{manga.id}_{chapter_data['number']}")) % 2147483647,
                                    'session': f"chapter_{manga.slug}_{str(chapter_data['number']).replace('.', '_')}",
                                    'source_url': chapter_data['url'],
                                    'is_active': True,
                                }
                            )
                            
                            existing_pages = MangaPage.objects.filter(chapter=chapter).count()
                            
                            if existing_pages == 0:
                                self.stdout.write(f"      📥 Fetching Chapter {chapter_data['number']}")
                                
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
                                            self.stdout.write(self.style.WARNING(f"         ⚠️ Page error: {e}"))
                                            continue
                                    
                                    chapter.pages_count = pages_created
                                    chapter.save()
                                    self.stdout.write(f"         💾 Saved {pages_created} pages")
                                    chapters_added += 1
                                
                                time.sleep(random.uniform(delay_min, delay_max))
                            else:
                                self.stdout.write(f"      ℹ️ Chapter {chapter_data['number']} has {existing_pages} pages")
                        
                        # Update manga stats
                        max_chapter = Chapter.objects.filter(manga=manga).aggregate(
                            max_ch=models.Max('chapter_number')
                        )['max_ch'] or 0
                        
                        manga.total_chapters = int(max_chapter)
                        manga.save()
                        
                        if chapters_added > 0:
                            self.stdout.write(self.style.SUCCESS(f"   ✨ Added {chapters_added} new chapters"))
                    
                    processed += 1
                    
                    # Progress update
                    self.stdout.write(self.style.SUCCESS(f"   📊 Progress: {processed} manga processed total"))
                    
                    # Check if we've reached max_manga limit
                    if max_manga and processed >= max_manga:
                        self.stdout.write(self.style.SUCCESS(f"\n✅ Reached max manga limit ({max_manga}), stopping..."))
                        break
                    
                    # Delay before next manga
                    time.sleep(random.uniform(delay_min * 1.5, delay_max * 1.5))
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"❌ Error processing manga: {e}"))
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Check if we've reached max_manga limit
            if max_manga and processed >= max_manga:
                break
            
            # Page completed
            self.stdout.write(self.style.SUCCESS(f"\n✅ Completed page {current_page}"))
            self.stdout.write(f"📊 Page stats: Processed {len(unique_links)} manga from this page")
            self.stdout.write(f"📈 Total progress: {processed} manga processed overall\n")
            
            # Move to next page
            current_page += 1
            time.sleep(random.uniform(delay_min, delay_max))
        
        # Final stats
        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS("🎉 SCRAPING COMPLETED!"))
        self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
        self.stdout.write(f"📊 Total manga processed: {processed}")
        self.stdout.write(f"📄 Pages scraped: {current_page - start_page}")
        self.stdout.write(f"🖼️ New covers found: {covers_found}")
        self.stdout.write(f"🎨 Covers updated: {covers_updated}")
        self.stdout.write(f"📚 Total manga in DB: {Manga.objects.count()}")
        self.stdout.write(f"📖 Total chapters in DB: {Chapter.objects.count()}")
        self.stdout.write(f"📄 Total pages in DB: {MangaPage.objects.count()}\n")