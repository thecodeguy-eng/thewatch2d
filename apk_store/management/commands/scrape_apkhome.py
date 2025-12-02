from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.db import connection, reset_queries
from django.db.models import Q
from apk_store.models import APK, Category, Screenshot
from bs4 import BeautifulSoup
import re
import time
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class Command(BaseCommand):
    help = 'Scrape APKs with smart deduplication by base game title'

    def add_arguments(self, parser):
        parser.add_argument('--max-items', type=int, default=100, help='Max NEW unique games')
        parser.add_argument('--start-page', type=int, default=1, help='Starting page')
        parser.add_argument('--delay-min', type=float, default=3.0, help='Min delay')
        parser.add_argument('--delay-max', type=float, default=7.0, help='Max delay')
        parser.add_argument('--keep-versions', action='store_true', help='Keep multiple versions of same game')

    def create_robust_session(self):
        """Create session with retries and better headers"""
        session = requests.Session()
        
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        return session

    def normalize_game_title(self, title):
        """
        Extract base game name by removing version numbers and mod info
        Example: "Minecraft 1.21.60.2 MOD" -> "minecraft"
        """
        # Convert to lowercase
        base = title.lower()
        
        # Remove version numbers (e.g., 1.21.60.2, v1.2.3, etc.)
        base = re.sub(r'\b\d+\.\d+[.\d]*\b', '', base)
        base = re.sub(r'\bv\d+[.\d]*\b', '', base)
        
        # Remove mod/status keywords
        keywords = ['mod', 'apk', 'premium', 'pro', 'unlocked', 'full', 'paid', 
                   'latest', 'update', 'new', 'free', 'hack', 'cheat']
        for kw in keywords:
            base = re.sub(r'\b' + kw + r'\b', '', base)
        
        # Clean up whitespace and special chars
        base = re.sub(r'[^\w\s]', ' ', base)
        base = re.sub(r'\s+', ' ', base).strip()
        
        return base

    def is_duplicate_game(self, title, existing_titles, existing_normalized):
        """Check if this is a duplicate game by comparing normalized titles"""
        normalized = self.normalize_game_title(title)
        
        if not normalized:
            return False
        
        # Check if this normalized title already exists
        if normalized in existing_normalized:
            return True
        
        # Also check for very similar titles (fuzzy match)
        words = set(normalized.split())
        if len(words) < 2:  # Single word titles, be strict
            return normalized in existing_normalized
        
        # For multi-word titles, check if major words match
        for existing_norm in existing_normalized:
            existing_words = set(existing_norm.split())
            if len(words) < 2 or len(existing_words) < 2:
                continue
            
            # If 80% of words match, consider it duplicate
            common = words.intersection(existing_words)
            if len(common) >= max(len(words), len(existing_words)) * 0.8:
                return True
        
        return False

    def get_page_with_retry(self, session, url, max_retries=3):
        """Fetch page with retries"""
        for attempt in range(max_retries):
            try:
                response = session.get(url, timeout=30, allow_redirects=True)
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 404:
                    return None
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    self.stdout.write(self.style.ERROR(f"❌ Failed: {e}"))
                else:
                    time.sleep(3 * (attempt + 1))
        
        return False

    def extract_apk_links(self, soup):
        """Extract APK links"""
        apk_links = set()
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').strip()
            
            if 'apkhome.net' not in href:
                continue
            
            if not any(p in href for p in ['-apk', '-mod', '/apk/', '/mod/']):
                continue
            
            skip = ['/category/', '/tag/', '/author/', '/page/', '/wp-', 
                   '/about', '/contact', '/privacy', '/terms', '/dmca', '/#']
            
            if any(s in href for s in skip):
                continue
            
            if not href.startswith('http'):
                if href.startswith('//'):
                    href = 'https:' + href
                elif href.startswith('/'):
                    href = 'https://apkhome.net' + href
                else:
                    href = 'https://apkhome.net/' + href
            
            apk_links.add(href.rstrip('/'))
        
        return list(apk_links)

    def scrape_apk_page(self, session, url):
        """Scrape individual APK page"""
        response = self.get_page_with_retry(session, url)
        
        if not response or response is None or response is False:
            return None
        
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Title
            title_elem = soup.find('h1')
            if not title_elem:
                return None
            
            title = title_elem.get_text().strip()
            
            # Extract mod features
            mod_features = ''
            for pattern in [r'\[(.*?)\]', r'\((.*?MOD.*?)\)']:
                match = re.search(pattern, title, re.IGNORECASE)
                if match:
                    mod_features = match.group(1)
                    break
            
            # Clean title but keep version
            clean_title = re.sub(r'\s*[\[\(].*?[\]\)]\s*', ' ', title)
            clean_title = re.sub(r'\s*(MOD|APK|Mod|Apk|MODDED)\s*', ' ', clean_title, flags=re.I)
            clean_title = re.sub(r'\s+', ' ', clean_title).strip()[:255]
            
            if not clean_title:
                return None
            
            # Icon
            icon_url = ''
            meta_img = soup.find('meta', property='og:image')
            if meta_img:
                icon_url = meta_img.get('content', '').strip()
            
            # Description
            description = ''
            meta_desc = soup.find('meta', property='og:description')
            if meta_desc:
                description = meta_desc.get('content', '').strip()[:5000]
            
            # Version & Size
            all_text = soup.get_text()
            
            version = ''
            match = re.search(r'Version[:\s]+v?([0-9]+\.[0-9]+(?:\.[0-9]+)*)', all_text, re.I)
            if match:
                version = match.group(1)
            
            size = ''
            match = re.search(r'Size[:\s]+(\d+(?:\.\d+)?)\s*(MB|GB)', all_text, re.I)
            if match:
                size = f"{match.group(1)} {match.group(2).upper()}"
            
            # Type
            apk_type = 'game'
            if '/app' in url.lower() and '/game' not in url.lower():
                apk_type = 'app'
            
            # Status
            combined = (title + ' ' + mod_features).lower()
            if 'mod' in combined:
                status = 'modded'
            elif 'premium' in combined:
                status = 'premium'
            elif 'pro' in combined:
                status = 'pro'
            else:
                status = 'original'
            
            return {
                'url': url,
                'title': clean_title,
                'type': apk_type,
                'icon_url': icon_url,
                'description': description,
                'version': version,
                'size': size,
                'status': status,
                'mod_features': mod_features,
                'download_url': url,
            }
            
        except Exception as e:
            return None

    def handle(self, *args, **options):
        max_items = options['max_items']
        start_page = options['start_page']
        delay_min = options['delay_min']
        delay_max = options['delay_max']
        keep_versions = options['keep_versions']
        
        session = self.create_robust_session()
        
        self.stdout.write(self.style.SUCCESS("\n" + "="*70))
        self.stdout.write(self.style.SUCCESS("🚀 SMART APK SCRAPER - UNIQUE GAMES ONLY"))
        self.stdout.write(self.style.SUCCESS("="*70))
        self.stdout.write(f"🎯 Target: {max_items} unique games")
        self.stdout.write(f"📄 Start: Page {start_page}")
        self.stdout.write(f"🔄 Multiple versions: {'YES' if keep_versions else 'NO (unique games only)'}")
        self.stdout.write(f"⏱️ Delay: {delay_min}-{delay_max}s\n")
        
        # Get existing games
        existing_apks = APK.objects.all()
        existing_urls = set(apk.source_url for apk in existing_apks)
        existing_titles = [apk.title for apk in existing_apks]
        existing_normalized = set(self.normalize_game_title(title) for title in existing_titles)
        
        self.stdout.write(f"📊 Existing: {len(existing_urls)} APKs, {len(existing_normalized)} unique games\n")
        
        created = 0
        skipped_duplicate_game = 0
        skipped_duplicate_url = 0
        skipped_error = 0
        current_page = start_page
        session_urls = set()
        session_normalized = set()
        consecutive_duplicate_pages = 0
        
        while created < max_items and consecutive_duplicate_pages < 5:
            self.stdout.write(f"\n{'='*70}")
            self.stdout.write(f"📋 PAGE {current_page} (Created: {created}/{max_items})")
            self.stdout.write(f"{'='*70}")
            
            # Refresh connection
            if current_page % 10 == 0:
                try:
                    reset_queries()
                    connection.close()
                except:
                    pass
            
            # Get page
            url = 'https://apkhome.net/' if current_page == 1 else f'https://apkhome.net/page/{current_page}/'
            response = self.get_page_with_retry(session, url)
            
            if response is None:
                self.stdout.write(self.style.WARNING("❌ Page not found"))
                break
            
            if not response:
                current_page += 1
                time.sleep(random.uniform(delay_min, delay_max))
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            apk_links = self.extract_apk_links(soup)
            
            if not apk_links:
                self.stdout.write(self.style.WARNING("⚠️ No links found"))
                current_page += 1
                time.sleep(random.uniform(delay_min, delay_max))
                continue
            
            # Filter new URLs
            new_urls = [u for u in apk_links if u not in session_urls and u not in existing_urls]
            
            self.stdout.write(f"📊 Found {len(apk_links)} links, {len(new_urls)} new URLs")
            
            if not new_urls:
                consecutive_duplicate_pages += 1
                self.stdout.write(f"⏭️ All URLs seen before ({consecutive_duplicate_pages}/5)")
                current_page += 1
                time.sleep(random.uniform(delay_min, delay_max))
                continue
            
            consecutive_duplicate_pages = 0
            page_created = 0
            
            # Process new URLs
            for idx, apk_url in enumerate(new_urls[:30], 1):
                if created >= max_items:
                    break
                
                session_urls.add(apk_url)
                
                self.stdout.write(f"\n[{idx}/{len(new_urls)}] {apk_url.split('/')[-1][:45]}")
                
                apk_data = self.scrape_apk_page(session, apk_url)
                
                if not apk_data:
                    skipped_error += 1
                    self.stdout.write("   ⏭️ Parse error")
                    time.sleep(random.uniform(delay_min * 0.5, delay_max * 0.5))
                    continue
                
                # Check if URL already exists
                if APK.objects.filter(source_url=apk_data['url']).exists():
                    skipped_duplicate_url += 1
                    self.stdout.write(f"   ⏭️ URL exists")
                    existing_urls.add(apk_data['url'])
                    continue
                
                # Check if game already exists (unless keeping versions)
                if not keep_versions:
                    normalized = self.normalize_game_title(apk_data['title'])
                    
                    if self.is_duplicate_game(apk_data['title'], existing_titles, existing_normalized):
                        skipped_duplicate_game += 1
                        session_normalized.add(normalized)
                        self.stdout.write(f"   🔄 Duplicate game: '{normalized}'")
                        continue
                
                try:
                    # Create new APK
                    apk = APK.objects.create(
                        source_url=apk_data['url'],
                        title=apk_data['title'],
                        apk_type=apk_data['type'],
                        description=apk_data.get('description', ''),
                        icon_url=apk_data.get('icon_url', ''),
                        version=apk_data.get('version', ''),
                        size=apk_data.get('size', ''),
                        status=apk_data['status'],
                        mod_features=apk_data.get('mod_features', ''),
                        download_url=apk_data['download_url'],
                        is_active=True,
                    )
                    
                    created += 1
                    page_created += 1
                    existing_urls.add(apk_data['url'])
                    existing_titles.append(apk_data['title'])
                    existing_normalized.add(self.normalize_game_title(apk_data['title']))
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"   ✅ CREATED ({created}/{max_items}): {apk_data['title'][:40]}"
                    ))
                    
                except Exception as e:
                    skipped_error += 1
                    self.stdout.write(self.style.ERROR(f"   ❌ DB error: {e}"))
                
                time.sleep(random.uniform(delay_min, delay_max))
            
            self.stdout.write(f"\n📊 Page summary: {page_created} created, {len(new_urls) - page_created} skipped")
            
            current_page += 1
            time.sleep(random.uniform(delay_min * 1.5, delay_max * 1.5))
        
        # Final stats
        self.stdout.write(self.style.SUCCESS(f"\n{'='*70}"))
        self.stdout.write(self.style.SUCCESS("🎉 SCRAPING COMPLETED!"))
        self.stdout.write(self.style.SUCCESS(f"{'='*70}"))
        self.stdout.write(self.style.SUCCESS(f"✅ Created: {created} unique games"))
        self.stdout.write(f"🔄 Skipped (duplicate game): {skipped_duplicate_game}")
        self.stdout.write(f"⏭️ Skipped (duplicate URL): {skipped_duplicate_url}")
        self.stdout.write(f"❌ Skipped (errors): {skipped_error}")
        self.stdout.write(f"📄 Pages processed: {current_page - start_page}\n")


# # Get 200 unique games, starting fresh
# python manage.py scrape_apkhome --max-items 200 --start-page 1 --delay-min 4 --delay-max 8

# # Get 50 unique games with slower scraping
# python manage.py scrape_apkhome --max-items 50 --delay-min 5 --delay-max 10

# # If you DO want multiple versions (e.g., different mods)
# python manage.py scrape_apkhome --max-items 100 --keep-versions