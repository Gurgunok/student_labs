import scrapy
from scrapy.exporters import CsvItemExporter


class ExcelCsvItemExporter(CsvItemExporter):
    def __init__(self, file, **kwargs):
        kwargs["delimiter"] = ";"
        super().__init__(file, **kwargs)


class ScrollQuotesSpider(scrapy.Spider):
    name = "scroll_quotes"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/scroll"]
    custom_settings = {
        "DOWNLOAD_DELAY": 0.35,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "FEED_EXPORT_ENCODING": "utf-8-sig",
        "FEED_EXPORT_FIELDS": ["page", "text", "author", "tags", "author_goodreads"],
        "FEED_EXPORTERS": {"csv": ExcelCsvItemExporter},
        "LOG_LEVEL": "INFO",
    }

    def parse(self, response):
        self.logger.info("Открыта страница бесконечной прокрутки: %s", response.url)
        yield response.follow("/api/quotes?page=1", callback=self.parse_api)

    def parse_api(self, response):
        payload = response.json()
        page = payload.get("page")
        quotes = payload.get("quotes", [])
        if not quotes:
            self.logger.warning("Страница API %s не содержит цитат", page)
        for quote in quotes:
            author = quote.get("author") or {}
            yield {
                "page": page,
                "text": quote.get("text", ""),
                "author": author.get("name", ""),
                "tags": " | ".join(quote.get("tags", [])),
                "author_goodreads": author.get("goodreads_link", ""),
            }
        self.logger.info("Страница API %s: собрано %s цитат", page, len(quotes))
        if payload.get("has_next"):
            next_page = int(page) + 1
            yield response.follow(f"/api/quotes?page={next_page}", callback=self.parse_api)

    def closed(self, reason):
        stats = self.crawler.stats.get_stats()
        count = stats.get("item_scraped_count", 0)
        self.logger.info("Завершение: %s; сохранено цитат: %s", reason, count)
        if not count:
            self.logger.error("Сбор завершён без данных")
