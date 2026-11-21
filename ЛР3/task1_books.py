import argparse
import csv
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from lxml import html

START_URL = "https://books.toscrape.com/"
FIELDS = ["page", "title", "price_gbp", "availability", "rating", "book_url"]
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def normalize(text):
    return " ".join(str(text).split())


def format_price(text):
    match = re.search(r"\d+[.,]\d{2}", normalize(text))
    if not match:
        raise ValueError(f"Не удалось определить цену: {text!r}")
    return match.group().replace(".", ",")


def parse_bs4(body, url, page):
    soup = BeautifulSoup(body, "html.parser")
    rows = []
    for item in soup.select("article.product_pod"):
        anchor = item.select_one("h3 a")
        price = item.select_one("p.price_color")
        availability = item.select_one("p.instock.availability")
        stars = item.select_one("p.star-rating")
        if not (anchor and price):
            continue
        css_classes = stars.get("class", []) if stars else []
        rating = next((RATINGS[c] for c in css_classes if c in RATINGS), None)
        rows.append({
            "page": page,
            "title": anchor.get("title", normalize(anchor.get_text(" ", strip=True))),
            "price_gbp": format_price(price.get_text(" ", strip=True)),
            "availability": normalize(availability.get_text(" ", strip=True)) if availability else "",
            "rating": rating,
            "book_url": urljoin(url, anchor.get("href", "")),
        })
    next_node = soup.select_one("li.next a[href]")
    next_url = urljoin(url, next_node["href"]) if next_node else None
    return rows, next_url


def xpath_text(node, expression):
    found = node.xpath(expression)
    return normalize(found[0]) if found else ""


def parse_lxml(body, url, page):
    root = html.fromstring(body)
    rows = []
    for item in root.xpath('//article[contains(concat(" ", normalize-space(@class), " "), " product_pod ")]'):
        title = xpath_text(item, ".//h3/a/@title") or xpath_text(item, ".//h3/a/text()")
        link = xpath_text(item, ".//h3/a/@href")
        price = xpath_text(item, './/p[contains(concat(" ", normalize-space(@class), " "), " price_color ")]/text()')
        stock = normalize(" ".join(item.xpath('.//p[contains(@class,"availability")]//text()')))
        classes = xpath_text(item, './/p[contains(@class,"star-rating")]/@class').split()
        rating = next((RATINGS[c] for c in classes if c in RATINGS), None)
        if not (title and price):
            continue
        rows.append({
            "page": page, "title": title, "price_gbp": format_price(price),
            "availability": stock, "rating": rating, "book_url": urljoin(url, link),
        })
    next_links = root.xpath('//li[contains(concat(" ",normalize-space(@class)," ")," next ")]/a/@href')
    next_url = urljoin(url, next_links[0]) if next_links else None
    return rows, next_url


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def scrape(max_pages=0, pause=0.35):
    session = requests.Session()
    session.headers.update({"User-Agent": "Student-Lab-WebScraping/1.0 (educational; respectful delay)"})
    seen_pages = set()
    pages_bs, pages_lxml = [], []
    url = START_URL
    page = 0
    while url and url not in seen_pages:
        if max_pages and page >= max_pages:
            break
        seen_pages.add(url)
        response = session.get(url, timeout=(10, 30))
        response.raise_for_status()
        page += 1
        body = response.content.decode("utf-8-sig")
        rows_bs, next_bs = parse_bs4(body, response.url, page)
        rows_lxml, next_lxml = parse_lxml(body, response.url, page)
        if not rows_bs or not rows_lxml:
            raise RuntimeError(f"Страница {page}: не удалось получить записи каталога")
        if rows_bs != rows_lxml:
            raise RuntimeError(f"Страница {page}: результаты BeautifulSoup и lxml различаются")
        if next_bs != next_lxml:
            raise RuntimeError(f"Страница {page}: алгоритмы различаются в следующей странице")
        pages_bs.extend(rows_bs)
        pages_lxml.extend(rows_lxml)
        logging.info("Страница %s: %s книг, всего %s", page, len(rows_bs), len(pages_bs))
        url = next_bs
        if url:
            time.sleep(pause)
    if not pages_bs:
        raise RuntimeError("Сайт не отдал каталог книг")
    if len({item["book_url"] for item in pages_bs}) != len(pages_bs):
        raise RuntimeError("Обнаружены повторяющиеся книги; необходимо проверить навигацию")
    output = Path("results")
    write_csv(output / "books_beautifulsoup.csv", pages_bs)
    write_csv(output / "books_lxml.csv", pages_lxml)
    logging.info("Готово: страниц %s, книг %s. Два CSV сохранены.", page, len(pages_bs))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--pause", type=float, default=0.35)
    args = parser.parse_args()
    Path("results").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("results/task1_books.log", encoding="utf-8"),
        ],
    )
    scrape(max_pages=args.max_pages, pause=args.pause)
