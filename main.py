from urllib.parse import urljoin, quote_plus
from dataclasses import dataclass
import argparse
import logging
import re
import os
import time
import shutil
import math

import requests
from bs4 import BeautifulSoup as bs
from rich.logging import RichHandler
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, TimeElapsedColumn

DOMAIN = 'https://rule34.xxx/'
LIST_URL_TEMPLATE = urljoin(DOMAIN, '/index.php?page=post&s=list&tags=%(tags)s&pid=%(pid)d')
IMG_URL_TEMPLATE = urljoin(DOMAIN, '/index.php?page=post&s=view&id=%(id)s')

IMAGES_ON_PAGE = 42


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
    image_count = get_count_by_thumbs(soup)

    paginator = soup.find('div', id='paginator')
    if not paginator:
        return image_count

    links = paginator.find_all('a')
    if len(links) <= 0:
        return image_count

    def get_pid(href):
        try:
            return int(re.search(r'(?<=pid=)\d+', href).group(0))
        except Exception:
            return None

    image_count = get_pid(links[-1]['href']) or image_count

    return image_count


@dataclass
class RequestInfo:
    image_count: int
    page_count: int


def get_request_info(session: requests.Session, tags: list, skip: int = 0) -> RequestInfo:
    url = LIST_URL_TEMPLATE % {
        'tags': quote_plus(' '.join(tags)),
        'pid': (skip // IMAGES_ON_PAGE) * IMAGES_ON_PAGE,
    }

    page = session.get(url)
    soup = bs(page.content, 'lxml')

    image_count = max((get_count(soup) or 0) - skip, 0)
    page_count = (image_count // IMAGES_ON_PAGE) + 1

    return RequestInfo(image_count, page_count)


def get_extension(url: str):
    m = re.search(r'\.\w+', os.path.splitext(url)[1] or '')
    if not m:
        return '.jpg'
    return m.group(0)


def download_image(session: requests.Session, url: str, path: str, on_progress, on_start):
    image_stream = session.get(url, stream=True)
    if image_stream.status_code != 200:
        logging.warning(f'Ошибка загрузки изображения "{url}"')
    total_length = image_stream.headers.get('content-length')
    if total_length:
        total_length = int(total_length)
    else:
        total_length = 0
    if on_start:
        on_start(total_length)
    with open(path, 'wb') as f:
        if total_length > 0:
            for data in image_stream.iter_content(chunk_size=4096):
                f.write(data)
                if on_progress:
                    on_progress(len(data))
        else:
            f.write(image_stream.content)
            # image_stream.raw.decode_content = True
            # shutil.copyfileobj(image_stream.raw, f)


@dataclass
class R34Image:
    session: requests.Session
    id: int
    thumbnail_url: str

    def download(self, path: str, *args, **kwargs) -> None:
        url = IMG_URL_TEMPLATE % { 'id': self.id }
        page = session.get(url)
        soup = bs(page.content, 'lxml')
        image_elm = soup.find('img', id='image')
        if not image_elm:
            logging.warning(f'Изображение не найдено на странице {url}')
            return
        image_url = soup.find('img', id='image')['src']

        ext = get_extension(image_url)
        download_image(self.session, image_url, os.path.join(path, f'{self.id}{ext}'), *args, **kwargs)

    def download_thumbnail(self, path: str, *args, **kwargs):
        ext = get_extension(self.thumbnail_url)
        download_image(self.session, self.thumbnail_url, os.path.join(path, f'thumb_{self.id}{ext}'), *args, **kwargs)


def get_page_images(session: requests.Session, tags: list[str], skip: int = 0):
    url = LIST_URL_TEMPLATE % {
        'tags': quote_plus(' '.join(tags)),
        'pid': (skip // IMAGES_ON_PAGE) * IMAGES_ON_PAGE,
    }

    page = session.get(url)
    soup = bs(page.content, 'lxml')
    post_list = soup.find('div', id='post-list')
    if not post_list:
        logging.warning('Блок превью не найден на странице')
        return []
    preview_links = post_list.find_all('span', class_='thumb')
    images = []
    for link in preview_links:
        id = int(link['id'][1:])
        thumbnail_url = link.find('img', class_='preview')['src']
        images.append(R34Image(session, id, thumbnail_url))
    return images


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='r34parser',
        description='Загружает картинки по тегам с R34',
    )

    parser.add_argument('-d', '--delay', type=int, default=1000, help='Задержка между запросами в мс. По-умолчанию: %(default)s.')
    parser.add_argument('-s', '--skip', type=int, default=0, help='Пропустить первые `SKIP` изображений.')
    parser.add_argument('-c', '--count', default='1p', help='Как много необходимо скачать (суффикс `p` означает считать в страницах). По-умолчанию: %(default)s.')
    parser.add_argument('-t', '--thumbnails-only', action='store_true', help='Скачать только превью.')
    parser.add_argument('-v', '--verbose', action='count', default=0)
    parser.add_argument('-o', '--output-directory', type=str, help='Путь для скачанных изображений. По-умолчанию будет создана директория с тегами в названии.')

    parser.add_argument('tags', nargs=argparse.REMAINDER, type=str, help='Теги для поиска. Негативные теги начинаются с `-`. Пример: `%(prog)s sfw -nsfw`')

    args = parser.parse_args()

    log_level = (2 - min(args.verbose, 2)) * 10
    logging.basicConfig(level=log_level, format='%(message)s', datefmt='[%X]', handlers=[RichHandler()])

    session = Session(args.delay)

    info = get_request_info(session, args.tags, args.skip)

    if info.image_count > 0:
        logging.info(f'Найдено {info.image_count} изображений на {info.page_count} страницах!')
    else:
        logging.error('Изображения не найдены! Выход...')
        exit(1)

    logging.info(f'Поиск по тегам: "{" ".join(args.tags)}"')

    out_dir = prepare_dir(args.output_directory)
    logging.info(f'Конечная директория: "{out_dir}"')

    page_count = 0
    count = 0
    if args.count[-1] == 'p':
        page_count = int(args.count[:-1])
        count = page_count * IMAGES_ON_PAGE
    else:
        count = int(args.count)
        page_count = math.ceil(count / IMAGES_ON_PAGE)
    count = min(count, info.image_count - args.skip)
    page_count = min(page_count, info.page_count - math.ceil(args.skip / IMAGES_ON_PAGE))
    logging.debug(f'Будет загружено: {page_count} страниц, {count} изображений')

    pid = 0
    page_idx = 1
    try:
        with DownloadProgress(expand=True) as progress:
            total_task = progress.add_task('Всего страниц:', total=page_count, progress_type='total')
            page_task = progress.add_task('Текущая страница:', total=IMAGES_ON_PAGE, progress_type='page')
            file_task = progress.add_task('Текущий файл:', total=0, progress_type='file')
            
            def on_file_start(total):
                progress.update(file_task, total=total, completed=0)

            def on_file_update(advance):
                progress.update(file_task, advance=advance)

            while pid < count:
                files = get_page_images(session, args.tags, (args.skip // IMAGES_ON_PAGE) * IMAGES_ON_PAGE + pid)
                progress.update(page_task, total=len(files), completed=0)
                for image in files:
                    if args.thumbnails_only:
                        image.download_thumbnail(out_dir, on_start=on_file_start, on_progress=on_file_update)
                    else:
                        image.download(out_dir, on_start=on_file_start, on_progress=on_file_update)
                    pid += 1
                    progress.update(page_task, advance=1)
                page_idx += 1
                progress.update(total_task, advance=1)
    except KeyboardInterrupt:
        logging.critical('Выход...')
        exit(1)