from collections import OrderedDict
import math
import os
from string import whitespace
from time import sleep

import click
import requests
from lxml.html import fromstring


def download(url, path, chunk_size=1024):
    """Downloads a file from the specified address."""
    resp = requests.get(url, stream=True)

    with open(path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size):
            f.write(chunk)

    return path


class MultipleElementsFoundError(Exception):
    def __init__(self, found, *args):
        super().__init__(*args)
        self.found = found


class Parser(object):
    BASE_URL = 'https://fb2-epub.ru'

    def get_abs_url(self, url):
        """Возвращает абсолютный URL-адрес."""
        return f'{self.BASE_URL}{url}'

    def findall(self, selector, url=None, tree=None):
        """Выбырает по CSS-селектору HTML-элементы и возвращает все найденные."""
        if tree is None:
            tree = self.make_tree(self.send(url))
        return tree.cssselect(selector)

    def findone(self, selector, url=None, tree=None):
        """Выбырает по CSS-селектору один HTML-элемент и возвращает его, либо None."""
        found = self.findall(selector, url=url, tree=tree)

        if len(found) > 1:
            raise MultipleElementsFoundError(found)

        return found[0] if found else None

    def make_tree(self, response):
        """Создает и возвращает HTML-дерево из результата запроса."""
        return fromstring(response.content)

    def send(self, url, **kwargs):
        """Выполняет GET запрос и возвращает объект-ответа."""
        return requests.get(self.get_abs_url(url), **kwargs)

    def get_book(self, url):
        """Возвращает полную информацию о книге."""
        elem = self.findone('.eText', url)
        book = {}

        author = elem.find('h1').find('a')
        book['author'] = author.text
        book['author_url'] = self.get_abs_url(author.get('href'))

        book['title'] = author.tail.strip(whitespace + '.')

        description = [e.text.strip() for e in self.findall('p', tree=elem) if e.text]
        book['description'] = '\n'.join(description)

        fb2_url = self.findone('div a[href$=".zip"]', tree=elem)

        if fb2_url is not None:
            book['fb2_url'] = self.get_abs_url(fb2_url.get('href'))

        epub_url = self.findone('div a[href$=".epub"]', tree=elem)

        if epub_url is not None:
            book['epub_url'] = self.get_abs_url(epub_url.get('href'))

        return book

    def get_index(self):
        """Возвращает алфавитный указатель в виде словаря."""
        return {a.text.lower(): a.get('href') for a in self.findall('#s1 a', '/')}

    def search(self, query):
        """Выполняет поиск в каталоге по алфавитному указателю."""
        first_letter = query[0].lower()
        url = self.get_index().get(first_letter)

        if url:
            for a in self.findall(f'h2 + p a:contains("{query}")', url):
                yield a.get('href'), a.text

    def iter_books(self, url):
        """Итетирует все книги с учетом пагинации с первой переданной страницы."""
        return BookIterator(self, url)


class BookIterator(object):
    def __init__(self, parser, base_url):
        self.parser = parser
        self.base_url = base_url

        show_count_element = self.parser.findone('.numShown73', url=self.base_url)

        self.show_count = int(show_count_element.text.split('-').pop())
        self.count = int(show_count_element.getparent().getparent().find('b').text)

    def __iter__(self):
        if self.count:
            count_pages = math.ceil(self.count / self.show_count) + 1

            for i in range(1, count_pages):
                for a in self.parser.findall('#allEntries .My a', url=f'{self.base_url}-{i}'):
                    yield self.parser.get_book(a.get('href'))


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
                           length=books.count) as bar:
        for book in bar:
            url = book.get(f'{file_format}_url')
            path = os.path.join(dest, book['author'])

            if not os.path.exists(path):
                os.mkdir(path, 0o755)

            path = os.path.join(path, filename_template.format(
                author=book['author'], title=book['title']
            ))

            _, ext = os.path.splitext(url)
            path += ext

            download(url, path)
            sleep(0.1)
