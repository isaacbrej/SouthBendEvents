import json
import os
import re
from datetime import datetime, timedelta
import dateutil.parser

# Reference timestamp for fuzzy parsing calculations
NOW = datetime(2026, 10, 14, 17, 0, 0)


class EventNormalizerPipeline:

    def __init__(
        self,
        raw_input_file="scraped_events.json",
        output_file="normalized_events.json",
    ):
        self.raw_input_file = raw_input_file
        self.output_file = output_file

    def parse_date(self, date_str):
        """Converts fuzzy/raw date strings into standardized ISO-8601 timestamps."""
        if not date_str or date_str in ["Upcoming", "None", ""]:
            return (NOW + timedelta(days=1)).strftime("%Y-%m-%dT19:00:00")

        clean_str = date_str.strip()

        try:
            dt = dateutil.parser.isoparse(clean_str)
            return dt.isoformat()
        except Exception:
            pass

        lower_str = clean_str.lower()
        if "today" in lower_str:
            return NOW.strftime("%Y-%m-%dT19:00:00")
        elif "tomorrow" in lower_str:
            return (NOW + timedelta(days=1)).strftime("%Y-%m-%dT19:00:00")

        try:
            dt = dateutil.parser.parse(clean_str, fuzzy=True, default=NOW)
            if dt.year < 2025 or dt.year > 2028:
                dt = dt.replace(year=2026)
            return dt.isoformat()
        except Exception:
            return (NOW + timedelta(days=1)).strftime("%Y-%m-%dT19:00:00")

    def categorize_event(self, title, venue, source_category):
        """Categorizes events to ensure social feeds are strictly fun & leisure activities."""
        title_lower = title.lower()
        text_full = f"{title} {venue}".lower()

        # 1. Noise Filter: Non-events, generic navigation, kids/afterschool programs, internal administrative noise
        noise_keywords = [
            "morning storytime",
            "toddler story",
            "infant laptime",
            "after school",
            "afterschool",
            "executive committee meeting",
            "internal staff meeting",
            "closed session",
            "contact us",
            "skip to content",
            "skip navigation",
            "view details",
            "click here",
            "privacy policy",
            "terms of service",
        ]
        if any(nk in text_full for nk in noise_keywords):
            return "Filtered Out"

        # 2. Civic, Government, Municipal & Professional/Workplace Events
        civic_professional_keywords = [
            "board meeting",
            "board of",
            "city council",
            "town hall",
            "committee meeting",
            "public hearing",
            "zoning",
            "plan commission",
            "plat committee",
            "merit board",
            "merit commission",
            "board of health",
            "animal care",
            "election board",
            "redevelopment",
            "public works",
            "neighborhood association",
            "historic preservation",
            "special events committee",
            "public safety",
            "human rights commission",
            "training meeting",
            "training session",
            "summit",
            "networking",
            "professional development",
            "workshop",
            "seminar",
            "symposium",
            "conference",
            "forum",
            "business after hours",
            "chamber of commerce",
        ]
        if any(kw in text_full for kw in civic_professional_keywords):
            return "Civic & Community Affairs"

        if re.search(r"\b(board|council|commission|meeting|summit|workshop|training)\b", title_lower):
            return "Civic & Community Affairs"

        # 3. Live Music & Concerts
        music_keywords = [
            "music",
            "concert",
            "band",
            "symphony",
            "orchestra",
            "singer",
            "dj",
            "jazz",
            "acoustic",
            "choir",
            "jam session",
            "live set",
        ]
        if any(re.search(r"\b" + re.escape(kw) + r"\b", text_full) for kw in music_keywords):
            return "Live Music"

        # 4. Shows, Theater & Performing Arts
        shows_keywords = [
            "theater",
            "theatre",
            "show",
            "comedy",
            "play",
            "broadway",
            "musical",
            "performance",
            "film",
            "movie",
            "dance",
            "ballet",
            "improv",
            "exhibit",
            "gallery",
        ]
        if any(re.search(r"\b" + re.escape(kw) + r"\b", text_full) for kw in shows_keywords):
            return "Shows & Arts"

        # 5. Sports & Recreation
        sports_keywords = [
            "sport",
            "game",
            "baseball",
            "cubs",
            "athletics",
            "bowling",
            "race",
            "5k",
            "marathon",
            "run",
            "fitness",
            "yoga",
            "tournament",
            "volleyball",
            "hike",
            "kayak",
        ]
        if any(re.search(r"\b" + re.escape(kw) + r"\b", text_full) for kw in sports_keywords):
            return "Sports & Recreation"

        # 6. Nightlife, Bar & Pub Socials
        nightlife_keywords = [
            "pub",
            "bar",
            "brewery",
            "taproom",
            "trivia",
            "beer",
            "wine",
            "distillery",
            "cocktail",
            "happy hour",
            "nightlife",
            "karaoke",
            "pub crawl",
        ]
        if any(re.search(r"\b" + re.escape(kw) + r"\b", text_full) for kw in nightlife_keywords):
            return "Nightlife & Pubs"

        # 7. Festivals & Fairs
        festival_keywords = [
            "festival",
            "fair",
            "parade",
            "market",
            "expo",
            "block party",
            "celebration",
            "food truck",
        ]
        if any(re.search(r"\b" + re.escape(kw) + r"\b", text_full) for kw in festival_keywords):
            return "Festivals & Community"

        # Fallback: Default to Community & Social for fun general socials
        return "Community & Social"

    def generate_ics_content(self, event):
        """Generates iCalendar .ics format for 1-click Google Calendar export."""
        title = event["title"]
        venue = event["venue"]
        link = event["link"]
        iso_date = event["iso_start_time"]

        try:
            dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
            dt_start = dt.strftime("%Y%m%dT%H%M%SZ")
            dt_end = (dt + timedelta(hours=2)).strftime("%Y%m%dT%H%M%SZ")
        except Exception:
            dt_start = "20261015T190000Z"
            dt_end = "20261015T210000Z"

        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//South Bend Event Aggregator//EN",
            "BEGIN:VEVENT",
            f"SUMMARY:{title}",
            f"LOCATION:{venue}",
            f"DESCRIPTION:Source Link: {link}",
            f"DTSTART:{dt_start}",
            f"DTEND:{dt_end}",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        return "\n".join(ics_lines)

    def process_pipeline(self):
        if not os.path.exists(self.raw_input_file):
            print(f"❌ Raw input file '{self.raw_input_file}' not found.")
            return []

        with open(self.raw_input_file, "r", encoding="utf-8") as f:
            raw_events = json.load(f)

        processed_events = []
        seen_keys = set()
        noise_filtered_count = 0
        dedup_filtered_count = 0

        for event in raw_events:
            title = event.get("title", "").strip()
            venue = event.get("venue", "").strip()
            link = event.get("link", "").strip()
            category_raw = event.get("category", "General Social")
            date_raw = event.get("date_raw", "Upcoming")

            category = self.categorize_event(title, venue, category_raw)
            if category == "Filtered Out":
                noise_filtered_count += 1
                continue

            iso_date = self.parse_date(date_raw)
            date_part = iso_date[:10]

            clean_title = re.sub(r"[^a-z0-9]", "", title.lower())
            dedup_key = f"{clean_title}_{venue.lower()}_{date_part}"
            if dedup_key in seen_keys:
                dedup_filtered_count += 1
                continue
            seen_keys.add(dedup_key)

            new_id = f"sbe_{len(processed_events) + 1:04d}"

            normalized_item = {
                "id": new_id,
                "title": title,
                "venue": venue,
                "city": event.get("city", "South Bend"),
                "category": category,
                "date_raw": date_raw,
                "iso_start_time": iso_date,
                "link": link,
                "scraped_at": event.get("scraped_at", NOW.isoformat()),
                "extraction_tier": event.get("extraction_tier", "Tier 2"),
            }
            normalized_item["ics_export"] = self.generate_ics_content(
                normalized_item
            )
            processed_events.append(normalized_item)

        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(processed_events, f, indent=2)

        print(f"🎉 Pipeline Complete!")
        print(f"  • Retained events: {len(processed_events)}")
        print(f"  • Filtered noise listings: {noise_filtered_count}")
        print(f"  • Removed duplicate posts: {dedup_filtered_count}")
        print(f"💾 Saved database to '{self.output_file}'")
        return processed_events


if __name__ == "__main__":
    normalizer = EventNormalizerPipeline(
        raw_input_file="scraped_events.json",
        output_file="normalized_events.json",
    )
    normalizer.process_pipeline()