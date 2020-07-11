#!/usr/bin/env python3

import re
import requests
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

# look for HighWire Press meta-tags
# see https://scholar.google.com/intl/en-us/scholar/inclusion.html#indexing


def extract_text(element):
    # type: (BeautifulSoup) -> str
    """Extract all text from the BeautifulSoup element."""
    text = []
    for desc in element.descendants:
        if not hasattr(desc, 'contents'):
            text.append(re.sub(r'\s', ' ', desc))
    return re.sub(r'  \+', ' ', ''.join(text).strip())



def scrape_sciencedirect_authors(html):
    authors = []
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find(id='author-group').find_all(class_='author'):
        first_name = extract_text(tag.find(class_='given-name'))
        last_name = extract_text(tag.find(class_='surname'))
        authors.append(f'{last_name}, {first_name}')
    return authors


def scrape_authors(url, html):
    parts = urlsplit(url, html)
    if parts.netloc.endswith('sciencedirect.com'):
        return scrape_sciencedirect_authors(html)
    return ''


def parse_author(info, url, html):
    if 'author' not in info:
        info['author'] = scrape_authors(url, html)
    if all(',' in author for author in info['author']):
        return ' and '.join(info['author'])
    else:
        authors = []
        for author in info['author']:
            names = author.split()
            authors.append(names[-1] + ', ' + ' '.join(names[:-1]))
        return ' and '.join(authors)


def parse_doi(info, url, html):
    if 'doi' in info:
        return info['doi']


def parse_journal(info, url, html):
    if 'journal' in info:
        return info['journal']


def parse_number(info, url, html):
    if 'number' in info:
        return info['number']


def parse_pages(info, url, html):
    if 'firstpage' in info and 'lastpage' in info:
        first_page = info['firstpage']
        last_page = info['lastpage']
        if first_page != last_page:
            return f'{first_page}--{last_page}'


def parse_publisher(info, url, html):
    if 'publisher' in info:
        return info['publisher']


def parse_title(info, url, html):
    if 'title' in info:
        return info['title']


def parse_type(info, url, html):
    for attr in ['type', 'article_type']:
        if attr not in info:
            continue
        if info[attr].lower() == 'jour' or 'article' in info[attr]:
            return 'article'
    return 'inproceedings' # FIXME


def parse_volume(info, url, html):
    if 'volume' in info:
        return info['volume']


def parse_year(info, url, html):
    for attr in ['date', 'publication_date', 'online_date', 'cover_date']:
        if attr not in info:
            continue
        match = re.search('[0-9]{4}', info[attr])
        if match:
            return match.group(0)


def create_bibtex_id(bibtex):
    if not all(attr in bibtex for attr in ['author', 'year', 'title']):
        return 'FIXME'
    bibtex_id = ''
    bibtex_id += bibtex['author'].split(',', maxsplit=1)[0]
    bibtex_id += bibtex['year']
    title = re.sub('[^0-9A-Za-z]', ' ', bibtex['title'])
    bibtex_id += ' '.join(
        part[0].upper() + part[1:] for part in title.split()[:3]
    ).title()
    bibtex_id = bibtex_id.replace(' ', '')
    return bibtex_id


def scrape_highwire(html):
    info = defaultdict(list)
    for match in re.finditer(r'<\s*meta[^>]*>', html):
        html = match.group(0)
        attrs = {
            match.group(1).lower(): match.group(2)
            for match in re.finditer('([a-z]+)="([^"]*)"', html)
        }
        name = attrs.get('name', '')
        if name.startswith('citation_') and name != 'citation_reference':
            info[name.replace('citation_', '')].append(attrs.get('content', ''))
    for k, v in info.items():
        if len(v) == 1:
            info[k] = v[0]
    return info


def to_bibtex(url, html=None):
    if html is None:
        html = download(url)
    info = scrape_highwire(html)
    bibtex = {}
    for name, function in globals().items():
        if not name.startswith('parse_'):
            continue
        attr = name.split('_')[1]
        val = function(info, url, html)
        if val is not None:
            bibtex[attr] = val
    bibtex_id = create_bibtex_id(bibtex)
    lines = []
    lines.append(('@' + bibtex['type'] + ' {' + bibtex_id + ',')
    for k, v in sorted(bibtex.items()):
        if k != 'type':
            lines.append(f'    {k} = {{{v}}},')
    lines.append('}')
    return '\n'.join(lines)


def get_head(html):
    start = html.find('<head')
    end = html.find('</head')
    if start == -1 or end == -1:
        return None
    else:
        return html[start:html.index('>', end) + 1]


def download(url):
    response = requests.get(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:78.0) Gecko/20100101 Firefox/78.0'},
    )
    if response.status_code != 200:
        raise IOError(f'Unable to download {url} (status code {response.status_code})')
    return response.text


def main():
    URLS = [
        'https://arxiv.org/abs/1901.00596',
        'https://link.springer.com/article/10.1007/s10956-015-9581-5',
        'https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0002756',
        'https://www.nature.com/articles/s41467-020-15146-7',
        'http://www.sciencedirect.com/science/article/pii/S0010027716302013',
    ]
    for url in URLS:
        slug = re.sub('[^0-9A-Za-z]', '', url)
        filepath = Path(__file__).parent / ('cache-' + slug)
        with filepath.open() as fd:
            html = get_head(fd.read())
        print(to_bibtex(url, html))
        print()


if __name__ == '__main__':
    main()
