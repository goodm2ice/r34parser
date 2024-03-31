from urllib.parse import urljoin, quote_plus
from dataclasses import dataclass
import argparse
import logging
import re
import os
import time
import shutil
import math
import json
import locale

import requests
from bs4 import BeautifulSoup as bs
from rich.logging import RichHandler
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, TimeElapsedColumn

LOCALES = [f[:-5] for f in os.listdir(os.path.join(os.path.dirname(__file__), f'locales')) if f.endswith('.json')]

DOMAIN = 'https://rule34.xxx/'
LIST_URL_TEMPLATE = urljoin(DOMAIN, '/index.php?page=post&s=list&tags=%(tags)s&pid=%(pid)d')
FILE_URL_TEMPLATE = urljoin(DOMAIN, '/index.php?page=post&s=view&id=%(id)s')

THUMBS_ON_PAGE = 42


class Translator:
    def __init__(self, _locale = None):
        new_locale = _locale or locale.getlocale()[0]
        try:
            self.change_locale(new_locale)
        except:
            try:
                self.change_locale('ru_RU')
            except:
                try:
                    self.change_locale('en_US')
                except Exception as e:
                    logging.critical(e)
                    exit(1)

    def change_locale(self, new_locale: str):
        path = Translator.get_locale_path(new_locale)
        if not os.path.exists(path) or not os.path.isfile(path):
            raise FileNotFoundError('Locale file not found')
        messages = None
        with open(path, 'r', encoding='utf-8') as f:
            messages = json.load(f)
        self.locale = new_locale
        self.locale_path = path
        self.messages = messages

    @staticmethod
    def get_locale_path(locale):
        return os.path.join(os.path.dirname(__file__), f'locales/{locale}.json')

    def register(self):
        global _
        _ = lambda name, *args, **kwargs: self.translate(name, *args, **kwargs)

    def translate(self, name, *args, **kwargs):
        return self.messages.get(name, f'<{name}>').format(*args, **kwargs)


class DownloadProgress(Progress):
    def get_renderables(self):
        for task in self.tasks:
            match task.fields.get('progress_type'):
                case 'total':
                    self.columns = (
                        TextColumn("[progress.description]{task.description} {task.completed}/{task.total}"),
                        BarColumn(bar_width=None),
                        TaskProgressColumn(),
                        TimeRemainingColumn(),
                        TimeElapsedColumn()
                    )
                case 'page':
                    self.columns = (
                        TextColumn("{task.description} {task.completed}/{task.total}"),
                        BarColumn(bar_width=None),
                        TaskProgressColumn(),
                        TimeRemainingColumn()
                    )
                case _:
                    self.columns = (
                        TextColumn("{task.description}"),
                        BarColumn(bar_width=None),
                        TaskProgressColumn(),
                        TimeRemainingColumn()
                    )
            yield self.make_tasks_table([task])


class Session(requests.Session):
    delay: int
    next_request: float

    def __init__(self, delay: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.delay = delay
        self.next_request = 0

        self.cookies.update({ 'resize-original': '1' })
        self.headers.update({
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def request(self, *args, **kwargs):
        current_time = time.time()
        if self.next_request > current_time:
            time.sleep((self.next_request - current_time) / 1000)

        self.next_request = current_time + self.delay
        return super().request(*args, **kwargs)


def prepare_dir(path: str):
    out_dir = path
    if not out_dir:
        out_dir = os.path.join(os.getcwd(), './*')

    if out_dir[-1] == '*':
        out_dir = os.path.join(out_dir[:-1], ' '.join(args.tags))

    out_dir = os.path.abspath(out_dir)
    if not os.path.exists(out_dir) or not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    return out_dir


def get_count_by_thumbs(soup: bs) -> int | None:
    post_list = soup.find('div', id='post-list')
    if not post_list:
        return None
    return len(post_list.find_all('span', class_='thumb'))


def get_count(soup: bs) -> int | None:
    file_count = get_count_by_thumbs(soup)

    paginator = soup.find('div', id='paginator')
    if not paginator:
        return file_count

    links = paginator.find_all('a')
    if len(links) <= 0:
        return file_count

    def get_pid(href):
        try:
            return int(re.search(r'(?<=pid=)\d+', href).group(0))
        except Exception:
            return None

    file_count = get_pid(links[-1]['href']) or file_count

    return file_count


@dataclass
class RequestInfo:
    file_count: int
    page_count: int


def get_request_info(session: requests.Session, tags: list, skip: int = 0) -> RequestInfo:
    url = LIST_URL_TEMPLATE % {
        'tags': quote_plus(' '.join(tags)),
        'pid': (skip // THUMBS_ON_PAGE) * THUMBS_ON_PAGE,
    }

    page = session.get(url)
    soup = bs(page.content, 'lxml')

    file_count = max((get_count(soup) or 0) - skip, 0)
    page_count = (file_count // THUMBS_ON_PAGE) + 1

    return RequestInfo(file_count, page_count)


def get_extension(url: str):
    m = re.search(r'\.\w+', os.path.splitext(url)[1] or '')
    if not m:
        return '.jpg'
    return m.group(0)


def download_file(session: requests.Session, url: str, path: str, on_progress, on_start):
    file_stream = session.get(url, stream=True)
    if file_stream.status_code != 200:
        logging.warning(_('file_loading_error', url=url))
    total_length = file_stream.headers.get('content-length')
    if total_length:
        total_length = int(total_length)
    else:
        total_length = 0
    if on_start:
        on_start(total_length)
    with open(path, 'wb') as f:
        if total_length > 0:
            for data in file_stream.iter_content(chunk_size=4096):
                f.write(data)
                if on_progress:
                    on_progress(len(data))
        else:
            f.write(file_stream.content)


@dataclass
class R34File:
    session: requests.Session
    id: int
    thumbnail_url: str
    page: bs | None = None
    props = None

    def load_page(self) -> None:
        url = FILE_URL_TEMPLATE % { 'id': self.id }
        page = session.get(url)
        self.page = bs(page.content, 'lxml')

    def load_props(self) -> None:
        if not self.page:
            self.load_page()
        tag_sidebar = self.page.find('ul', id='tag-sidebar')
        tag_types = ('copyright', 'character', 'artist', 'general', 'metadata')
        props = { 'id': self.id }
        for tag_type in tag_types:
            li_list = tag_sidebar.findAll('li', class_=f'tag-type-{tag_type}')
            out = []
            for li in li_list:
                if len(li) < 1:
                    continue
                href = li.findAll('a')[-1]['href']
                idx = href.find('&tags=')
                if idx < 0:
                    continue
                out.append(href[idx+6:])

            props[tag_type] = ' '.join(out)
        
        self.props = props


    def download(self, path: str, format: str | None = None, pid: int | None = None, *args, **kwargs) -> None:
        if not self.page or not self.props:
            self.load_page()
            self.load_props()
        image_elm = self.page.find('img', id='image')
        video_elm = self.page.find('video', id='gelcomVideoPlayer')
        if video_elm:
            video_elm = video_elm.find('source')
        if not image_elm and not video_elm:
            logging.warning(_('page_content_not_found', url=url))
            return

        def get_filename(ext: str):
            return (format or '{id}{ext}').format(ext=ext, pid=pid, **self.props)

        if video_elm:
            file_url = video_elm['src']
            ext = get_extension(file_url)
            download_file(self.session, file_url, os.path.join(path, get_filename(ext)), *args, **kwargs)
        if image_elm:
            file_url = image_elm['src']
            ext = get_extension(file_url)
            download_file(self.session, file_url, os.path.join(path, get_filename(ext)), *args, **kwargs)


    def download_thumbnail(self, path: str, *args, **kwargs):
        ext = get_extension(self.thumbnail_url)
        download_file(self.session, self.thumbnail_url, os.path.join(path, f'thumb_{self.id}{ext}'), *args, **kwargs)


def get_page_images(session: requests.Session, tags: list[str], skip: int = 0):
    url = LIST_URL_TEMPLATE % {
        'tags': quote_plus(' '.join(tags)),
        'pid': (skip // THUMBS_ON_PAGE) * THUMBS_ON_PAGE,
    }

    page = session.get(url)
    soup = bs(page.content, 'lxml')
    post_list = soup.find('div', id='post-list')
    if not post_list:
        logging.warning(_('preview_not_found'))
        return []
    preview_links = post_list.find_all('span', class_='thumb')
    images = []
    for link in preview_links:
        id = int(link['id'][1:])
        thumbnail_url = link.find('img', class_='preview')['src']
        images.append(R34File(session, id, thumbnail_url))
    return images


if __name__ == '__main__':
    logging.basicConfig(level=logging.NOTSET, format='%(message)s', datefmt='[%X]', handlers=[RichHandler()])

    env_lang = os.environ['LANG']
    lang = list(filter(lambda x: x.find(env_lang) >= 0, LOCALES))
    lang = lang[0] if len(lang) > 0 else None

    translator = Translator(lang)
    translator.register()

    parser = argparse.ArgumentParser(prog='r34parser', description=_('prog_description'))
    parser.add_argument('-d', '--delay', type=int, default=1000, help=_('arg_delay_help'))
    parser.add_argument('-s', '--skip', type=int, default=0, help=_('arg_skip_help'))
    parser.add_argument('-c', '--count', default='1p', help=_('arg_count_help'))
    parser.add_argument('-t', '--thumbnails-only', action='store_true', help=_('arg_thumbnails_only_help'))
    parser.add_argument('-o', '--output-directory', type=str, help=_('arg_output_directory_help'))
    parser.add_argument('-f', '--format', type=str, help=_('arg_format_help'))
    parser.add_argument('--locale', choices=LOCALES, default=lang or 'ru_RU', help=_('arg_locale_help'))
    parser.add_argument('-v', '--verbose', action='count', default=0)

    parser.add_argument('tags', nargs=argparse.REMAINDER, type=str, help=_('arg_tags_help'))

    args = parser.parse_args()

    translator.change_locale(args.locale)

    log_level = (2 - min(args.verbose, 2)) * 10
    logging.basicConfig(level=log_level, format='%(message)s', datefmt='[%X]', handlers=[RichHandler()])

    session = Session(args.delay)

    info = get_request_info(session, args.tags, args.skip)

    if info.file_count > 0:
        logging.info(_('founded_files', files=info.file_count, pages=info.page_count))
    else:
        logging.error(_('content_not_found'))
        exit(1)

    logging.info(_('search_tags', tags=' '.join(args.tags)))

    out_dir = prepare_dir(args.output_directory)
    logging.info(_('output_directory', directory=out_dir))

    page_count = 0
    count = 0
    if args.count[-1] == 'p':
        page_count = int(args.count[:-1])
        count = page_count * THUMBS_ON_PAGE
    else:
        count = int(args.count)
        page_count = math.ceil(count / THUMBS_ON_PAGE)
    count = min(count, info.file_count - args.skip)
    page_count = min(page_count, info.page_count - math.ceil(args.skip / THUMBS_ON_PAGE))
    logging.debug(_('download_count', pages=page_count, files=count))

    pid = 0
    page_idx = 1
    try:
        with DownloadProgress(expand=True) as progress:
            total_task = progress.add_task(_('total_pages'), total=page_count, progress_type='total')
            page_task = progress.add_task(_('current_page'), total=THUMBS_ON_PAGE, progress_type='page')
            file_task = progress.add_task(_('current_file'), total=0, progress_type='file')
            
            def on_file_start(total):
                progress.update(file_task, total=total, completed=0)

            def on_file_update(advance):
                progress.update(file_task, advance=advance)

            while pid < count:
                files = get_page_images(session, args.tags, (args.skip // THUMBS_ON_PAGE) * THUMBS_ON_PAGE + pid)
                progress.update(page_task, total=len(files), completed=0)
                for file in files:
                    pid += 1
                    if args.thumbnails_only:
                        file.download_thumbnail(out_dir, on_start=on_file_start, on_progress=on_file_update)
                    else:
                        file.download(out_dir, args.format, pid, on_start=on_file_start, on_progress=on_file_update)
                    progress.update(page_task, advance=1)
                page_idx += 1
                progress.update(total_task, advance=1)
    except KeyboardInterrupt:
        logging.critical(_('exiting'))
        exit(1)
