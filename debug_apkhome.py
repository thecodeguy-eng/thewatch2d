"""
Debug script to test APKHome.net selectors
Save this as: debug_apkhome.py
Run with: python debug_apkhome.py
"""

import requests
from bs4 import BeautifulSoup

def test_selectors():
    url = 'https://apkhome.net/'
    
    print("🔍 Testing APKHome.net selectors...\n")
    print(f"URL: {url}\n")
    
    # Create session with headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    
    try:
        response = session.get(url, timeout=30)
        print(f"✅ Status Code: {response.status_code}\n")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Save HTML to file for inspection
        with open('apkhome_debug.html', 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
        print("✅ HTML saved to: apkhome_debug.html\n")
        
        print("="*70)
        print("TESTING SELECTORS")
        print("="*70 + "\n")
        
        # Test various selectors
        selectors_to_test = [
            ('article', 'article'),
            ('article a', 'article a'),
            ('article h2', 'article h2'),
            ('article h3', 'article h3'),
            ('article h2 a', 'article h2 a'),
            ('article h3 a', 'article h3 a'),
            ('.post', '.post'),
            ('.post a', '.post a'),
            ('.post-title', '.post-title'),
            ('.post-title a', '.post-title a'),
            ('.entry-title', '.entry-title'),
            ('.entry-title a', '.entry-title a'),
            ('h2.entry-title a', 'h2.entry-title a'),
            ('h3.entry-title a', 'h3.entry-title a'),
            ('a[rel="bookmark"]', 'a[rel="bookmark"]'),
            ('.wp-block-post-title a', '.wp-block-post-title a'),
            ('a[href*="-apk"]', 'a[href*="-apk"]'),
            ('a[href*="-mod"]', 'a[href*="-mod"]'),
            ('.item', '.item'),
            ('.grid-item', '.grid-item'),
            ('.post-item', '.post-item'),
            ('.card', '.card'),
            ('main a', 'main a'),
            ('.site-content a', '.site-content a'),
        ]
        
        for name, selector in selectors_to_test:
            elements = soup.select(selector)
            if elements:
                print(f"✅ {name}: Found {len(elements)} elements")
                
                # Show first 3 links if they're anchor tags
                if 'a' in selector and len(elements) > 0:
                    for i, elem in enumerate(elements[:3]):
                        href = elem.get('href', '')
                        text = elem.get_text().strip()[:60]
                        if href and 'apkhome.net' in href:
                            print(f"   [{i+1}] {text}")
                            print(f"       {href}")
                print()
            else:
                print(f"❌ {name}: Not found")
        
        print("\n" + "="*70)
        print("ANALYZING PAGE STRUCTURE")
        print("="*70 + "\n")
        
        # Find all links
        all_links = soup.find_all('a', href=True)
        apk_links = []
        
        for link in all_links:
            href = link.get('href', '')
            if 'apkhome.net' in href:
                # Skip non-content pages
                skip_patterns = ['/category/', '/tag/', '/author/', '/page/', 
                               '/about', '/contact', '/privacy', '/terms', '/dmca',
                               '/wp-', '#', 'feed', 'comment']
                
                if not any(pattern in href for pattern in skip_patterns):
                    text = link.get_text().strip()
                    if text and len(text) > 3:
                        apk_links.append((text[:60], href))
        
        print(f"📦 Total potential APK links found: {len(apk_links)}\n")
        
        if apk_links:
            print("Sample links:")
            for i, (text, href) in enumerate(apk_links[:10], 1):
                print(f"  [{i}] {text}")
                print(f"      {href}")
                print()
        
        # Check for common WordPress classes
        print("\n" + "="*70)
        print("WORDPRESS STRUCTURE CHECK")
        print("="*70 + "\n")
        
        wp_elements = {
            'Posts': soup.select('.post, [class*="post"]'),
            'Articles': soup.select('article'),
            'Entry Content': soup.select('.entry-content'),
            'Main Content': soup.select('main, .main, #main'),
            'Site Content': soup.select('.site-content'),
        }
        
        for name, elements in wp_elements.items():
            print(f"{name}: {len(elements)} found")
        
        # Check for JavaScript-rendered content
        scripts = soup.find_all('script')
        print(f"\nScript tags: {len(scripts)} found")
        
        # Check if site uses React/Vue/other frameworks
        for script in scripts:
            src = script.get('src', '')
            if 'react' in src.lower() or 'vue' in src.lower() or 'angular' in src.lower():
                print(f"⚠️  Framework detected: {src}")
                print("   Site may be using JavaScript to render content!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_selectors()