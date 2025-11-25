from django.core.management.base import BaseCommand
from django.utils.text import slugify
from apk_store.models import APK, Category, Screenshot, APKVersion
from bs4 import BeautifulSoup
import re
import time
import random
import requests
from datetime import datetime

class Command(BaseCommand):
    help = 'Scrape Android APKs from APKHome.net'

    def add_arguments(self, parser):
        parser.add_argument('--max-items', type=int, default=9999, help='Max items to scrape')
        parser.add_argument('--type', type=str, choices=['games', 'apps', 'all'], default='all', help='Type to scrape')
        parser.add_argument('--start-page', type=int, default=1, help='Starting page')
        parser.add_argument('--delay-min', type=float, default=2.0, help='Min delay between requests')
        parser.add_argument('--delay-max', type=float, default=5.0, help='Max delay between requests')

    def create_session(self):
        """Create requests session with proper headers"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        return session

    def get_listing_page(self, session, apk_type='all', page=1):
        """Get list of APK URLs from listing page"""
        if page == 1:
            if apk_type == 'games':
                url = 'https://apkhome.net/category/games/'
            elif apk_type == 'apps':
                url = 'https://apkhome.net/category/apps/'
            else:
                url = 'https://apkhome.net/'
        else:
            if apk_type == 'games':
                url = f'https://apkhome.net/category/games/page/{page}/'
            elif apk_type == 'apps':
                url = f'https://apkhome.net/category/apps/page/{page}/'
            else:
                url = f'https://apkhome.net/page/{page}/'
        
        try:
            self.stdout.write(f"\n🌐 Fetching: {url}")
            response = session.get(url, timeout=30)
            
            if response.status_code != 200:
                self.stdout.write(self.style.WARNING(f"⚠️ Status code: {response.status_code}"))
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            apk_links = []
            
            main_content = soup.find('main') or soup.find('body')
            if main_content:
                all_links = main_content.find_all('a', href=True)
                
                for link in all_links:
                    href = link.get('href', '').strip()
                    
                    if 'apkhome.net' not in href:
                        continue
                    
                    if not ('-apk' in href.lower() or '-mod' in href.lower()):
                        continue
                    
                    skip_patterns = [
                        '/category/', '/tag/', '/author/', '/page/', 
                        '/wp-', '/about', '/contact', '/privacy', 
                        '/terms', '/dmca', '/sitemap', '/feed'
                    ]
                    if any(pattern in href for pattern in skip_patterns):
                        continue
                    
                    if not href.startswith('http'):
                        if href.startswith('//'):
                            href = 'https:' + href
                        elif href.startswith('/'):
                            href = 'https://apkhome.net' + href
                        else:
                            href = 'https://apkhome.net/' + href
                    
                    href = href.rstrip('/')
                    apk_links.append(href)
            
            apk_links = list(set(apk_links))
            
            if apk_links:
                self.stdout.write(self.style.SUCCESS(f"   ✅ Found {len(apk_links)} unique APK links"))
                for i, link in enumerate(apk_links[:3], 1):
                    title = link.split('/')[-1].replace('-', ' ').title()[:50]
                    self.stdout.write(f"   [{i}] {title}...")
                return apk_links
            else:
                self.stdout.write(self.style.WARNING("   ⚠️ No APK links found"))
                return []
                    
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Error: {e}"))
            return []

    def extract_icon_url(self, soup, page_url):
        """Extract icon/cover image with multiple fallback strategies"""
        
        # Strategy 1: Meta tags (most reliable)
        meta_selectors = [
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
            'meta[property="og:image:secure_url"]',
        ]
        
        for selector in meta_selectors:
            meta = soup.select_one(selector)
            if meta and meta.get('content'):
                url = meta.get('content').strip()
                if url.startswith('http') and not url.endswith('.svg'):
                    return url
        
        # Strategy 2: Main article/post images
        # Look for featured image, app icon in article
        article_selectors = [
            '.app-icon img',
            '.game-icon img',
            'article .app-icon-img',
            '.entry-thumb img',
            '.featured-image img',
            '.post-thumbnail img',
            '.wp-post-image',
            'article img[width]',  # Images with width attribute
        ]
        
        for selector in article_selectors:
            elem = soup.select_one(selector)
            if elem:
                url = self._extract_img_src(elem)
                if url and self._is_valid_icon(url):
                    return url
        
        # Strategy 3: First large image in main content
        main_content = soup.find('article') or soup.find('main') or soup.find('.entry-content')
        if main_content:
            images = main_content.find_all('img')
            for img in images[:10]:  # Check first 10 images
                url = self._extract_img_src(img)
                if url and self._is_valid_icon(url):
                    # Check dimensions
                    width = self._get_dimension(img, 'width')
                    height = self._get_dimension(img, 'height')
                    
                    # Accept if dimensions are good or unknown
                    if (width >= 150 or height >= 150) or (width == 0 and height == 0):
                        return url
        
        # Strategy 4: JSON-LD structured data
        json_ld = soup.find('script', type='application/ld+json')
        if json_ld:
            try:
                import json
                data = json.loads(json_ld.string)
                if isinstance(data, dict):
                    if 'image' in data:
                        img = data['image']
                        if isinstance(img, str):
                            return img
                        elif isinstance(img, dict) and 'url' in img:
                            return img['url']
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and 'image' in item:
                            img = item['image']
                            if isinstance(img, str):
                                return img
                            elif isinstance(img, dict) and 'url' in img:
                                return img['url']
            except:
                pass
        
        return None

    def _extract_img_src(self, img):
        """Extract image source from img tag with lazy loading support"""
        src_attrs = [
            'data-src',
            'data-lazy-src',
            'data-original',
            'src',
        ]
        
        for attr in src_attrs:
            url = img.get(attr, '').strip()
            if url:
                # Handle srcset format
                if ' ' in url:
                    url = url.split()[0]
                
                # Normalize URL
                if not url.startswith('http'):
                    if url.startswith('//'):
                        url = 'https:' + url
                    elif url.startswith('/'):
                        url = 'https://apkhome.net' + url
                
                return url
        
        # Try srcset as fallback
        srcset = img.get('srcset', '').strip()
        if srcset:
            # Parse srcset and get highest resolution
            entries = srcset.split(',')
            if entries:
                url = entries[-1].strip().split()[0]
                if not url.startswith('http'):
                    if url.startswith('//'):
                        url = 'https:' + url
                    elif url.startswith('/'):
                        url = 'https://apkhome.net' + url
                return url
        
        return None

    def _get_dimension(self, img, attr):
        """Get image dimension safely"""
        try:
            val = img.get(attr, '0')
            if isinstance(val, str):
                val = re.sub(r'[^\d]', '', val)  # Remove non-digits
            return int(val) if val else 0
        except:
            return 0

    def _is_valid_icon(self, url):
        """Check if URL looks like a valid icon/cover image"""
        if not url or not url.startswith('http'):
            return False
        
        # Exclude common non-icon patterns
        exclude_patterns = [
            'logo', 'favicon', 'avatar', 'author',
            'banner', 'header', 'footer', 'sidebar',
            '.svg', '.gif', 'icon-', '-icon.',
            'gravatar', 'emoji'
        ]
        
        url_lower = url.lower()
        for pattern in exclude_patterns:
            if pattern in url_lower:
                return False
        
        return True

    def extract_description(self, soup):
        """Extract description with better cleanup"""
        
        # Try meta description first
        meta_desc = soup.find('meta', {'name': 'description'})
        if not meta_desc:
            meta_desc = soup.find('meta', {'property': 'og:description'})
        
        if meta_desc and meta_desc.get('content'):
            meta_text = meta_desc.get('content').strip()
            if len(meta_text) > 100:
                return meta_text
        
        # Extract from article content
        content_selectors = [
            '.entry-content',
            '.post-content',
            'article .content',
            '.about-content',
            'article',
        ]
        
        desc_elem = None
        for selector in content_selectors:
            desc_elem = soup.select_one(selector)
            if desc_elem:
                break
        
        if not desc_elem:
            return ''
        
        # Remove unwanted elements
        for unwanted in desc_elem.select(
            'script, style, .download-link, .wp-block-button, '
            '.download-button, .install-button, .download-links, '
            'nav, aside, footer, header, .menu, .navigation, '
            '.sidebar, .widget, .related, .comments, .share'
        ):
            unwanted.decompose()
        
        # Extract meaningful paragraphs
        paragraphs = desc_elem.find_all(['p', 'div'], recursive=True)
        desc_parts = []
        
        for p in paragraphs[:15]:  # Check more paragraphs
            text = p.get_text(separator=' ', strip=True)
            
            # Skip short or useless text
            if len(text) < 50:
                continue
            
            # Skip download/button text
            skip_phrases = [
                'download', 'click here', 'get it', 'install',
                'app info', 'additional information', 'mod info',
                'version', 'size:', 'requires android'
            ]
            if any(phrase in text.lower()[:50] for phrase in skip_phrases):
                continue
            
            desc_parts.append(text)
            
            # Stop if we have enough
            if len(' '.join(desc_parts)) > 1000:
                break
        
        description = '\n\n'.join(desc_parts)
        
        # Clean up
        description = re.sub(r'\s+', ' ', description)  # Normalize whitespace
        description = re.sub(r'\n\s*\n', '\n\n', description)  # Clean multiple newlines
        
        return description[:5000] if description else ''

    def extract_download_link(self, soup, session, page_url):
        """Extract the actual download link"""
        download_selectors = [
            'a.download-button',
            'a.btn.primary.install-button',
            'a[href*="dl.apkhome"]',
            'a[href*="dl7.apkhome"]',
            'a[href*="dl8.apkhome"]',
            'a.wp-block-button__link',
            'a.download-btn',
            '.download-links a',
            '.wp-block-buttons a',
            'a[href$=".apk"]',
        ]
        
        for selector in download_selectors:
            link = soup.select_one(selector)
            if link:
                href = link.get('href', '')
                if href:
                    if '.apk' in href.lower() or 'dl' in href:
                        return href if href.startswith('http') else f"https://apkhome.net{href}"
        
        # Fallback: search all links
        all_links = soup.find_all('a', href=True)
        for link in all_links:
            href = link.get('href', '')
            text = link.get_text().strip().lower()
            if ('download' in text or 'get' in text) and ('.apk' in href or 'dl' in href):
                return href if href.startswith('http') else f"https://apkhome.net{href}"
        
        return page_url

    def scrape_apk_page(self, session, apk_url, apk_type_filter='all'):
        """Scrape individual APK page"""
        try:
            self.stdout.write(f"\n🎮 Scraping: {apk_url}")
            response = session.get(apk_url, timeout=30)
            
            if response.status_code != 200:
                self.stdout.write(self.style.WARNING(f"   ⚠️ Status: {response.status_code}"))
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            apk_data = {'url': apk_url}
            
            # ===== TITLE =====
            title_selectors = ['h1.entry-title', 'h1.post-title', 'article h1', 'h1']
            title_elem = None
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    break
            
            if not title_elem:
                self.stdout.write(self.style.WARNING("   ⚠️ No title found"))
                return None
            
            title_text = title_elem.get_text().strip()
            
            # Extract mod features
            mod_patterns = [
                r'\[(.*?)\]',
                r'\((.*?MOD.*?)\)',
                r'MOD\s+(.*?)(?:\||$)',
            ]
            for pattern in mod_patterns:
                mod_match = re.search(pattern, title_text, re.IGNORECASE)
                if mod_match:
                    apk_data['mod_features'] = mod_match.group(1)
                    break
            
            # Clean title
            title_text = re.sub(r'\s*[\[\(].*?[\]\)]\s*', ' ', title_text)
            title_text = re.sub(r'\s*(MOD|APK|Mod|Apk|MODDED|Premium|Pro)\s*', ' ', title_text, flags=re.IGNORECASE)
            title_text = re.sub(r'\s+', ' ', title_text).strip()
            apk_data['title'] = title_text[:255]
            
            self.stdout.write(f"   📱 Title: {apk_data['title']}")
            
            # ===== TYPE DETECTION =====
            apk_data['type'] = 'game'
            
            url_lower = apk_url.lower()
            if '/app' in url_lower and '/game' not in url_lower:
                apk_data['type'] = 'app'
            elif '/game' in url_lower:
                apk_data['type'] = 'game'
            
            cat_links = soup.select('a[rel="category tag"], .category a, .post-categories a')
            category_texts = [cat.get_text().lower().strip() for cat in cat_links]
            
            app_keywords = ['app', 'tool', 'productivity', 'social', 'communication', 
                           'photography', 'video editor', 'music', 'utility', 'lifestyle']
            
            for cat_text in category_texts:
                if any(keyword in cat_text for keyword in app_keywords):
                    if 'game' not in cat_text:
                        apk_data['type'] = 'app'
                        break
            
            game_keywords = ['soccer', 'football', 'tycoon', 'simulator', 'craft', 
                           'battle', 'shooting', 'adventure', 'puzzle', 'racing']
            
            title_lower = title_text.lower()
            if any(keyword in title_lower for keyword in game_keywords):
                apk_data['type'] = 'game'
            
            if apk_type_filter != 'all' and apk_data['type'] != apk_type_filter.rstrip('s'):
                self.stdout.write(self.style.WARNING(f"   ⏭️ Skipping: Type mismatch"))
                return None
            
            self.stdout.write(f"   🎯 Type: {apk_data['type'].upper()}")
            
            # ===== ICON (FIXED) =====
            icon_url = self.extract_icon_url(soup, apk_url)
            if icon_url:
                apk_data['icon_url'] = icon_url
                self.stdout.write(f"   🖼️ Icon: ✓")
            else:
                self.stdout.write(self.style.WARNING(f"   ⚠️ No icon found"))
            
            # ===== DESCRIPTION (FIXED) =====
            description = self.extract_description(soup)
            if description:
                apk_data['description'] = description
                self.stdout.write(f"   📄 Description: {len(description)} chars")
            else:
                self.stdout.write(self.style.WARNING(f"   ⚠️ No description found"))
            
            # ===== VERSION & SIZE =====
            all_text = soup.get_text()
            
            version_patterns = [
                r'Version[:\s]+v?([0-9]+\.[0-9]+(?:\.[0-9]+)*)',
                r'v([0-9]+\.[0-9]+\.[0-9]+)',
            ]
            for pattern in version_patterns:
                match = re.search(pattern, all_text, re.IGNORECASE)
                if match:
                    apk_data['version'] = match.group(1)
                    self.stdout.write(f"   🔢 Version: {apk_data['version']}")
                    break
            
            size_patterns = [
                r'Size[:\s]+(\d+(?:\.\d+)?)\s*(MB|GB)',
                r'(\d+(?:\.\d+)?)\s*(MB|GB)',
            ]
            for pattern in size_patterns:
                match = re.search(pattern, all_text, re.IGNORECASE)
                if match:
                    apk_data['size'] = f"{match.group(1)} {match.group(2).upper()}"
                    self.stdout.write(f"   💾 Size: {apk_data['size']}")
                    break
            
            # ===== DOWNLOAD LINK =====
            download_url = self.extract_download_link(soup, session, apk_url)
            apk_data['download_url'] = download_url
            self.stdout.write(f"   📦 Download: {'✓' if download_url != apk_url else 'Using page URL'}")
            
            # ===== SCREENSHOTS =====
            apk_data['screenshots'] = []
            for img in soup.select('article img, .content img, .screenshots img'):
                src = self._extract_img_src(img)
                if src and self._is_valid_screenshot(src):
                    if src not in apk_data['screenshots'] and len(apk_data['screenshots']) < 10:
                        apk_data['screenshots'].append(src)
            
            if apk_data['screenshots']:
                self.stdout.write(f"   🖼️ Screenshots: {len(apk_data['screenshots'])}")
            
            # ===== CATEGORIES =====
            apk_data['categories'] = []
            for cat in soup.select('a[rel="category tag"], .post-categories a'):
                cat_name = cat.get_text().strip()
                excluded = ['home', 'android', 'games', 'apps', 'modded', 'uncategorized']
                if cat_name.lower() not in excluded:
                    apk_data['categories'].append(cat_name)
            
            # ===== STATUS =====
            combined_text = (title_text + ' ' + apk_data.get('mod_features', '')).lower()
            if 'mod' in combined_text or 'modded' in combined_text:
                apk_data['status'] = 'modded'
            elif 'premium' in combined_text:
                apk_data['status'] = 'premium'
            elif 'pro' in combined_text:
                apk_data['status'] = 'pro'
            elif 'unlocked' in combined_text:
                apk_data['status'] = 'unlocked'
            else:
                apk_data['status'] = 'original'
            
            return apk_data
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Error: {e}"))
            import traceback
            traceback.print_exc()
            return None

    def _is_valid_screenshot(self, url):
        """Check if URL is a valid screenshot"""
        if not url or not url.startswith('http'):
            return False
        
        url_lower = url.lower()
        
        # Exclude patterns
        exclude = ['icon', 'logo', 'avatar', 'favicon', '.svg', 'gravatar']
        for pattern in exclude:
            if pattern in url_lower:
                return False
        
        return True

    def handle(self, *args, **options):
        max_items = options['max_items']
        apk_type = options['type']
        start_page = options['start_page']
        delay_min = options['delay_min']
        delay_max = options['delay_max']
        
        session = self.create_session()
        
        self.stdout.write(self.style.SUCCESS("\n" + "="*70))
        self.stdout.write(self.style.SUCCESS("🚀 APKHOME.NET SCRAPER - ENHANCED VERSION"))
        self.stdout.write(self.style.SUCCESS("="*70 + "\n"))
        self.stdout.write(f"📊 Max items: {max_items}")
        self.stdout.write(f"🎯 Type: {apk_type.upper()}")
        self.stdout.write(f"📄 Start page: {start_page}")
        self.stdout.write(f"⏱️ Delay: {delay_min}-{delay_max}s\n")
        
        processed = 0
        created = 0
        updated = 0
        skipped = 0
        current_page = start_page
        processed_urls = set()
        
        while processed < max_items:
            self.stdout.write(f"\n{'='*70}")
            self.stdout.write(f"📋 PAGE {current_page}")
            self.stdout.write(f"{'='*70}")
            
            apk_links = self.get_listing_page(session, apk_type, current_page)
            
            if not apk_links:
                self.stdout.write(self.style.WARNING(f"⚠️ No items on page {current_page}"))
                if current_page > 5:
                    break
                current_page += 1
                time.sleep(random.uniform(delay_min, delay_max))
                continue
            
            unique_links = [link for link in apk_links if link not in processed_urls]
            
            if not unique_links:
                current_page += 1
                continue
            
            for idx, link in enumerate(unique_links, 1):
                if processed >= max_items:
                    break
                
                processed_urls.add(link)
                self.stdout.write(f"\n[{idx}/{len(unique_links)}]")
                
                apk_data = self.scrape_apk_page(session, link, apk_type)
                
                if not apk_data:
                    skipped += 1
                    time.sleep(random.uniform(delay_min * 0.5, delay_max * 0.5))
                    continue
                
                try:
                    apk, is_created = APK.objects.update_or_create(
                        source_url=apk_data['url'],
                        defaults={
                            'title': apk_data['title'],
                            'apk_type': apk_data.get('type', 'game'),
                            'description': apk_data.get('description', ''),
                            'icon_url': apk_data.get('icon_url', ''),
                            'version': apk_data.get('version', ''),
                            'size': apk_data.get('size', ''),
                            'status': apk_data.get('status', 'modded'),
                            'mod_features': apk_data.get('mod_features', ''),
                            'download_url': apk_data.get('download_url', ''),
                            'is_active': True,
                        }
                    )
                    
                    if is_created:
                        created += 1
                        self.stdout.write(self.style.SUCCESS(f"   ✅ CREATED"))
                    else:
                        updated += 1
                        self.stdout.write(self.style.SUCCESS(f"   🔄 UPDATED"))
                    
                    # Screenshots
                    if apk_data.get('screenshots'):
                        Screenshot.objects.filter(apk=apk).delete()
                        for idx, screenshot_url in enumerate(apk_data['screenshots'], 1):
                            Screenshot.objects.create(
                                apk=apk,
                                image_url=screenshot_url,
                                order=idx
                            )
                    
                    # Categories
                    for cat_name in apk_data.get('categories', [])[:5]:
                        category, _ = Category.objects.get_or_create(
                            slug=slugify(cat_name),
                            defaults={'name': cat_name}
                        )
                        apk.categories.add(category)
                    
                    processed += 1
                    
                except Exception as e:
                    skipped += 1
                    self.stdout.write(self.style.ERROR(f"   ❌ DB error: {e}"))
                
                time.sleep(random.uniform(delay_min, delay_max))
            
            current_page += 1
            time.sleep(random.uniform(delay_min * 1.5, delay_max * 1.5))
        
        # Final stats
        self.stdout.write(self.style.SUCCESS(f"\n{'='*70}"))
        self.stdout.write(self.style.SUCCESS("🎉 SCRAPING COMPLETED!"))
        self.stdout.write(self.style.SUCCESS(f"{'='*70}"))
        self.stdout.write(f"📊 Processed: {processed}")
        self.stdout.write(self.style.SUCCESS(f"✅ Created: {created}"))
        self.stdout.write(f"🔄 Updated: {updated}")
        self.stdout.write(f"⏭️ Skipped: {skipped}")
        self.stdout.write(f"📚 Total APKs: {APK.objects.count()}\n")