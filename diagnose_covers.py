#!/usr/bin/env python3
"""
Diagnostic tool to find the correct cover image selectors for ManhuaPlus
Run: python diagnose_covers.py
"""

import cloudscraper
from bs4 import BeautifulSoup
import sys

def diagnose_manga_page(url):
    """Diagnose a manga page to find cover images"""
    print(f"\n🔍 Diagnosing: {url}\n")
    
    # Create scraper
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    
    scraper.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })
    
    try:
        response = scraper.get(url, timeout=20)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch page: {response.status_code}")
            return
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        print("=" * 70)
        print("🖼️  ALL IMAGES ON PAGE:")
        print("=" * 70)
        
        # Find ALL images
        all_images = soup.find_all('img')
        print(f"\nFound {len(all_images)} total images\n")
        
        for idx, img in enumerate(all_images, 1):
            # Get all possible image sources
            src = img.get('src', '')
            data_src = img.get('data-src', '')
            data_lazy = img.get('data-lazy-src', '')
            data_original = img.get('data-original', '')
            
            # Get parent classes
            parent_classes = []
            if img.parent:
                parent_classes = img.parent.get('class', [])
            
            img_classes = img.get('class', [])
            
            print(f"Image #{idx}:")
            print(f"  Classes: {' '.join(img_classes)}")
            print(f"  Parent classes: {' '.join(parent_classes)}")
            if src:
                print(f"  src: {src[:100]}")
            if data_src:
                print(f"  data-src: {data_src[:100]}")
            if data_lazy:
                print(f"  data-lazy-src: {data_lazy[:100]}")
            if data_original:
                print(f"  data-original: {data_original[:100]}")
            
            # Check if it looks like a cover
            if any(keyword in str(img).lower() for keyword in ['cover', 'thumb', 'poster', 'summary']):
                print(f"  ⭐ LIKELY COVER IMAGE")
            
            print()
        
        print("\n" + "=" * 70)
        print("🎯 TESTING COMMON SELECTORS:")
        print("=" * 70 + "\n")
        
        # Test various selectors
        selectors = [
            '.summary_image img',
            '.tab-summary img',
            'img.wp-post-image',
            '.post-thumb img',
            '.manga-cover img',
            'div.summary_image img',
            'article img',
            '.entry-content img',
            'img[data-src]',
            'img.lazy',
        ]
        
        for selector in selectors:
            imgs = soup.select(selector)
            if imgs:
                img = imgs[0]
                src = (img.get('data-src') or img.get('src') or 
                       img.get('data-lazy-src') or img.get('data-original') or '')
                if src:
                    print(f"✅ {selector}")
                    print(f"   → {src[:100]}")
                else:
                    print(f"⚠️  {selector} (found but no src)")
            else:
                print(f"❌ {selector}")
        
        print("\n" + "=" * 70)
        print("📝 HTML STRUCTURE:")
        print("=" * 70 + "\n")
        
        # Look for specific divs
        summary_div = soup.select_one('.summary_image')
        if summary_div:
            print("✅ Found .summary_image div")
            print(f"   Content preview: {str(summary_div)[:300]}...")
        else:
            print("❌ No .summary_image div")
        
        tab_summary = soup.select_one('.tab-summary')
        if tab_summary:
            print("✅ Found .tab-summary div")
            print(f"   Content preview: {str(tab_summary)[:300]}...")
        else:
            print("❌ No .tab-summary div")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Test URLs
    test_urls = [
        'https://manhuaplus.com/manga/above-ten-thousand-people/',
        'https://manhuaplus.com/manga/martial-peak/',
    ]
    
    if len(sys.argv) > 1:
        # Use URL from command line
        diagnose_manga_page(sys.argv[1])
    else:
        # Test default URLs
        for url in test_urls:
            diagnose_manga_page(url)
            input("\nPress Enter to continue to next URL...\n")