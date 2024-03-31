[Описание на русском](#russian)

# English
Simple parser for downloading video and images from rule34xxx
```bash
usage: r34parser [-h] [-d DELAY] [-s SKIP] [-c COUNT] [-t] [-o OUTPUT_DIRECTORY] [-f FORMAT] [--locale {en_US,ru_RU}] [-v] ...

Download files from R34 by search tags

positional arguments:
  tags                  'Search tags. Negative tags begins with `-`. Example: `r34parser sfw -nsfw`'

options:
  -h, --help            show this help message and exit
  -d DELAY, --delay DELAY
                        Delay between requests in ms. Needed to avoid getting banned. By default: 1000.
  -s SKIP, --skip SKIP  Skip first `SKIP` files.
  -c COUNT, --count COUNT
                        Downloading files/pages count (suffix `p` means pages). By default: 1p.
  -t, --thumbnails-only
                        Download preview only.
  -o OUTPUT_DIRECTORY, --output-directory OUTPUT_DIRECTORY
                        'Directory path for downloaded files. If it contains `*` at the end, a directory using the specified tags will be created at the specified location. By default, a
                        directory with tags in the name will be created.'
  -f FORMAT, --format FORMAT
                        Format for names of downloaded files. Available variables: id, pid, ext, artist, copyright, character, general, metadata. By default: `{id}{ext}`
  --locale {en_US,ru_RU}
                        Program output language
  -v, --verbose
```
## Dependencies
* `beautifulsoup4` - For HTML parsing
* `lxml` - For BeautifulSoup4
* `requests` - For downloading pages and files
* `rich` - For pretty logging

## Prepare for using
```bash
python -m venv venv
chmod +x ./venv/bin/activate
source ./venv/bin/activate
pip install -r requirements.txt
```

# Russian
Простой парсер для загрузки видео и изображений с rule34xxx
```bash
usage: r34parser [-h] [-d DELAY] [-s SKIP] [-c COUNT] [-t] [-o OUTPUT_DIRECTORY] [-f FORMAT] [--locale {en_US,ru_RU}] [-v] ...

Загружает файлы с R34 по вписанным тегам

positional arguments:
  tags                  'Теги для поиска. Негативные теги начинаются с `-`. Пример: `r34parser sfw -nsfw`'

options:
  -h, --help            show this help message and exit
  -d DELAY, --delay DELAY
                        Задержка между запросами в мс. Нужна чтобы не получить бан. По-умолчанию: 1000.
  -s SKIP, --skip SKIP  Пропустить первые `SKIP` файлов.
  -c COUNT, --count COUNT
                        Как много необходимо скачать (суффикс `p` означает считать в страницах). По-умолчанию: 1p.
  -t, --thumbnails-only
                        Скачать только превью.
  -o OUTPUT_DIRECTORY, --output-directory OUTPUT_DIRECTORY
                        'Путь для скачанных файлов. Если в конце содержит `*`, в указанном месте будет добавлена директория по заданным тегам. По-умолчанию будет создана директория с тегами в
                        названии.'
  -f FORMAT, --format FORMAT
                        Формат для имён загруженных файлов. Доступные переменные: id, pid, ext, artist, copyright, character, general, metadata. По-умолчанию: `{id}{ext}`
  --locale {en_US,ru_RU}
                        Язык вывода программы
  -v, --verbose
```

## Зависимости
* `beautifulsoup4` - Для парсинга HTML
* `lxml` - Для BeautifulSoup4
* `requests` - Для загрузки страниц и файлов
* `rich` - Для красивого логгирования

## Подготовка к запуску
```bash
python -m venv venv
chmod +x ./venv/bin/activate
source ./venv/bin/activate
pip install -r requirements.txt
```
