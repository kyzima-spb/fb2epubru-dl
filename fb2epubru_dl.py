from collections import OrderedDict
from functools import lru_cache
from itertools import count
import logging
import os
from pathlib import Path
from string import whitespace
from time import sleep
import urllib.parse

import click
import requests
from lxml.html import fromstring


logging.basicConfig(level=logging.DEBUG)


logger = logging.getLogger(__name__)


def download(url, referer, path, chunk_size=1024):
    """Downloads a file from the specified address."""
    resp = make_session().get(url, stream=True, headers={
        'referer': referer,
    })

    with open(path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size):
            f.write(chunk)

    return path


@lru_cache()
def make_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:68.0) Gecko/20100101 Firefox/68.0',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
    })
    return session


class MultipleElementsFoundError(Exception):
    def __init__(self, found, *args):
        super().__init__(*args)
        self.found = found


class BadSelector(Exception):
    def __init__(self, selector, *args):
        super().__init__(*args)
        self.selector = selector


class Parser(object):
    BASE_URL = 'https://fb2-epub.ru'

    def get_abs_url(self, url):
        """Возвращает абсолютный URL-адрес."""
        return urllib.parse.urljoin(self.BASE_URL, url)

    def findall(self, selector, url=None, tree=None, error_message=None):
        """Выбырает по CSS-селектору HTML-элементы и возвращает все найденные."""
        if tree is None:
            tree = self.make_tree(self.send(url))

        found = tree.cssselect(selector)

        if not found and error_message:
            raise BadSelector(selector, error_message)

        return found

    def findone(self, selector, url=None, tree=None, error_message=None):
        """Выбырает по CSS-селектору один HTML-элемент и возвращает его, либо None."""
        found = self.findall(selector, url=url, tree=tree, error_message=error_message)

        if len(found) > 1:
            raise MultipleElementsFoundError(found)

        return found[0] if found else None

    def make_tree(self, response):
        """Создает и возвращает HTML-дерево из результата запроса."""
        return fromstring(response.content)

    def send(self, url, **kwargs):
        """Выполняет GET запрос и возвращает объект-ответа."""
        return make_session().get(self.get_abs_url(url), **kwargs)

    def get_book(self, url):
        """Возвращает полную информацию о книге."""
        elem = self.findone(
            selector='#dle-content',
            url=url,
            error_message='CSS selector for retrieving book has been changed.'
        )
        authors = self.findall(
            selector='#msg > :first-child a',
            tree=elem,
            error_message='CSS selector for retrieving book authors has been changed.'
        )
        book = {
            'url': url,
            'authors': [
                dict(name=a.text, url=self.get_abs_url(a.get('href'))) for a in authors
            ],
            'title': authors[-1].tail.strip(whitespace + '.'),
        }

        book['author'] = ', '.join(a['name'] for a in book['authors'])

        # description = [e.text.strip() for e in self.findall('p', tree=elem) if e.text]
        # book['description'] = '\n'.join(description)

        fb2_url = self.findone(
            selector='#download .loadbuttons__button-fb2 .loadbuttons__button-size',
            tree=elem,
            error_message='CSS selector for retrieving FB2 has been changed.'
        )

        if fb2_url is not None:
            book['fb2_url'] = fb2_url.get('data-link')

        epub_url = self.findone(
            selector='#download .loadbuttons__button-epub .loadbuttons__button-size',
            tree=elem,
            error_message='CSS selector for retrieving EPUB has been changed.'
        )

        if epub_url is not None:
            book['epub_url'] = epub_url.get('data-link')

        return book

    def get_index(self):
        """Возвращает алфавитный указатель в виде словаря."""
        index = self.findall(
            selector='main .header__menu a',
            url='/',
            error_message='CSS selector for retrieving index has been changed.'
        )
        return {a.text.lower(): a.get('href') for a in index}

    def search(self, query):
        """Выполняет поиск в каталоге по алфавитному указателю."""
        first_letter = query[0].lower()
        url = self.get_index().get(first_letter)

        logger.debug(f'Поисковый запрос: "{query}" ({self.get_abs_url(url)})')

        if url:
            authors_list = self.findall(
                selector=f'h1.block__title ~ a:contains("{query}")',
                url=url,
                error_message='CSS selector for retrieving authors list has been changed.'
            )

            for a in authors_list:
                yield a.get('href'), a.text

    def iter_books(self, url):
        """Итетирует все книги с учетом пагинации с первой переданной страницы."""
        logger.debug(f'Создан итератор по книгам для адреса: {self.get_abs_url(url)}')
        return BookIterator(self, url)


class BookIterator(object):
    def __init__(self, parser, base_url):
        self.parser = parser
        self.base_url = base_url

        count_element = self.parser.findone(
            '.main__h1-wrapper p',
            url=self.base_url,
            error_message='CSS selector for retrieving number of books by the author has been changed.'
        )

        self.books_count = int(count_element.text.split(': ').pop())

    def __iter__(self):
        if self.books_count:
            received = 0
            page = count(start=1)

            while received < self.books_count:
                books_urls = self.parser.findall(
                    selector='#dle-content .entry__title a',
                    url=f'{self.base_url}/page/{next(page)}',
                    error_message='CSS selector for retrieving books list has been changed.'
                )

                for a in books_urls:
                    yield self.parser.get_book(a.get('href'))

                received += len(books_urls)

    def __len__(self):
        return self.books_count


def make_select_menu(iterable):
    menu = OrderedDict()

    for i, item in enumerate(iterable, start=1):
        menu[i] = item[0]
        click.echo(f'{i}. {item[1]}')

    idx = click.prompt(
        'Select one',
        type=click.IntRange(1, len(menu)),
        show_choices=False
    )

    return menu.get(idx)


@click.command()
@click.argument('query')
@click.argument('dest', type=click.Path(exists=True, writable=True, resolve_path=True))
@click.option('--filename-template', default='{author}. {title}')
@click.option('--file-format', type=click.Choice(('epub', 'fb2')), default='epub')
def main(query, dest, filename_template, file_format):
    """Загрузка всех книг автора."""
    parser = Parser()
    found = tuple(parser.search(query))

    if len(found) > 1:
        url = make_select_menu(found)
    else:
        url = found[0][0]

    books = parser.iter_books(url)

    with click.progressbar(books, label='Downloading books',
                           fill_char=click.style('#', fg='green'),
                           length=len(books)) as bar:
        for book in bar:
            url = book.get(f'{file_format}_url')
            path = Path(dest, book['author'])

            if not path.exists():
                os.mkdir(path, 0o755)

            path = path / filename_template.format(
                author=book['author'], title=book['title']
            )

            download(url, book['url'], path.with_suffix(f'.{file_format}'))
            sleep(0.5)
