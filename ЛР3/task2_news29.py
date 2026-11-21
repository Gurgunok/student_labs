import argparse
import csv
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = "https://www.news29.ru"
SECTIONS = ["ekonomika", "obschestvo", "kultura"]
ARTICLE_PATH = re.compile(r"^/novosti/[^/]+/[^/]+/\d+/?$")
DATE_PATTERN = re.compile(r"\b\d{2}\.\d{2}\.\d{2,4}\s+\d{2}:\d{2}\b")
FIELDS = ["title", "publication_date", "url"]
MORE_XPATH = (
    "//*[self::button or self::a or self::div or self::span]"
    "[normalize-space(.)='Показать ещё' or normalize-space(.)='Показать еще']"
)


def extract_news(document, section):
    soup = BeautifulSoup(document, "html.parser")
    result = {}
    expected = f"/novosti/{section}/"
    for anchor in soup.find_all("a", href=True):
        link = urljoin(BASE, anchor["href"])
        url = urlparse(link)
        if url.netloc not in ("www.news29.ru", "news29.ru"):
            continue
        if not url.path.startswith(expected) or not ARTICLE_PATH.fullmatch(url.path):
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if not 12 <= len(title) <= 220:
            continue
        publication_date = ""
        parent = anchor
        for _ in range(5):
            parent = parent.parent
            if parent is None:
                break
            content = parent.get_text(" ", strip=True)
            if len(content) > 1400:
                continue
            match = DATE_PATTERN.search(content)
            if match:
                publication_date = match.group(0)
                break
        record = {"title": title, "publication_date": publication_date, "url": link}
        previous = result.get(link)
        if previous is None or (
            not previous["publication_date"] and record["publication_date"]
        ):
            result[link] = record
    return result


def dismiss_cookies(driver):
    candidates = driver.find_elements(
        By.XPATH,
        "//*[self::button or self::a or self::div or self::span]"
        "[normalize-space(.)='Понятно']",
    )
    for node in candidates:
        if not node.is_displayed():
            continue
        try:
            node.click()
            logging.info("Закрыто уведомление о cookies")
            return
        except WebDriverException:
            continue


def find_more(driver):
    elements = driver.find_elements(By.XPATH, MORE_XPATH)
    elements += driver.find_elements(
        By.CSS_SELECTOR, ".show-more, .load-more, .list-more, [class*='more-news']"
    )
    for element in elements:
        try:
            if element.is_displayed() and element.is_enabled():
                return element
        except StaleElementReferenceException:
            continue
    return None


def attempt(driver, section, clicks, timeout):
    url = f"{BASE}/novosti/{section}/"
    logging.info("Открываем рубрику: %s", url)
    driver.get(url)
    WebDriverWait(driver, 30).until(
        lambda browser: bool(extract_news(browser.page_source, section))
    )
    dismiss_cookies(driver)
    collected = extract_news(driver.page_source, section)
    initial = len(collected)
    logging.info("Рубрика %s: до нажатий %s новостей", section, initial)
    completed = 0
    for number in range(1, clicks + 1):
        button = find_more(driver)
        if button is None:
            logging.warning("Рубрика %s: кнопка не найдена", section)
            break
        previous = set(collected)
        details = button.get_attribute("outerHTML")
        logging.info("Найдена кнопка: %s", details[:350].replace("\n", " "))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        time.sleep(0.4)
        try:
            button.click()
        except (ElementClickInterceptedException, WebDriverException):
            logging.info("Нативный click не сработал, используем JavaScript click")
            driver.execute_script("arguments[0].click()", button)
        logging.info("Рубрика %s: нажатие %s выполнено, проверяем данные", section, number)
        try:
            WebDriverWait(driver, timeout, poll_frequency=0.5).until(
                lambda browser: bool(
                    set(extract_news(browser.page_source, section)) - previous
                )
            )
        except TimeoutException:
            logging.warning(
                "Рубрика %s: после нажатия %s новые записи не появились; URL %s",
                section, number, driver.current_url
            )
            break
        latest = extract_news(driver.page_source, section)
        collected.update(latest)
        difference = len(set(collected) - previous)
        completed += 1
        logging.info(
            "Рубрика %s: успешное нажатие %s, новых записей %s, всего %s",
            section, number, difference, len(collected)
        )
    return collected, completed, initial


def scrape(clicks=3, headless=False, timeout=25, sections=None):
    Path("results").mkdir(exist_ok=True)
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1440,1000")
    if headless:
        options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)
    sections = sections or SECTIONS
    try:
        for section in sections:
            try:
                rows, successful, initial = attempt(driver, section, clicks, timeout)
            except (TimeoutException, WebDriverException) as exc:
                logging.warning("Рубрика %s недоступна: %s", section, exc)
                continue
            if successful:
                output = Path("results/news29_selenium.csv")
                with output.open("w", encoding="utf-8-sig", newline="") as file:
                    writer = csv.DictWriter(file, fieldnames=FIELDS, delimiter=";")
                    writer.writeheader()
                    writer.writerows(rows.values())
                logging.info(
                    "ГОТОВО: рубрика %s, до нажатий %s, после %s, успешных нажатий %s. CSV: %s",
                    section, initial, len(rows), successful, output
                )
                return
        raise RuntimeError(
            "Ни в одной рубрике News29 не удалось подтвердить подгрузку новостей"
        )
    finally:
        driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clicks", type=int, default=3)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--sections", nargs="+", choices=SECTIONS, default=SECTIONS)
    args = parser.parse_args()
    Path("results").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("results/task2_news29.log", encoding="utf-8"),
        ],
    )
    scrape(clicks=args.clicks, headless=args.headless, timeout=args.timeout, sections=args.sections)
