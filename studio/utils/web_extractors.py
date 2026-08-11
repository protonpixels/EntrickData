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

            # If main_text is empty, try to extract from main_html
            if not main_text and main_html:
                soup = BeautifulSoup(main_html, 'html.parser')
                main_text = soup.get_text(separator='\n', strip=True)

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

            # Extract elements from main content
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
            # Handle case where prop might be a list
            prop = tag.get('property', '') or tag.get('name', '')

            # If prop is a list, convert to string or skip
            if isinstance(prop, list):
                # If it's a list, take the first item or join them
                prop = prop[0] if prop else ''

            # Skip if prop is not a string
            if not isinstance(prop, str):
                continue

            content = tag.get('content', '')

            # Skip if content is not a string
            if not isinstance(content, str):
                content = str(content) if content else ''

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
        """Extract meaningful elements from HTML - including all text content"""
        elements = []

        # Process the soup to extract all text content in order
        # This will handle divs and other containers properly

        def process_element(element, parent_type=None):
            """Recursively process elements to extract meaningful content"""
            if element.name is None:
                return

            # Skip script, style, nav, header, footer
            if element.name in ['script', 'style', 'nav', 'header', 'footer', 'aside']:
                return

            # Get text content
            text = element.get_text(strip=True)

            # Skip empty elements
            if not text:
                return

            # Determine element type
            element_type = 'text'
            is_heading = element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']
            is_paragraph = element.name == 'p'
            is_list = element.name in ['ul', 'ol']
            is_list_item = element.name == 'li'
            is_blockquote = element.name == 'blockquote'
            is_div = element.name == 'div'
            is_section = element.name in ['section', 'article']

            if is_heading:
                element_type = 'heading'
            elif is_paragraph:
                element_type = 'paragraph'
            elif is_list:
                element_type = 'list'
            elif is_list_item:
                element_type = 'list_item'
            elif is_blockquote:
                element_type = 'quote'
            elif is_div or is_section:
                # For divs, check if it has substantial content
                # and isn't just a container for other elements
                children_text = ''
                for child in element.children:
                    if child.name is None:
                        children_text += str(child).strip()

                # If the div has its own text (not just children), include it
                if children_text and len(children_text) > 20:
                    element_type = 'section'
                else:
                    # Process children instead
                    for child in element.children:
                        process_element(child, element_type)
                    return
            else:
                # For other tags, process children
                for child in element.children:
                    process_element(child, element_type)
                return

            # Get attributes
            attributes = {}
            if element.name == 'a' and element.get('href'):
                href = element.get('href')
                if isinstance(href, list):
                    href = href[0] if href else None
                if href:
                    attributes['href'] = href

            if element.name == 'img' and element.get('src'):
                src = element.get('src')
                if isinstance(src, list):
                    src = src[0] if src else None
                if src:
                    attributes['src'] = src

            # For list items, include the parent list type in attributes
            if is_list_item and parent_type in ['list']:
                attributes['parent_type'] = 'list'

            # Add the element
            elements.append({
                'type': element_type,
                'content': text,
                'html': str(element)[:500],
                'attributes': attributes
            })

        # Start processing from the body or the soup itself
        body = soup.find('body') if soup.find('body') else soup
        process_element(body)

        return elements