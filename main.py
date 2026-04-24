"""
Парсер треков из плейлиста "Мне нравится" — Яндекс Музыка (веб).

Особенности:
  - Поддерживает URL вида /playlists/lk.xxxx (не только /users/login/playlists/3)
  - Обходит VirtualScroll (треки рендерятся только в видимой зоне)
  - Закрывает рекламные попапы
  - Использует актуальные классы: CommonTrack_root__, TrackPlaylist_*

Установка:
    pip install selenium webdriver-manager

Запуск:
    python yandex_music_parser.py
"""

import time
import json
import csv
import re
from dataclasses import dataclass, asdict
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    NoSuchElementException, ElementClickInterceptedException, StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager


# ══════════════════════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ══════════════════════════════════════════════════════════════════════════════

# Вставьте ссылку из адресной строки браузера:
PLAYLIST_URL = "https://music.yandex.ru/playlists/lk.959bcd2e-7f4d-44f7-ae9c-b7987c6c4208"

OUTPUT_CSV  = "liked_tracks.csv"
OUTPUT_JSON = "liked_tracks.json"

# Пауза после каждого шага скролла (сек) — увеличьте если интернет медленный
SCROLL_PAUSE   = 1.5
# Сколько шагов без новых треков → считаем что всё загружено
SCROLL_RETRIES = 6
# Ожидание авторизации (сек)
LOGIN_TIMEOUT  = 90
HEADLESS       = False

# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class Track:
    index:        int
    title:        str
    artist:       str
    duration:     str
    duration_sec: int


def duration_to_seconds(dur: str) -> int:
    parts = re.split(r"[:\.]", dur.strip())
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0


def build_driver() -> webdriver.Chrome:
    opts = webdriver.ChromeOptions()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1440,900")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-notifications")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"}
    )
    return driver


# ─── Закрытие рекламы ─────────────────────────────────────────────────────────

AD_SELECTORS = [
    "[class*='ads-banner__close']",
    "[class*='ad-close']", "[class*='AdClose']",
    "[class*='popup__close']", "[class*='Modal__close']", "[class*='modal__close']",
    "button[aria-label='Закрыть']", "button[aria-label='Close']",
    "[class*='notification__close']",
    "[class*='PromoMobile'] button", "[class*='promo-mobile__close']",
    "[class*='banner__close']", "[class*='advert'] button",
]

def close_ads(driver: webdriver.Chrome) -> None:
    for sel in AD_SELECTORS:
        try:
            for btn in driver.find_elements(By.CSS_SELECTOR, sel):
                if btn.is_displayed():
                    try:
                        btn.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.3)
                    print(f"  ✖ Закрыт попап: {sel}")
        except Exception:
            pass
    try:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    except Exception:
        pass


# ─── Парсинг трека из DOM-элемента ───────────────────────────────────────────
#
# Актуальная структура (апрель 2025):
#
#   div.CommonTrack_root__i6shE          ← весь трек
#     div.TrackPlaylist_playButtonCell__ ← кнопка play (с aria-label = "Артист — Название")
#     div.Meta_root__...
#       a.d-track__title  или span       ← название
#       a[href*='/artist/']              ← артист(ы)
#     div.TrackPlaylist_controlsBarCell__
#       span / time                      ← длительность
#

TITLE_SELECTORS = [
    "[class*='d-track__title']",
    "[class*='TrackTitle']",
    "[class*='track__name']",
    "[class*='Track__name']",
    "[class*='trackName']",
    "[class*='title_']",
    "a[class*='d-track']",
]

ARTIST_SELECTORS = [
    "[class*='d-track__artists']",
    "a[href*='/artist/']",
    "[class*='TrackArtists']",
    "[class*='track__artists']",
    "[class*='artists_']",
]

DURATION_SELECTORS = [
    "[class*='TrackDuration']",
    "[class*='track__duration']",
    "[class*='duration_']",
    "[class*='d-track__duration']",
    "time",
]


def find_text(el, selectors: list) -> str:
    for sel in selectors:
        try:
            nodes = el.find_elements(By.CSS_SELECTOR, sel)
            texts = [n.text.strip() for n in nodes if n.text.strip()]
            if texts:
                return " & ".join(texts)
        except Exception:
            pass
    return ""


def parse_via_aria(el) -> tuple:
    """
    Fallback: читаем aria-label кнопки Play — там обычно "Артист — Название".
    Возвращает (title, artist) или ("", "").
    """
    try:
        btn = el.find_element(By.CSS_SELECTOR, "[class*='playButtonCell'] [aria-label]")
        label = btn.get_attribute("aria-label") or ""
        # Формат: "Играть. Океан Ельзи — Вище неба"
        m = re.search(r"\.\s*(.+?)\s*[–—]\s*(.+)$", label)
        if m:
            return m.group(2).strip(), m.group(1).strip()
        return label.strip(), ""
    except Exception:
        return "", ""


def parse_track(el, index: int) -> Optional[Track]:
    title  = find_text(el, TITLE_SELECTORS)
    artist = find_text(el, ARTIST_SELECTORS)
    dur    = find_text(el, DURATION_SELECTORS)

    # Fallback через aria-label
    if not title:
        title, artist_fb = parse_via_aria(el)
        if not artist:
            artist = artist_fb

    # Fallback через data-атрибуты
    if not title:
        title = (el.get_attribute("data-title") or "").strip()

    # Длительность должна выглядеть как "3:45"
    if dur and not re.search(r"\d:\d", dur):
        dur = ""

    if not title:
        return None

    return Track(
        index=index,
        title=title,
        artist=artist or "—",
        duration=dur or "—",
        duration_sec=duration_to_seconds(dur),
    )


# ─── VirtualScroll: пошаговый скролл через ScrollIntoView ────────────────────

def scroll_virtual_list(driver: webdriver.Chrome, track_sel: str) -> list:
    """
    VirtualScroll рендерит только видимые элементы.
    Стратегия: находим последний видимый трек → scrollIntoView → ждём → повторяем.
    Собираем данные на каждом шаге чтобы не потерять треки которые выгрузились из DOM.
    """
    collected: dict = {}   # key -> Track
    idx = 1
    no_new = 0
    step   = 0

    while no_new < SCROLL_RETRIES:
        step += 1
        close_ads(driver)

        elements = driver.find_elements(By.CSS_SELECTOR, track_sel)
        if not elements:
            no_new += 1
            time.sleep(SCROLL_PAUSE)
            continue

        # Парсим всё что сейчас в DOM
        new_this_step = 0
        for el in elements:
            try:
                t = parse_track(el, idx)
                if t:
                    key = f"{t.title}|{t.artist}"
                    if key not in collected:
                        collected[key] = t
                        idx += 1
                        new_this_step += 1
            except StaleElementReferenceException:
                pass

        print(f"  Шаг {step:>3} | в DOM: {len(elements):>4} | всего собрано: {len(collected):>4}", end="\r")

        if new_this_step == 0:
            no_new += 1
        else:
            no_new = 0

        # Скроллим последний элемент в видимую область
        try:
            last = elements[-1]
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", last)
        except StaleElementReferenceException:
            driver.execute_script("window.scrollBy(0, 600);")

        time.sleep(SCROLL_PAUSE)

    print()  # перевод строки после \r
    return list(collected.values())


# ─── Главная функция ──────────────────────────────────────────────────────────

def scrape(url: str) -> list:
    print("=" * 62)
    print("   Яндекс Музыка — парсер 'Мне нравится'")
    print("=" * 62)

    driver = build_driver()

    # Актуальный класс корневого элемента трека из диагностики
    # (содержит 'CommonTrack_root')
    TRACK_SEL = "[class*='CommonTrack_root']"

    try:
        print(f"\n[1/4] Открываем: {url}")
        driver.get(url)
        time.sleep(3)

        print("[2/4] Закрываем рекламу...")
        for _ in range(4):
            close_ads(driver)
            time.sleep(0.8)

        print(f"[3/4] Ждём треки (до {LOGIN_TIMEOUT} сек)...")
        print("      Если нужна авторизация — войдите в открытом окне Chrome.")

        deadline = time.time() + LOGIN_TIMEOUT
        found = False
        while time.time() < deadline:
            close_ads(driver)
            els = driver.find_elements(By.CSS_SELECTOR, TRACK_SEL)
            if len(els) >= 1:
                print(f"\n  ✔ Найдено {len(els)} трек(ов) в DOM, начинаем скролл...")
                found = True
                break
            time.sleep(2)

        if not found:
            # Финальная диагностика
            print("\n⚠  Элементы CommonTrack_root не найдены. Классы на странице:")
            try:
                res = driver.execute_script("""
                    const m={};
                    document.querySelectorAll('*').forEach(e=>{
                        e.className.toString().split(' ').forEach(c=>{
                            c=c.trim();
                            if(c) m[c]=(m[c]||0)+1;
                        });
                    });
                    return Object.entries(m)
                        .filter(([k])=>/(track|Track|playlist|Playlist)/i.test(k))
                        .sort((a,b)=>b[1]-a[1]).slice(0,25)
                        .map(([k,v])=>k+' = '+v).join('\\n');
                """)
                print(res)
            except Exception as e:
                print(e)
            return []

        time.sleep(1)

        print("[4/4] Скроллим и собираем треки...")
        tracks = scroll_virtual_list(driver, TRACK_SEL)

        print(f"\n✅ Собрано уникальных треков: {len(tracks)}")
        return tracks

    finally:
        driver.quit()


# ─── Экспорт ──────────────────────────────────────────────────────────────────

def save_csv(tracks, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["index","title","artist","duration","duration_sec"])
        w.writeheader()
        w.writerows(asdict(t) for t in tracks)
    print(f"💾 CSV  → {path}")

def save_json(tracks, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(t) for t in tracks], f, ensure_ascii=False, indent=2)
    print(f"💾 JSON → {path}")

def print_summary(tracks):
    total = sum(t.duration_sec for t in tracks)
    h, r  = divmod(total, 3600)
    m     = r // 60
    print(f"\n{'─'*65}")
    print(f"  Треков: {len(tracks)}   |   Общая длительность: {h}ч {m}мин")
    print(f"{'─'*65}")
    print(f"{'#':>4}  {'Исполнитель':<28}  {'Название':<30}  Длит.")
    print("─" * 72)
    for t in tracks[:30]:
        a = (t.artist[:26]+"..") if len(t.artist)>28 else t.artist
        n = (t.title[:28] +"..") if len(t.title) >30 else t.title
        print(f"{t.index:>4}  {a:<28}  {n:<30}  {t.duration}")
    if len(tracks) > 30:
        print(f"       … и ещё {len(tracks)-30} треков")


# ─── Точка входа ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tracks = scrape(PLAYLIST_URL)
    if tracks:
        print_summary(tracks)
        save_csv(tracks,  OUTPUT_CSV)
        save_json(tracks, OUTPUT_JSON)