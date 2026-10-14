import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
import openpyxl
import requests
import urllib3
from bs4 import BeautifulSoup
import yaml

# Suppress SSL warnings for local servers with self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Dynamic Playwright Check
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


# ==========================================
# 0. DUAL CONSOLE & FILE LOGGER (TEE)
# ==========================================
class TeeLogger:
    """Duplicates stdout to both the console terminal and scraper_output.log."""

    def __init__(self, filepath="scraper_output.log"):
        self.terminal = sys.stdout
        self.log_file = open(filepath, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()


# Redirect standard output to automatically maintain scraper_output.log
sys.stdout = TeeLogger("scraper_output.log")


# ==========================================
# 1. UNIVERSAL 3-TIER EVENT EXTRACTION ENGINE
# ==========================================
class UniversalEventExtractor:
    """Multi-tiered extractor that parses JSON-LD metadata, CSS selectors, or semantic HTML heuristics."""

    @staticmethod
    def extract_json_ld(soup, base_url, source_name, category, city):
        """Tier 1: Extract standard Schema.org JSON-LD event metadata."""
        events = []
        scripts = soup.find_all("script", type="application/ld+json")
        for s in scripts:
            if not s.string:
                continue
            try:
                data = json.loads(s.string)
                items = data if isinstance(data, list) else [data]

                flat_items = []
                for item in items:
                    if isinstance(item, dict) and "@graph" in item:
                        flat_items.extend(item["@graph"])
                    else:
                        flat_items.append(item)

                for item in flat_items:
                    if isinstance(item, dict) and item.get("@type") in [
                        "Event",
                        "SocialEvent",
                        "MusicEvent",
                        "TheaterEvent",
                        "EducationEvent",
                    ]:
                        title = item.get("name")
                        date_raw = (
                            item.get("startDate")
                            or item.get("doorTime")
                            or "Upcoming"
                        )
                        link = item.get("url") or base_url
                        full_link = urljoin(base_url, str(link))

                        if title and isinstance(title, str):
                            events.append(
                                {
                                    "title": title.strip(),
                                    "date_raw": str(date_raw).strip(),
                                    "category": category,
                                    "city": city,
                                    "venue": source_name,
                                    "link": full_link,
                                    "scraped_at": datetime.now().isoformat(),
                                    "extraction_tier": "Tier 1 (JSON-LD)",
                                }
                            )
            except Exception:
                continue
        return events

    @staticmethod
    def extract_by_selectors(soup, base_url, source_config):
        """Tier 2: Extract events using configured or auto-inferred CSS selectors."""
        events = []
        source_name = source_config["name"]
        selectors = source_config.get("selectors", {})

        card_sel = selectors.get(
            "card",
            "article, .event-card, .event-item, .sqs-events-collection-item, "
            "a.calendarData, tr.calendarRow, .type-tribe_events, .event",
        )
        title_sel = selectors.get(
            "title",
            "h1, h2, h3, h4, h5, .title, .event-title, .entry-title, .calendarDataTitle, strong",
        )
        date_sel = selectors.get(
            "date", "time, .date, .event-date, .date-time, .dtstart, .calendarDataDate"
        )
        link_sel = selectors.get("link", "a")

        cards = soup.select(card_sel)

        for card in cards:
            title_elem = card.select_one(title_sel)
            if not title_elem and card.name in ["h1", "h2", "h3", "h4", "a"]:
                title_elem = card
            title = title_elem.get_text(strip=True) if title_elem else None

            if not title or len(title) < 3:
                continue

            date_elem = card.select_one(date_sel)
            date_str = (
                date_elem.get_text(strip=True) if date_elem else "Upcoming"
            )

            if card.name == "a" and "href" in card.attrs:
                link = card["href"]
            else:
                link_elem = card.select_one(link_sel)
                link = (
                    link_elem["href"]
                    if link_elem and "href" in link_elem.attrs
                    else base_url
                )

            full_link = urljoin(base_url, link)

            events.append(
                {
                    "title": title,
                    "date_raw": date_str,
                    "category": source_config.get("category", "General Social"),
                    "city": source_config.get("city", "South Bend"),
                    "venue": source_name,
                    "link": full_link,
                    "scraped_at": datetime.now().isoformat(),
                    "extraction_tier": "Tier 2 (CSS Selectors)",
                }
            )

        return events

    @staticmethod
    def extract_by_heuristics(soup, base_url, source_config):
        """Tier 3: Fallback heuristic scanning for hyperlinked headings and dates."""
        events = []
        source_name = source_config["name"]
        date_pattern = re.compile(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{1,2}/\d{1,2}|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)",
            re.I,
        )

        links = soup.find_all("a")
        seen_titles = set()

        for a in links:
            title_elem = a.find(["h1", "h2", "h3", "h4", "h5"])
            title_text = (
                title_elem.get_text(strip=True)
                if title_elem
                else a.get_text(strip=True)
            )

            if (
                title_text
                and 5 <= len(title_text) <= 120
                and title_text not in seen_titles
            ):
                parent = a.find_parent(["div", "li", "tr", "td", "article"])
                parent_text = parent.get_text() if parent else ""

                if date_pattern.search(parent_text):
                    date_match = date_pattern.search(parent_text)
                    date_str = (
                        date_match.group(0) if date_match else "Upcoming"
                    )
                    link = a["href"] if "href" in a.attrs else base_url

                    events.append(
                        {
                            "title": title_text,
                            "date_raw": date_str,
                            "category": source_config.get(
                                "category", "General Social"
                            ),
                            "city": source_config.get("city", "South Bend"),
                            "venue": source_name,
                            "link": urljoin(base_url, link),
                            "scraped_at": datetime.now().isoformat(),
                            "extraction_tier": "Tier 3 (Semantic Heuristic)",
                        }
                    )
                    seen_titles.add(title_text)

            if len(events) >= 30:
                break

        return events


# ==========================================
# 2. AUTO-DISCOVERY EXCEL -> YAML SYNC
# ==========================================
def find_master_excel():
    """Locates the newest available Master Excel workbook in the working directory."""
    candidates = [
        "South_Bend_Master_Event_Sources_Cleaned.xlsx",
        "South_Bend_Master_Event_Sources_Cleaned_2.xlsx",
        "South_Bend_Master_Event_Sources_v3.xlsx",
        "South_Bend_Master_Event_Sources_v2.xlsx",
        "South_Bend_Master_Event_Sources.xlsx",
    ]
    for filename in candidates:
        if os.path.exists(filename):
            return filename

    glob_matches = glob.glob("*South_Bend*.xlsx") + glob.glob("*Master*.xlsx")
    return glob_matches[0] if glob_matches else None


def sync_excel_to_yaml(yaml_path="sources.yaml"):
    excel_path = find_master_excel()
    if not excel_path:
        print("⚠️ No Master Excel file found in folder. Skipping YAML sync.")
        return

    print(f"📖 Reading Master Directory from: '{excel_path}'")

    existing_sources = {}
    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                for source in data.get("sources", []):
                    existing_sources[source["id"]] = source
        except Exception as e:
            print(f"⚠️ Warning reading existing {yaml_path}: {e}")

    wb = openpyxl.load_workbook(excel_path)
    ws = wb.active

    updated_sources = []
    processed_ids = set()

    for row in range(5, ws.max_row + 1):
        category = ws.cell(row=row, column=1).value
        name = ws.cell(row=row, column=2).value
        url = ws.cell(row=row, column=3).value
        priority = ws.cell(row=row, column=6).value

        if not category or not name or not url:
            continue

        url_str = str(url).strip()
        if not url_str.startswith(("http://", "https://")):
            continue

        category_str = str(category).strip()
        name_str = str(name).strip()

        source_id = re.sub(
            r"[^a-z0-9_]", "", name_str.lower().replace(" ", "_")
        )
        if source_id in processed_ids or not source_id:
            continue
        processed_ids.add(source_id)

        existing_cfg = existing_sources.get(source_id, {})

        # SELF-HEALING PRESERVATION: Preserve enabled status & scraping_type if investigator updated them
        enabled_status = existing_cfg.get("enabled", True)
        if priority and "Disabled" in str(priority):
            enabled_status = False

        source_entry = {
            "id": source_id,
            "name": name_str,
            "url": url_str,
            "category": category_str,
            "city": existing_cfg.get("city", "South Bend"),
            "scraping_type": existing_cfg.get("scraping_type", "beautifulsoup"),
            "enabled": enabled_status,
            "priority": str(priority) if priority else "Medium",
            "selectors": existing_cfg.get(
                "selectors",
                {
                    "card": "article, .event-card, .event-item, .sqs-events-collection-item, .event, .listing, a.calendarData, tr.calendarRow",
                    "title": "h1, h2, h3, h4, .title, .event-title, .entry-title, .calendarDataTitle",
                    "date": "time, .date, .event-date, .date-time, .dtstart, .calendarDataDate",
                    "link": "a",
                },
            ),
        }

        updated_sources.append(source_entry)

    full_yaml_data = {
        "version": "1.0",
        "default_location": "South Bend, IN",
        "sources": updated_sources,
    }

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(
            full_yaml_data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    print(
        f"🔄 Sync Complete: Updated '{yaml_path}' with {len(updated_sources)} valid sources."
    )


# ==========================================
# 3. MAIN SCRAPER ENGINE WITH CACHING & SSL FIXES
# ==========================================
class EventScraperEngine:

    def __init__(
        self,
        config_path="sources.yaml",
        cache_path=".scrape_cache.json",
        cache_ttl_minutes=30,
    ):
        self.config_path = config_path
        self.cache_path = cache_path
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.sources = self._load_sources()
        self.cache = self._load_cache()
        self.extractor = UniversalEventExtractor()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.google.com/",
        }

    def _load_sources(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return data.get("sources", [])
        except Exception as e:
            print(f"❌ Error loading {self.config_path}: {e}")
            return []

    def _load_cache(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Failed to read cache file: {e}")
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save cache: {e}")

    def _get_valid_cache(self, source_id):
        if source_id not in self.cache:
            return None

        entry = self.cache[source_id]
        scraped_time_str = entry.get("timestamp")
        events = entry.get("events", [])

        if not scraped_time_str or not events:
            return None

        try:
            scraped_time = datetime.fromisoformat(scraped_time_str)
            if datetime.now() - scraped_time < self.cache_ttl:
                return events
        except Exception:
            return None

        return None

    def _set_cache(self, source_id, events):
        if events and len(events) > 0:
            self.cache[source_id] = {
                "timestamp": datetime.now().isoformat(),
                "count": len(events),
                "events": events,
            }
            self._save_cache()

    def scrape_with_playwright(self, url, source_config):
        if not PLAYWRIGHT_AVAILABLE:
            print(
                f"⚠️ Playwright not installed. Skipping browser render for {url}."
            )
            return []

        print(f"🎭 Rendering {url} using Playwright headless browser...")
        source_name = source_config["name"]
        category = source_config.get("category", "General Social")
        city = source_config.get("city", "South Bend")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                # Ignore HTTPS certificate errors to render local sites with self-signed certs
                context = browser.new_context(
                    user_agent=self.headers["User-Agent"],
                    ignore_https_errors=True,
                )
                page = context.new_page()
                page.goto(url, timeout=15000, wait_until="domcontentloaded")

                # Auto-scroll to trigger lazy-loaded Wix/Squarespace cards
                try:
                    page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight)"
                    )
                except Exception:
                    pass

                page.wait_for_timeout(3000)
                html_content = page.content()
                browser.close()

            soup = BeautifulSoup(html_content, "html.parser")

            events = self.extractor.extract_json_ld(
                soup, url, source_name, category, city
            )
            if not events:
                events = self.extractor.extract_by_selectors(
                    soup, url, source_config
                )
            if not events:
                events = self.extractor.extract_by_heuristics(
                    soup, url, source_config
                )

            return events

        except Exception as e:
            print(f"❌ Playwright Error for {source_name}: {e}")
            return []

    def scrape_source(self, source_config, retry_count=0):
        source_id = source_config["id"]
        source_name = source_config["name"]
        url = source_config["url"]
        category = source_config.get("category", "General Social")
        city = source_config.get("city", "South Bend")

        cached_events = self._get_valid_cache(source_id)
        if cached_events is not None:
            print(
                f"⚡ [CACHE HIT] {source_name}: Loaded {len(cached_events)} events (Scraped <30m ago)."
            )
            return cached_events

        print(f"🔍 Scraping: {source_name} ({url})...")

        try:
            response = requests.get(
                url, headers=self.headers, timeout=12, verify=False
            )

            # Route 403 Forbidden to Playwright
            if response.status_code == 403:
                print(
                    f"🛡️ Status 403 for '{source_name}'. Executing Playwright fallback..."
                )
                events = self.scrape_with_playwright(url, source_config)
                print(f"✅ Harvested {len(events)} events from {source_name}.")
                self._set_cache(source_id, events)
                return events

            # Base domain fallback on 404
            if response.status_code == 404 and retry_count == 0:
                parsed = urlparse(url)
                base_domain_url = f"{parsed.scheme}://{parsed.netloc}"
                if base_domain_url != url:
                    print(
                        f"⚠️ Status 404 for '{source_name}'. Retrying with root domain: {base_domain_url}"
                    )
                    source_config_copy = dict(source_config)
                    source_config_copy["url"] = base_domain_url
                    return self.scrape_source(
                        source_config_copy, retry_count=retry_count + 1
                    )

            if response.status_code != 200:
                print(
                    f"⚠️ Failed to reach {source_name} (Status {response.status_code})"
                )
                return []

            soup = BeautifulSoup(response.text, "html.parser")

            events = self.extractor.extract_json_ld(
                soup, url, source_name, category, city
            )

            if not events:
                events = self.extractor.extract_by_selectors(
                    soup, url, source_config
                )

            if not events:
                events = self.extractor.extract_by_heuristics(
                    soup, url, source_config
                )

            if not events and retry_count == 0 and PLAYWRIGHT_AVAILABLE:
                print(
                    f"💡 0 static events for '{source_name}'. Retrying with Playwright render..."
                )
                events = self.scrape_with_playwright(url, source_config)

            print(f"✅ Harvested {len(events)} events from {source_name}.")

            self._set_cache(source_id, events)
            return events

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ) as e:
            if retry_count < 1:
                print(
                    f"⏳ Timeout/Connection issue for '{source_name}'. Retrying in 2 seconds..."
                )
                time.sleep(2)
                return self.scrape_source(
                    source_config, retry_count=retry_count + 1
                )
            else:
                print(
                    f"❌ Connection failed for '{source_name}' after retry: {e}"
                )
                return []
        except Exception as e:
            print(f"❌ Error scraping {source_name}: {e}")
            return []

    def run_all(self):
        all_events = []
        enabled_sources = [s for s in self.sources if s.get("enabled", True)]

        print(
            f"\n🚀 Running Universal Scraper Engine for {len(enabled_sources)} enabled targets...\n"
        )

        for source in enabled_sources:
            if source.get("scraping_type") == "beautifulsoup":
                results = self.scrape_source(source)
                all_events.extend(results)

        return all_events


# ==========================================
# EXECUTION ENTRY POINT
# ==========================================
if __name__ == "__main__":
    sync_excel_to_yaml(yaml_path="sources.yaml")

    engine = EventScraperEngine(
        config_path="sources.yaml", cache_ttl_minutes=30
    )
    scraped_events = engine.run_all()

    output_filename = "scraped_events.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(scraped_events, f, indent=2)

    print(
        f"\n🎉 Process Complete! Saved {len(scraped_events)} total events to '{output_filename}'."
    )