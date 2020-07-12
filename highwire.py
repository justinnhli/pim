#!/usr/bin/env python3

import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

# look for HighWire Press meta-tags
# see https://scholar.google.com/intl/en-us/scholar/inclusion.html#indexing

# downloading


def extract_text(element):
    # type: (BeautifulSoup) -> str
    """Extract all text from the BeautifulSoup element."""
    text = []
    for desc in element.descendants:
        if not hasattr(desc, 'contents'):
            text.append(re.sub(r'\s', ' ', desc))
    return re.sub(r'  \+', ' ', ''.join(text).strip())


def download(url):
    response = requests.get(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:78.0) Gecko/20100101 Firefox/78.0'},
    )
    if response.status_code != 200:
        raise IOError(f'Unable to download {url} (status code {response.status_code})')
    return response.text


# source-agnostic processing


def parse_author(highwire, url, html):
    # pylint: disable = unused-argument
    if 'author' not in highwire:
        return None
    if all(',' in author for author in highwire['author']):
        return ' and '.join(highwire['author'])
    else:
        authors = []
        for author in highwire['author']:
            names = author.split()
            authors.append(names[-1] + ', ' + ' '.join(names[:-1]))
        return ' and '.join(authors)


def parse_doi(highwire, url, html):
    # pylint: disable = unused-argument
    return highwire.get('doi', None)


def parse_journal(highwire, url, html):
    # pylint: disable = unused-argument
    return highwire.get('journal', None)


def parse_number(highwire, url, html):
    # pylint: disable = unused-argument
    for attr in ('number', 'issue'):
        if attr in highwire:
            return highwire[attr]
    return None


def parse_pages(highwire, url, html):
    # pylint: disable = unused-argument
    if 'firstpage' in highwire and 'lastpage' in highwire:
        first_page = highwire['firstpage']
        last_page = highwire['lastpage']
        if first_page != last_page:
            return f'{first_page}--{last_page}'
    return None


def parse_publisher(highwire, url, html):
    # pylint: disable = unused-argument
    return highwire.get('publisher', None)


def parse_title(highwire, url, html):
    # pylint: disable = unused-argument
    return highwire.get('title', None)


def parse_type(highwire, url, html):
    # pylint: disable = unused-argument
    for attr in ['type', 'article_type']:
        if attr not in highwire:
            continue
        if highwire[attr].lower() == 'jour' or 'article' in highwire[attr]:
            return 'article'
    return 'inproceedings' # FIXME


def parse_volume(highwire, url, html):
    # pylint: disable = unused-argument
    return highwire.get('volume', None)


def parse_year(highwire, url, html):
    # pylint: disable = unused-argument
    for attr in ['date', 'publication_date', 'online_date', 'cover_date']:
        if attr not in highwire:
            continue
        match = re.search('[0-9]{4}', highwire[attr])
        if match:
            return match.group(0)
    return None


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


# source-specific processing


def scrape_sciencedirect_author(html):
    authors = []
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find(id='author-group').find_all(class_='author'):
        first_name = extract_text(tag.find(class_='given-name'))
        last_name = extract_text(tag.find(class_='surname'))
        authors.append(f'{last_name}, {first_name}')
    return authors


# conversion


def get_domain(url):
    match = re.search(r'([^.]+\.)*([^.]+)(\.[^.]+)', urlsplit(url).netloc)
    if not match:
        raise ValueError(f'unable to determine domain of {url}')
    return re.sub('[^0-9A-Za-z]', '', match.groups()[-2]).lower()


def get_attributes():
    attrs = set()
    for name in globals():
        if name.startswith('parse_'):
            attrs.add(name.split('_')[1])
            continue
        match = re.fullmatch('scrape_(?P<domain>[^_]*)_(?P<attr>[a-z]*)', name)
        if match:
            attrs.add(match.group('attr'))
    return attrs


def scrape_highwire(url, html):
    domain = get_domain(url)
    functions = globals()
    highwire = defaultdict(list)
    for match in re.finditer(r'<\s*meta[^>]*>', html):
        attrs = {
            match.group(1).lower(): match.group(2)
            for match in re.finditer('([a-z]+)="([^"]*)"', match.group(0))
        }
        name = attrs.get('name', '')
        if name.startswith('citation_') and name != 'citation_reference':
            highwire[name.replace('citation_', '')].append(attrs.get('content', ''))
    for attr in get_attributes():
        if attr not in highwire and f'scrape_{domain}_{attr}' in functions:
            val = functions[f'scrape_{domain}_{attr}'](html)
            if val is not None:
                highwire[attr] = val
    for attr, val in highwire.items():
        if len(val) == 1:
            highwire[attr] = val[0]
    return highwire


def highwire_to_bibtex(highwire, url, html):
    bibtex = {}
    functions = globals()
    for attr in get_attributes():
        val = None
        if f'parse_{attr}' in functions:
            val = functions[f'parse_{attr}'](highwire, url, html)
        if val is not None:
            bibtex[attr] = val
    bibtex['id'] = create_bibtex_id(bibtex)
    return bibtex


def bibtex_to_str(bibtex):
    lines = []
    lines.append('@' + bibtex['type'] + ' {' + bibtex['id'] + ',')
    for attr, val in sorted(bibtex.items()):
        if attr not in ('type', 'id'):
            lines.append(f'    {attr} = {{{val}}},')
    lines.append('}')
    return '\n'.join(lines)


def to_bibtex(url, html=None):
    if html is None:
        html = download(url)
    highwire = scrape_highwire(url, html)
    bibtex = highwire_to_bibtex(highwire, url, html)
    return bibtex_to_str(bibtex)


# main


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
