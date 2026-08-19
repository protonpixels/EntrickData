import re
from html import unescape


class WebExtractor:
    """Clean text extraction from HTML."""

    def clean_html(self, html: str) -> str:
        """Clean HTML and extract plain text."""
        if not html:
            return ""

        # Remove script and style tags
        html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL)

        # Remove navigation, header, footer
        html = re.sub(r'<nav.*?>.*?</nav>', '', html, flags=re.DOTALL)
        html = re.sub(r'<header.*?>.*?</header>', '', html, flags=re.DOTALL)
        html = re.sub(r'<footer.*?>.*?</footer>', '', html, flags=re.DOTALL)

        # Extract main content if possible
        content_patterns = [
            r'<main.*?>(.*?)</main>',
            r'<article.*?>(.*?)</article>',
            r'<div[^>]*class="[^"]*content[^"]*".*?>(.*?)</div>',
            r'<div[^>]*id="[^"]*content[^"]*".*?>(.*?)</div>',
            r'<body.*?>(.*?)</body>'
        ]

        extracted_text = ""
        for pattern in content_patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                extracted_text = match.group(1)
                break

        if not extracted_text:
            extracted_text = html

        # Remove all HTML tags
        extracted_text = re.sub(r'<[^>]+>', ' ', extracted_text)

        # Unescape HTML entities
        extracted_text = unescape(extracted_text)

        # Normalize whitespace
        extracted_text = re.sub(r'\s+', ' ', extracted_text)

        return extracted_text.strip()