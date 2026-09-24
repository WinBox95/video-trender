#!/usr/bin/env python3
"""
Soccer & Phonk Shorts Radar Bot v3.2
- Embedded Discord Webhook URL.
- Kid-Safe Content Filtering (No NSFW, explicit language, crime, or politics).
- Niche Focus: Soccer / Football goals, skill clips, EA FC moments, and Brazilian Phonk audio.
- 1-Click Video Downloader for raw 1080p clips.
- 1-Click CapCut Template search links for velocity and beat-synced edits.
"""

import os
import sys
import re
import json
import time
import copy
import hashlib
import logging
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TrendRadar")

# Your Pre-configured Discord Webhook
ACTIVE_WEBHOOK_URL = "https://discord.com/api/webhooks/1552645608676786237/_uaGO9XTJld8xOYtICDBm1MOuiaXD-Xh8Xwn8bwXdpDqP2_4eSqWJNQePImgNEk3NIQB"

# Safety Blocklist: Automatically drops any inappropriate, adult, or political themes
SAFETY_BLOCKLIST = [
    "nsfw", "porn", "sex", "nude", "naked", "arrest", "murder", "shooting",
    "killed", "death", "dead", "fatal", "court", "trial", "lawsuit", "drug",
    "drugs", "cocaine", "overdose", "war", "ukraine", "russia", "israel", "gaza",
    "biden", "trump", "harris", "election", "senate", "congress", "democrat",
    "republican", "suicide", "crash", "dui", "assault", "scandal", "racist"
]

# Niche Whitelist for Google Trends: Only allow sports, soccer, gaming, and phonk topics
NICHE_KEYWORDS = [
    "goal", "assist", "skills", "save", "penalty", "red card", "soccer", "football",
    "champions league", "premier league", "la liga", "serie a", "mls", "fifa", "ea fc",
    "fc 25", "messi", "ronaldo", "mbappe", "yamal", "vinicius", "vini", "bellingham",
    "haaland", "neymar", "phonk", "brazil", "brazilian", "montage", "edit", "clip",
    "fortnite", "gaming", "streamer", "highlight", "derby", "cup", "real madrid",
    "barcelona", "arsenal", "manchester", "liverpool", "psg", "inter miami", "world cup"
]

DEFAULT_CONFIG = {
    "webhook_url": ACTIVE_WEBHOOK_URL,
    "poll_interval_seconds": 600,  # 10 minutes
    "state_file": "seen_items.json",
    "google_trends": {
        "enabled": True,
        "geo": "US",
        "feed_url": "https://trends.google.com/trending/rss?geo=US",
        "filter_niche_only": True
    },
    "reddit_monitor": {
        "enabled": True,
        "subreddits": [
            "soccer",
            "football",
            "EASportsFC",
            "phonk",
            "soccercirclejerk"
        ],
        "feeds": ["rising", "hot"],
        "limit_per_feed": 25
    }
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def deep_merge(base, override):
    """Recursively merges override dictionary into base dictionary without wiping sibling keys."""
    for k, v in override.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            deep_merge(base[k], v)
        else:
            base[k] = v


def is_content_safe(text):
    """Returns False if text contains any adult, violent, or political words."""
    text_lower = text.lower()
    for word in SAFETY_BLOCKLIST:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
            return False
    return True


def matches_channel_niche(text):
    """Returns True if the trend or post matches soccer, sports, phonk, or gaming."""
    text_lower = text.lower()
    for kw in NICHE_KEYWORDS:
        if kw in text_lower:
            return True
    return False


class Storage:
    """Handles persistence of seen item IDs to prevent duplicate alerts."""
    def __init__(self, filename="seen_items.json", retention_days=3):
        if not os.path.isabs(filename):
            self.filename = os.path.join(SCRIPT_DIR, filename)
        else:
            self.filename = filename

        self.retention_seconds = retention_days * 86400
        self.seen_data = self._load()

    def _load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info(f"Loaded {len(data)} previously seen items from {self.filename}")
                    return data
            except Exception as e:
                logger.warning(f"Could not load state file, starting fresh: {e}")
        return {}

    def is_seen(self, item_id):
        return item_id in self.seen_data

    def mark_seen(self, item_id):
        self.seen_data[item_id] = time.time()

    def save(self):
        now = time.time()
        self.seen_data = {
            k: v for k, v in self.seen_data.items()
            if (now - v) < self.retention_seconds
        }
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.seen_data, f, indent=2)
            logger.info(f"Saved state ({len(self.seen_data)} tracked items) to {self.filename}")
        except Exception as e:
            logger.error(f"Failed to save state file: {e}")


class WebhookClient:
    """Dispatches formatted embeds to Discord."""
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def send_embed(self, title, url, description, fields=None, color=0x2ECC71, footer="Shorts Edit Radar"):
        if not self.webhook_url:
            logger.info(f"[DRY RUN - No Webhook URL] Discovered: {title} ({url})")
            return True

        embed = {
            "title": title[:250],
            "url": url,
            "description": (description[:400] + "...") if len(description) > 400 else description,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": footer}
        }
        if fields:
            embed["fields"] = fields

        payload = {
            "username": "Soccer & Phonk Edit Radar",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/861/861512.png",
            "embeds": [embed]
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "TrendClipRadar/3.2"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 204):
                    logger.info(f"Dispatched alert: {title}")
                    return True
                else:
                    logger.error(f"Discord returned status {resp.status}")
                    return False
        except urllib.error.HTTPError as e:
            if e.code == 429:
                logger.warning("Discord rate limit hit, sleeping...")
                time.sleep(2)
            else:
                logger.error(f"HTTP error posting to Discord: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to post to webhook: {e}")
            return False


class TrendScraper:
    """Scrapes soccer, phonk, and gaming trends with safety filtering and edit tooling."""
    def __init__(self, config, storage, webhook):
        self.config = config
        self.storage = storage
        self.webhook = webhook

    def fetch_google_trends(self):
        gt_cfg = self.config.get("google_trends", {})
        if not gt_cfg.get("enabled", True):
            return

        feed_url = gt_cfg.get("feed_url", "https://trends.google.com/trending/rss?geo=US")
        filter_niche = gt_cfg.get("filter_niche_only", True)
        logger.info(f"Fetching Google Trends from {feed_url}")
        req = urllib.request.Request(feed_url, headers=BROWSER_HEADERS)

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)

            ns = {"ht": "https://trends.google.com/trending/rss"}

            for item in root.findall(".//item"):
                title_elem = item.find("title")
                traffic_elem = item.find("ht:approx_traffic", ns)
                desc_elem = item.find("description")

                title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Unknown Trend"
                traffic = traffic_elem.text.strip() if traffic_elem is not None and traffic_elem.text else "High Search Spike"
                description = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""

                if not is_content_safe(title) or not is_content_safe(description):
                    continue

                if filter_niche and not matches_channel_niche(title + " " + description):
                    continue

                news_item = item.find("ht:news_item", ns)
                article_url = None
                article_source = "Sports / News"
                if news_item is not None:
                    url_elem = news_item.find("ht:news_item_url", ns)
                    src_elem = news_item.find("ht:news_item_source", ns)
                    if url_elem is not None and url_elem.text:
                        article_url = url_elem.text.strip()
                    if src_elem is not None and src_elem.text:
                        article_source = src_elem.text.strip()

                encoded_title = urllib.parse.quote(title)
                primary_url = article_url if article_url else f"https://www.google.com/search?q={encoded_title}"

                capcut_search_url = f"https://www.tiktok.com/search?q={encoded_title}+capcut+template"
                phonk_audio_url = f"https://www.youtube.com/results?search_query=brazilian+phonk+{encoded_title}+edit+audio"
                yt_shorts_url = f"https://www.youtube.com/results?search_query={encoded_title}+shorts"

                item_id = "gtrend_" + hashlib.md5(title.encode("utf-8")).hexdigest()

                if not self.storage.is_seen(item_id):
                    fields = [
                        {"name": "Search Volume", "value": f"📈 {traffic}", "inline": True},
                        {"name": "Source", "value": f"📰 {article_source}", "inline": True},
                        {
                            "name": "✂️ CapCut Templates & Audio",
                            "value": f"[CapCut Template Search]({capcut_search_url}) • [Brazilian Phonk Audio]({phonk_audio_url})",
                            "inline": False
                        },
                        {
                            "name": "🎬 Existing YouTube Shorts",
                            "value": f"[View Existing Edits & Clips]({yt_shorts_url})",
                            "inline": False
                        }
                    ]
                    success = self.webhook.send_embed(
                        title=f"⚽ Trending Topic: {title}",
                        url=primary_url,
                        description=f"Trending now in sports/culture.\n\n{description}",
                        fields=fields,
                        color=0x2ECC71,
                        footer="Google Trends Real-time"
                    )
                    if success:
                        self.storage.mark_seen(item_id)
                        time.sleep(1)

        except Exception as e:
            logger.error(f"Error fetching Google Trends: {e}")

    def fetch_reddit_clips(self):
        reddit_cfg = self.config.get("reddit_monitor", {})
        if not reddit_cfg.get("enabled", True):
            return

        raw_sub_list = reddit_cfg.get("subreddits", ["soccer", "football", "phonk"])
        sub_list = [
            s["name"] if isinstance(s, dict) else str(s)
            for s in raw_sub_list
            if (isinstance(s, dict) and "name" in s) or isinstance(s, str)
        ]

        feeds = reddit_cfg.get("feeds", ["rising", "hot"])
        limit = reddit_cfg.get("limit_per_feed", 25)

        combined_subs = "+".join(sub_list)

        for feed_type in feeds:
            rss_url = f"https://www.reddit.com/r/{combined_subs}/{feed_type}/.rss?limit={limit}"
            logger.info(f"Fetching combined Reddit feed: r/{combined_subs} [{feed_type}]")

            req = urllib.request.Request(rss_url, headers=BROWSER_HEADERS)

            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    xml_data = resp.read()
                root = ET.fromstring(xml_data)

                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entries = root.findall(".//atom:entry", ns)
                logger.info(f"Discovered {len(entries)} candidate posts in [{feed_type}] feed.")

                for entry in entries:
                    id_elem = entry.find("atom:id", ns)
                    title_elem = entry.find("atom:title", ns)
                    link_elem = entry.find("atom:link", ns)
                    cat_elem = entry.find("atom:category", ns)

                    raw_id = id_elem.text if id_elem is not None and id_elem.text else str(time.time())
                    post_id = raw_id.split("/")[-1]
                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Soccer / Phonk Clip"
                    permalink = link_elem.attrib.get("href", "") if link_elem is not None else ""
                    sub_name = cat_elem.attrib.get("term", "soccer") if cat_elem is not None else "soccer"

                    if not is_content_safe(title):
                        continue

                    item_id = f"reddit_{post_id}"
                    if not self.storage.is_seen(item_id):
                        encoded_title = urllib.parse.quote(title)
                        encoded_permalink = urllib.parse.quote(permalink)

                        # 1-Click Video Downloader link
                        download_url = f"https://rapidsave.com/info?url={encoded_permalink}"
                        
                        # Direct CapCut Template search link on TikTok
                        capcut_search_url = f"https://www.tiktok.com/search?q={encoded_title}+capcut+template"
                        
                        # Trending Brazilian Phonk beat search link
                        phonk_audio_url = f"https://www.youtube.com/results?search_query=brazilian+phonk+{encoded_title}+edit+audio"

                        fields = [
                            {"name": "Subreddit", "value": f"r/{sub_name}", "inline": True},
                            {"name": "Feed Type", "value": f"⚡ {feed_type.upper()}", "inline": True},
                            {
                                "name": "⬇️ Download Clip for Editing",
                                "value": f"[1-Click 1080p MP4 Download]({download_url}) • [Open Thread]({permalink})",
                                "inline": False
                            },
                            {
                                "name": "✂️ CapCut Templates & Audio",
                                "value": f"[Find CapCut Velocity Template]({capcut_search_url}) • [Find Brazilian Phonk Beats]({phonk_audio_url})",
                                "inline": False
                            }
                        ]

                        icon = "🎵" if sub_name.lower() == "phonk" else ("🎮" if "fc" in sub_name.lower() else "⚽")

                        success = self.webhook.send_embed(
                            title=f"{icon} Clip: {title}",
                            url=permalink,
                            description=f"Fresh highlight from r/{sub_name} trending in {feed_type}.",
                            fields=fields,
                            color=0x3498DB if sub_name.lower() == "phonk" else 0xE67E22,
                            footer=f"Reddit r/{sub_name} Radar"
                        )
                        if success:
                            self.storage.mark_seen(item_id)
                            time.sleep(1)

                time.sleep(2)

            except urllib.error.HTTPError as e:
                logger.error(f"HTTP error fetching Reddit RSS for {feed_type}: {e.code} {e.reason}")
            except Exception as e:
                logger.error(f"Error fetching Reddit RSS for {feed_type}: {e}")

    def run_cycle(self):
        logger.info("Starting trend & clip scan cycle...")
        self.fetch_google_trends()
        self.fetch_reddit_clips()
        self.storage.save()
        logger.info("Scan cycle completed.")


def main():
    config = copy.deepcopy(DEFAULT_CONFIG)
    config_file = os.path.join(SCRIPT_DIR, "config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
                deep_merge(config, user_cfg)
        except Exception as e:
            logger.warning(f"Could not parse {config_file}: {e}")

    # Ensure webhook is always active even if config.json has placeholder or empty string
    wh = config.get("webhook_url", "")
    if not wh or "YOUR_DISCORD_WEBHOOK_URL" in wh:
        config["webhook_url"] = ACTIVE_WEBHOOK_URL

    storage = Storage(config.get("state_file", "seen_items.json"))
    webhook = WebhookClient(config.get("webhook_url", ACTIVE_WEBHOOK_URL))
    scraper = TrendScraper(config, storage, webhook)

    run_once = "--once" in sys.argv or os.getenv("RUN_ONCE", "false").lower() == "true"

    if run_once:
        scraper.run_cycle()
    else:
        interval = config.get("poll_interval_seconds", 600)
        logger.info(f"Starting continuous radar monitoring every {interval} seconds.")
        while True:
            try:
                scraper.run_cycle()
            except KeyboardInterrupt:
                logger.info("Stopping monitor...")
                break
            except Exception as e:
                logger.error(f"Unexpected error in monitor loop: {e}")
            time.sleep(interval)


if __name__ == "__main__":
    main()
