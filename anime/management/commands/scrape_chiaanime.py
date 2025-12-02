from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
from django.db import connection, reset_queries
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
import os
import pickle

API_URL = 'https://chia-anime.su/wp-json/wp/v2/posts/'

class Command(BaseCommand):
    help = 'Scrape ALL anime data from chia-anime.su and update database'

    def __init__(self):
        super().__init__()
        self.cache_file = 'scraped_pages_cache.pkl'
        self.scraped_pages = self.load_scraped_pages()

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
        # Save cache every 5 pages
        if len(self.scraped_pages) % 5 == 0:
            self.save_scraped_pages()

    def is_page_scraped(self, page_number):
        """Check if a page has been scraped before"""
        return page_number in self.scraped_pages

    def add_arguments(self, parser):
        parser.add_argument('--max-pages', type=int, default=None)
        parser.add_argument('--start-page', type=int, default=1)
        parser.add_argument('--per-page', type=int, default=99999)
        parser.add_argument('--delay-min', type=float, default=2.0)
        parser.add_argument('--delay-max', type=float, default=4.0)
        parser.add_argument('--force-rescrape', action='store_true', 
                          help='Force rescrape of already scraped pages')
        parser.add_argument('--clear-cache', action='store_true',
                          help='Clear the scraped pages cache before starting')

    def refresh_db_connection(self):
        """Refresh database connection to prevent timeout"""
        try:
            reset_queries()
            connection.close()
            print("  🔄 Database connection refreshed")
        except Exception as e:
            print(f"  ⚠️ Connection refresh warning: {e}")

    def clean_title(self, title):
        """Extract anime title and episode info from post title"""
        title = re.sub(r'\s+', ' ', title).strip()
        title = re.sub(r'\s*English Subbed$', '', title, flags=re.IGNORECASE)
        episode_match = re.search(r'Episode (\d+)', title, re.IGNORECASE)
        episode_number = int(episode_match.group(1)) if episode_match else None
        anime_title = re.sub(r'\s*Episode \d+', '', title, flags=re.IGNORECASE).strip()
        return anime_title, episode_number

    def extract_anime_poster(self, post_content, anime_title):
        """Extract anime poster/image from post content or search for it"""
        try:
            if post_content:
                soup = BeautifulSoup(post_content, 'html.parser')
                images = soup.find_all('img')
                
                for img in images:
                    src = img.get('src', '').strip()
                    alt = img.get('alt', '').lower()
                    
                    if any(skip in src.lower() for skip in ['logo', 'banner', 'ad', 'button']):
                        continue
                        
                    if src and (anime_title.lower() in alt or 'poster' in alt or 'cover' in alt):
                        return src
                
                for img in images:
                    src = img.get('src', '').strip()
                    if src and not any(skip in src.lower() for skip in ['logo', 'banner', 'ad', 'button']):
                        return src
                        
        except Exception as e:
            print(f"Error extracting poster: {e}")
            
        return None

    def resolve_stream_link(self, fyptt_url):
        """Resolve fypttvideos.xyz links to actual stream URLs"""
        try:
            if 'fypttvideos.xyz' not in fyptt_url:
                return fyptt_url
                
            print(f"  🔄 Resolving stream link: {fyptt_url}")
            
            scraper = cloudscraper.create_scraper()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://chia-anime.su/",
            }
            
            response = scraper.get(fyptt_url, headers=headers, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            iframes = soup.find_all('iframe')
            for iframe in iframes:
                src = iframe.get('src')
                if src:
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://fypttvideos.xyz' + src
                    
                    embed_domains = ['embedz.net', 'vidstream', 'streamtape', 'mixdrop', 'doodstream']
                    if any(domain in src.lower() for domain in embed_domains):
                        print(f"  ✅ Found embedded player: {src}")
                        return src
            
            print(f"  ❌ Could not resolve stream link")
            return None
            
        except Exception as e:
            print(f"  ❌ Error resolving stream link {fyptt_url}: {e}")
            return None
        
        finally:
            time.sleep(random.uniform(1, 3))

    def is_valid_streaming_url(self, url):
        """Check if URL is a valid streaming/download link"""
        url_lower = url.lower()
        
        excluded_extensions = ['.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.ico']
        excluded_paths = ['/wp-content/', '/wp-includes/', '/assets/', '/css/', '/js/']
        
        for ext in excluded_extensions:
            if url_lower.endswith(ext) or f'{ext}?' in url_lower:
                return False
                
        for path in excluded_paths:
            if path in url_lower:
                return False
        
        valid_domains = [
            'fypttvideos.xyz', 'embedz.net', 'vidstream', 'mega.nz', 
            'streamtape.com', 'mixdrop.co', 'doodstream.com'
        ]
        
        for domain in valid_domains:
            if domain in url_lower:
                return True
        
        return False

    def extract_download_links(self, html_content, post_content):
        """Extract and resolve download links"""
        links = []
        
        if html_content:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            episode_repeater = soup.find('div', class_='episodeRepeater')
            if episode_repeater:
                print("  🔍 Found episodeRepeater section")
                for a_tag in episode_repeater.find_all('a', href=True):
                    href = a_tag.get('href', '').strip()
                    text = a_tag.get_text().strip()
                    
                    if href and self.is_valid_streaming_url(href):
                        if 'fypttvideos.xyz' in href:
                            resolved_url = self.resolve_stream_link(href)
                            if resolved_url:
                                href = resolved_url
                                print(f"  ✅ Resolved: {href}")
                        
                        quality = self.extract_quality_from_text(text)
                        
                        links.append({
                            'url': href,
                            'label': text if text else 'Stream Link',
                            'quality': quality
                        })
                        print(f"  🔹 Added stream link: {text} -> {href}")
            
            streaming_containers = soup.find_all(['div'], class_=['bixbox', 'show_adv_wrap'])
            for container in streaming_containers:
                for a_tag in container.find_all('a', href=True):
                    href = a_tag.get('href', '').strip()
                    text = a_tag.get_text().strip()
                    
                    if href and self.is_valid_streaming_url(href):
                        if href not in [link['url'] for link in links]:
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
        else:
            return '720p'

    def fetch_episode_page(self, post_link):
        """Fetch the episode page HTML"""
        try:
            scraper = cloudscraper.create_scraper()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            
            response = scraper.get(post_link, headers=headers, timeout=15)
            response.raise_for_status()
            return response.text
            
        except Exception as e:
            print(f"⚠️ Error fetching episode page {post_link}: {e}")
            return None

    def get_or_create_category(self, category_id):
        """Get or create anime category"""
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
            
            return category
            
        except Exception as e:
            print(f"Error fetching category: {e}")
            category, _ = AnimeCategory.objects.get_or_create(
                name='Anime',
                defaults={'slug': 'anime', 'is_active': True}
            )
            return category

    def get_total_posts(self):
        """Get total number of posts"""
        try:
            scraper = cloudscraper.create_scraper()
            response = scraper.get(
                API_URL,
                params={'page': 1, 'per_page': 1, 'status': 'publish'},
                timeout=15
            )
            response.raise_for_status()
            
            total_posts = response.headers.get('X-WP-Total', 0)
            total_pages = response.headers.get('X-WP-TotalPages', 0)
            
            return int(total_posts), int(total_pages)
            
        except Exception as e:
            print(f"⚠️ Could not get total post count: {e}")
            return None, None

    def get_host_name(self, url):
        """Extract host name from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            if 'mega.nz' in domain:
                return 'mega'
            elif 'fypttvideos.xyz' in domain:
                return 'vidstreaming'
            elif 'embedz.net' in domain:
                return 'embedz'
            elif 'streamtape.com' in domain:
                return 'streamtape'
            else:
                return domain.replace('www.', '')
        except:
            return 'unknown'

    def handle(self, *args, **options):
        max_pages = options.get('max_pages')
        start_page = options.get('start_page', 1)
        per_page = min(options.get('per_page', 20), 100)
        delay_min = options.get('delay_min', 2.0)
        delay_max = options.get('delay_max', 4.0)
        force_rescrape = options.get('force_rescrape', False)
        clear_cache = options.get('clear_cache', False)
        
        # Clear cache if requested
        if clear_cache:
            self.scraped_pages.clear()
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            print("🗑️ Cleared scraped pages cache")
        
        print(f"🚀 Starting comprehensive scrape from chia-anime.su...")
        print(f"   📊 Starting from page: {start_page}")
        print(f"   📄 Posts per page: {per_page}")
        print(f"   ⏱️  Request delay: {delay_min}-{delay_max} seconds")
        print(f"   🔄 Force rescrape: {force_rescrape}")
        print(f"   📂 Previously scraped pages: {len(self.scraped_pages)}")
        
        total_posts, total_pages = self.get_total_posts()
        if total_posts and total_pages:
            print(f"   📈 Total posts available: {total_posts}")
            print(f"   📚 Total pages available: {total_pages}")
        
        page = start_page
        processed_posts = 0
        skipped_pages = 0
        consecutive_empty_pages = 0
        max_empty_pages = 3
        
        # Statistics tracking
        stats = {
            'new_animes': 0,
            'existing_animes': 0,
            'new_episodes': 0,
            'existing_episodes': 0,
            'new_links': 0,
            'updated_links': 0,
            'skipped_links': 0
        }
        
        while True:
            if max_pages and page > start_page + max_pages - 1:
                print(f"✅ Reached maximum pages limit ({max_pages})")
                break
            
            # Check if page was already scraped
            if not force_rescrape and self.is_page_scraped(page):
                print(f"\n⏭️  Page {page} - ALREADY SCRAPED (skipping)")
                skipped_pages += 1
                page += 1
                continue
            
            # Refresh DB connection every 10 pages
            if (page - start_page) % 10 == 0 and page != start_page:
                self.refresh_db_connection()
                
            try:
                print(f"\n🌐 Fetching page {page}...")
                
                scraper = cloudscraper.create_scraper()
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
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
                        raw_title = post.get('title', {}).get('rendered', '').strip()
                        if not raw_title:
                            continue

                        print(f"\n🎬 Processing: {raw_title}")
                        
                        anime_title, episode_number = self.clean_title(raw_title)
                        
                        if not episode_number:
                            print(f"⚠️ No episode number found, skipping")
                            continue

                        content = post.get('content', {}).get('rendered', '')
                        description = BeautifulSoup(
                            post.get('excerpt', {}).get('rendered', ''), 
                            'html.parser'
                        ).get_text().strip()
                        
                        post_link = post.get('link', '')
                        
                        print(f"  📄 Fetching episode page: {post_link}")
                        episode_html = self.fetch_episode_page(post_link)

                        download_links = self.extract_download_links(episode_html, content)
                        
                        if not download_links:
                            print(f"⚠️ No download links found for: {anime_title} Episode {episode_number}")
                            continue
                        
                        print(f"✅ Found {len(download_links)} download links")

                        poster_url = self.extract_anime_poster(content, anime_title)

                        try:
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

                            if anime_created:
                                print(f"  🆕 Created NEW anime: {anime_title}")
                                stats['new_animes'] += 1
                            else:
                                print(f"  ♻️  Using EXISTING anime: {anime_title}")
                                stats['existing_animes'] += 1

                            if not anime_created and poster_url and not anime.poster_url:
                                anime.poster_url = poster_url
                                anime.save()
                                print(f"  🖼️  Updated poster image for {anime_title}")

                            if anime_created and post.get('categories'):
                                category = self.get_or_create_category(post['categories'][0])
                                anime.category = category
                                anime.save()

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
                                print(f"  🆕 Created NEW episode: {anime_title} Episode {episode_number}")
                                stats['new_episodes'] += 1
                            else:
                                print(f"  ♻️  EXISTING episode: {anime_title} Episode {episode_number}")
                                stats['existing_episodes'] += 1

                            # Process download links with detailed status
                            existing_links = {dl.url: dl for dl in episode.download_links.all()}
                            added_links = 0
                            updated_links = 0
                            skipped_links = 0
                            
                            for link_data in download_links:
                                link_url = link_data['url']
                                
                                if link_url in existing_links:
                                    # Link already exists - check if we need to update
                                    existing_link = existing_links[link_url]
                                    needs_update = False
                                    
                                    if existing_link.quality != link_data['quality']:
                                        existing_link.quality = link_data['quality']
                                        needs_update = True
                                    
                                    if existing_link.label != link_data['label']:
                                        existing_link.label = link_data['label']
                                        needs_update = True
                                    
                                    if needs_update:
                                        existing_link.save()
                                        updated_links += 1
                                        stats['updated_links'] += 1
                                        print(f"  🔄 Updated link: {link_data['quality']} - {link_data['label']}")
                                    else:
                                        skipped_links += 1
                                        stats['skipped_links'] += 1
                                        print(f"  ⏭️  Skipped (exists): {link_data['quality']} - {link_data['label']}")
                                else:
                                    # Create new link
                                    DownloadLink.objects.create(
                                        episode=episode,
                                        quality=link_data['quality'],
                                        url=link_data['url'],
                                        host_name=self.get_host_name(link_data['url']),
                                        label=link_data['label'],
                                        is_active=True
                                    )
                                    added_links += 1
                                    stats['new_links'] += 1
                                    print(f"  ➕ Added NEW link: {link_data['quality']} - {link_data['label']}")

                            # Summary for this episode
                            print(f"  📊 Link Summary: {added_links} new, {updated_links} updated, {skipped_links} existing")

                            max_episode = Episode.objects.filter(anime=anime).aggregate(
                                max_ep=models.Max('episode_number')
                            )['max_ep'] or 0
                            
                            if max_episode > anime.total_episodes:
                                anime.total_episodes = max_episode
                                anime.save()

                            processed_posts += 1
                            posts_processed_this_page += 1
                            
                        except Exception as db_error:
                            print(f"💥 Database error: {db_error}")
                            self.refresh_db_connection()
                            continue
                        
                        time.sleep(random.uniform(delay_min, delay_max))

                    except Exception as e:
                        print(f"💥 Error processing post: {e}")
                        continue

                # Mark page as scraped after successful processing
                self.mark_page_as_scraped(page)
                
                print(f"✅ Page {page} complete: processed {posts_processed_this_page}/{len(posts)} posts")
                print(f"📊 Total processed so far: {processed_posts} posts")
                print(f"⏭️  Total skipped pages: {skipped_pages}")
                
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
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= max_empty_pages:
                    break
                continue

        # Save cache one final time
        self.save_scraped_pages()
        
        # Final summary
        self.refresh_db_connection()
        
        try:
            total_animes = Anime.objects.count()
            total_episodes = Episode.objects.count()
            total_links = DownloadLink.objects.count()
        except:
            total_animes = "Unknown"
            total_episodes = "Unknown"
            total_links = "Unknown"
        
        print(f"\n🎉 Scraping completed!")
        print(f"📊 Final Statistics:")
        print(f"   • Total posts processed: {processed_posts}")
        print(f"   • Pages scraped: {page - start_page}")
        print(f"   • Pages skipped (already scraped): {skipped_pages}")
        print(f"   • Total scraped pages in cache: {len(self.scraped_pages)}")
        print(f"\n📺 Anime Statistics:")
        print(f"   • New animes created: {stats['new_animes']}")
        print(f"   • Existing animes updated: {stats['existing_animes']}")
        print(f"   • Total animes in DB: {total_animes}")
        print(f"\n🎬 Episode Statistics:")
        print(f"   • New episodes created: {stats['new_episodes']}")
        print(f"   • Existing episodes found: {stats['existing_episodes']}")
        print(f"   • Total episodes in DB: {total_episodes}")
        print(f"\n🔗 Download Link Statistics:")
        print(f"   • New links added: {stats['new_links']}")
        print(f"   • Links updated: {stats['updated_links']}")
        print(f"   • Links skipped (unchanged): {stats['skipped_links']}")
        print(f"   • Total links in DB: {total_links}")
        print(f"\n💡 Tip: Use --force-rescrape to re-scrape already scraped pages")
        print(f"💡 Tip: Use --clear-cache to start fresh")