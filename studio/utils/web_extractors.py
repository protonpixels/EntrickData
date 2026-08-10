import requests
import hashlib
import json
import time
import random
from typing import Dict, Optional, List
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from readability import Document


class WebExtractor:
    """Web content extraction utility"""

    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()

    def extract_page(self, url: str) -> Dict:
        """Extract content from a URL"""
        try:
            # Fetch HTML
            headers = {'User-Agent': self.ua.random}
            time.sleep(random.uniform(0.5, 2))

            response = self.session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            html = response.text

            # Extract with readability
            doc = Document(html)
            main_html = doc.summary()
            main_text = doc.text() if hasattr(doc, 'text') else ""
            title = doc.title() if hasattr(doc, 'title') else ""

            # If no title, try to get it from HTML
            if not title:
                soup = BeautifulSoup(html, 'html.parser')
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.get_text(strip=True)

            # Extract metadata
            soup = BeautifulSoup(html, 'html.parser')
            metadata = self._extract_metadata(soup, url)

            # Extract elements
            elements = self._extract_elements(BeautifulSoup(main_html, 'html.parser'))

            # Calculate content hash for deduplication
            content_hash = hashlib.md5(main_text.encode()).hexdigest()

            return {
                'url': url,
                'title': title or 'Untitled',
                'main_html': main_html,
                'main_text': main_text,
                'metadata': metadata,
                'raw_html': html,
                'content_hash': content_hash,
                'elements': elements
            }

        except Exception as e:
            return {
                'url': url,
                'error': str(e),
                'title': 'Error',
                'main_html': '',
                'main_text': '',
                'metadata': {},
                'raw_html': '',
                'content_hash': '',
                'elements': []
            }

    def _extract_metadata(self, soup: BeautifulSoup, url: str) -> Dict:
        """Extract metadata from HTML"""
        metadata = {
            'url': url,
            'domain': url.split('/')[2] if len(url.split('/')) > 2 else ''
        }

        # Open Graph tags
        for tag in soup.find_all('meta'):
            prop = tag.get('property', '') or tag.get('name', '')
            content = tag.get('content', '')

            if prop.startswith('og:'):
                metadata[prop[3:]] = content

            if prop in ['description', 'keywords', 'author']:
                metadata[prop] = content

        # Canonical URL
        canon = soup.find('link', {'rel': 'canonical'})
        if canon and canon.get('href'):
            metadata['canonical'] = canon.get('href')

        return metadata

    def _extract_elements(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract meaningful elements from HTML"""
        elements = []
        element_types = {
            'heading': ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
            'paragraph': ['p'],
            'link': ['a'],
            'image': ['img'],
            'list': ['ul', 'ol'],
            'list_item': ['li'],
            'table': ['table'],
            'quote': ['blockquote']
        }

        for element_type, tags in element_types.items():
            for tag in tags:
                for elem in soup.find_all(tag):
                    text = elem.get_text(strip=True)
                    if text or element_type == 'image':
                        attributes = {}
                        if tag == 'a' and elem.get('href'):
                            attributes['href'] = elem.get('href')
                        if tag == 'img' and elem.get('src'):
                            attributes['src'] = elem.get('src')
                            if not text:
                                text = elem.get('alt', '')

                        elements.append({
                            'type': element_type,
                            'content': text,
                            'html': str(elem)[:500],
                            'attributes': attributes
                        })

        return elements[:100]  # Limit to 100 elements