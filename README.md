# Простой парсер для загрузки изображений с rule34xxx
```bash
usage: r34parser [-h] [-d DELAY] [-s SKIP] [-c COUNT] [-t] [-v] [-o OUTPUT_DIRECTORY] ...

Загружает файлы с R34 по вписанным тегам

positional arguments:
  tags                  Теги для поиска. Негативные теги начинаются с `-`. Пример: `r34parser sfw -nsfw`

options:
  -h, --help            show this help message and exit
  -d DELAY, --delay DELAY
                        Задержка между запросами в мс. Нужна чтобы не получить бан. По-умолчанию: 1000.
  -s SKIP, --skip SKIP  Пропустить первые `SKIP` файлов.
  -c COUNT, --count COUNT
                        Как много необходимо скачать (суффикс `p` означает считать в страницах). По-умолчанию: 1p.
  -t, --thumbnails-only
                        Скачать только превью.
  -v, --verbose
  -o OUTPUT_DIRECTORY, --output-directory OUTPUT_DIRECTORY
                        Путь для скачанных файлов. По-умолчанию будет создана директория с тегами в названии.
```

## Зависимости
* `beautifulsoup4` - Для парсинга HTML
* `lxml` - Для BeautifulSoup4
* `requests` - Для загрузки страниц и изображений
* `rich` - Для красивого логгирования

## Подготовка к запуску
```bash
python -m venv venv
chmod +x ./venv/bin/activate
source ./venv/bin/activate
pip install -r requirements.txt
```
