import requests
from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]
from pathlib import Path
import re

# URLs for Helm best practices
BEST_PRACTICES_URLS = [
    ("General Conventions", "https://helm.sh/docs/chart_best_practices/conventions/"),
    ("Values", "https://helm.sh/docs/chart_best_practices/values/"),
    ("Templates", "https://helm.sh/docs/chart_best_practices/templates/"),
    ("Dependencies", "https://helm.sh/docs/chart_best_practices/dependencies/"),
    ("Labels and Annotations", "https://helm.sh/docs/chart_best_practices/labels/"),
    ("Custom Resource Definitions (CRD)", "https://helm.sh/docs/chart_best_practices/custom_resource_definitions/"),
    ("RBAC", "https://helm.sh/docs/chart_best_practices/rbac/"),
]

OUTPUT_DIR = Path(__file__).parent.parent / 'static'
OUTPUT_FILE = 'HELM_BEST_PRACTICES.md'

def safe_find(element, *args, **kwargs):
    if not isinstance(element, Tag):
        return None
    return element.find(*args, **kwargs)

def safe_find_all(element, *args, **kwargs):
    if not isinstance(element, Tag):
        return []
    return element.find_all(*args, **kwargs)

def fetch_and_extract(url):
    """Fetch a Helm best practices page and extract the main content as markdown."""
    print(f"Fetching {url} ...")
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    # Step 1: Find <div class="columns">
    columns_div = soup.find('div', class_='columns')
    if not columns_div:
        print(f"[ERROR] Could not find <div class='columns'> for {url}")
        raise RuntimeError(f"Could not find <div class='columns'> for {url}")
    # Step 2: Find <section class="column content-docs">
    section = columns_div.find('section', class_='column content-docs')
    if not section:
        print(f"[ERROR] Could not find <section class='column content-docs'> for {url}")
        raise RuntimeError(f"Could not find <section class='column content-docs'> for {url}")
    # Step 3: Find <article class="content-wrapper">
    article = section.find('article', class_='content-wrapper')
    if not article:
        print(f"[ERROR] Could not find <article class='content-wrapper'> for {url}")
        raise RuntimeError(f"Could not find <article class='content-wrapper'> for {url}")
    # Step 4: Extract all direct children of the article
    print(f"[DEBUG] Article children tags: {[c.name for c in article.children if hasattr(c, 'name')]}")
    content = html_to_markdown(article)
    return content


def html_to_markdown(soup):
    """Convert a BeautifulSoup HTML fragment to markdown-ish text."""
    lines = []
    for elem in soup.children:
        if elem.name == 'h1':
            lines.append(f"# {elem.get_text(strip=True)}\n")
        elif elem.name == 'h2':
            lines.append(f"## {elem.get_text(strip=True)}\n")
        elif elem.name == 'h3':
            lines.append(f"### {elem.get_text(strip=True)}\n")
        elif elem.name == 'pre':
            code = elem.get_text()
            lines.append(f"```\n{code}\n```\n")
        elif elem.name == 'code':
            code = elem.get_text()
            lines.append(f"`{code}`")
        elif elem.name == 'ul':
            for li in elem.find_all('li', recursive=False):
                lines.append(f"* {li.get_text(strip=True)}")
            lines.append("")
        elif elem.name == 'ol':
            for i, li in enumerate(elem.find_all('li', recursive=False), 1):
                lines.append(f"{i}. {li.get_text(strip=True)}")
            lines.append("")
        elif elem.name == 'blockquote':
            lines.append(f"> {elem.get_text(strip=True)}")
        elif elem.name == 'p':
            lines.append(elem.get_text(strip=True) + "\n")
        elif elem.name is None:
            # NavigableString
            text = str(elem).strip()
            if text:
                lines.append(text)
        else:
            # Recursively process children
            lines.append(html_to_markdown(elem))
    return '\n'.join(lines)


def main():
    """
    Scrape Helm best practices from official docs and assemble a markdown file.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    toc = ["# Helm Best Practices (Scraped)", "", "_This document was automatically extracted from the official Helm documentation._", ""]
    toc.append("## Table of Contents\n")
    section_links = []
    sections = []
    for section, url in BEST_PRACTICES_URLS:
        anchor = re.sub(r'[^a-z0-9]+', '-', section.lower()).strip('-')
        section_links.append(f"- [{section}](#{anchor})")
        content = fetch_and_extract(url)
        sections.append(f"\n## {section}\n\n_Source: [{url}]({url})_\n\n{content}")
    toc.extend(section_links)
    toc.append("")
    markdown = '\n'.join(toc + sections)
    output_path = OUTPUT_DIR / OUTPUT_FILE
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown)
    print(f"Successfully saved to {output_path}")

if __name__ == '__main__':
    import os
    main() 