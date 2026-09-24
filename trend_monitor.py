#!/usr/bin/env python3
"""
Soccer, ASMR & Phonk Shorts Radar Bot v3.4
- Strict Youth-Audience Focus: Real in-game soccer highlights & superstar skill plays.
- Viral ASMR & Oddly Satisfying video feeds.
- Expanded Video Host recognition (including streamff, dubz, streamin, v.redd.it).
- Anti-Screenshot Filter: Drops all static images, text discussions, and memes.
- 1-Click 1080p MP4 Downloader.
- 1-Click CapCut Template search links for velocity & ASMR beat syncs.
"""

import os
import sys
import re
import html
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

# Strict Safety Blocklist: Drops adult themes, violence, controversies, injury drama, and politics
SAFETY_BLOCKLIST = [
    "nsfw", "porn", "sex", "nude", "naked", "arrest", "murder", "shooting",
    "killed", "death", "dead", "fatal", "court", "trial", "lawsuit", "drug",
    "drugs", "cocaine", "overdose", "war", "ukraine", "russia", "israel", "gaza",
    "biden", "trump", "harris", "election", "senate", "congress", "democrat",
    "republican", "suicide", "crash", "dui", "assault", "scandal", "racist",
    "injury", "brawl", "fight", "referee controversy", "statement"
]

# Patterns that prove a post is an actual soccer goal/skill video, rather than discussion or news
SOCCER_HIGHLIGHT_PATTERNS = [
    r'\[\d+\]', r'\d+\s*-\s*\[?\d+\]?', r"\d+['’]",  # e.g. [1]-0 or 83'
    r'great goal', r'goal', r'skills?', r'assist', r'save', r'free kick', r'dribble',
    r'nutmeg', r'bicycle kick', r'volley', r'solo run', r'celebration', r'curler',
    r'ronaldo', r'messi', r'yamal', r'vinicius', r'vini', r'bellingham', r'haaland',
    r'mbappe', r'neymar', r'endrick', r'ishowspeed', r'speed', r'trick'
]

# Verified video hosts
VIDEO_HOSTS = [
    "v.redd.it", "streamin.me", "streamin.one", "streamin.to", "dubz.co", "dubz.link",
    "streamff.com", "streamja.com", "streamable.com", "streamye.com", "youtube.com",
    "youtu.be", "tiktok.com", "clips.twitch.tv", "redgifs.com"
]

IMAGE_INDICATORS = [
    "i.redd.it", "i.imgur.com", "imgur.com", "/gallery/",
    ".jpg", ".jpeg", ".png", ".webp"
]

DEFAULT_CONFIG = {
    "webhook_url": ACTIVE_WEBHOOK_URL,
    "poll_interval_seconds": 600,
    "state_file": "seen_items.json",
    "max_alerts_per_cycle": 10,
    "feeds": [
        {
            "name": "Soccer Highlights & Skills",
            "type": "soccer",
            "subreddits": ["soccer", "footballhighlights", "EASportsFC"],
            "sorts": ["rising", "hot"],
            "limit": 40
        },
        {
            "name": "Viral ASMR & Oddly Satisfying",
            "type": "asmr",
            "subreddits": ["oddlysatisfying", "Satisfyingasfuck", "soapcutting", "asmr"],
            "sorts": ["rising", "hot"],
            "limit": 30
        },
        {
            "name": "Brazilian & Drift Phonk Audio",
            "type": "phonk",
            "subreddits": ["phonk"],
            "sorts": ["hot"],
            "limit": 15
        }
    ]
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def deep_merge(base, override):
    """Recursively merges override dictionary into base dictionary."""
    for k, v in override.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            deep_merge(base[k], v)
        else:
            base[k] = v


def is_content_safe(text):
    """Returns False if text contains any adult, violent, or controversial words."""
    text_lower = text.lower()
    for word in SAFETY_BLOCKLIST:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
            return False
    return True


def is_soccer_highlight(title):
    """Ensures a soccer post is an actual goal or skill highlight rather than news or debate."""
    t_lower = title.lower()
    for pattern in SOCCER_HIGHLIGHT_PATTERNS:
        if re.search(pattern, t_lower):
            return True
    return False


def extract_media_details(permalink, raw_html):
    """Extracts direct media URL and verifies it is a playable video."""
    unescaped = html.unescape(raw_html) if raw_html else ""
    match = re.search(r'<a\s+href="([^"]+)">\[link\]</a>', unescaped)
    media_url = match.group(1) if match else permalink
    media_lower = media_url.lower()

    # Reject static images
    for img_ind in IMAGE_INDICATORS:
        if img_ind in media_lower:
            return False, media_url

    # Check for known video host
    for vh in VIDEO_HOSTS:
        if vh in media_lower:
            return True, media_url

    # Check for native reddit video embed
    if "v.redd.it" in unescaped:
        return True, media_url

    return False, media_url


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
            "username": "Shorts Clip & Trend Radar",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/861/861512.png",
            "embeds": [embed]
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "TrendClipRadar/3.4"
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
    """Scrapes curated Soccer, ASMR, and Phonk video feeds with youth-oriented filtering."""
    def __init__(self, config, storage, webhook):
        self.config = config
        self.storage = storage
        self.webhook = webhook

    def run_cycle(self):
        logger.info("Starting curated video clip scan cycle...")
        dispatched_count = 0
        max_alerts = self.config.get("max_alerts_per_cycle", 10)

        for feed_group in self.config.get("feeds", []):
            if dispatched_count >= max_alerts:
                break

            group_name = feed_group.get("name", "Clips")
            category_type = feed_group.get("type", "soccer")
            subreddits = feed_group.get("subreddits", ["soccer"])
            sorts = feed_group.get("sorts", ["rising", "hot"])
            limit = feed_group.get("limit", 30)

            combined_subs = "+".join(subreddits)

            for sort_type in sorts:
                if dispatched_count >= max_alerts:
                    break

                rss_url = f"https://www.reddit.com/r/{combined_subs}/{sort_type}/.rss?limit={limit}"
                logger.info(f"Checking [{group_name}] r/{combined_subs} ({sort_type})...")

                req = urllib.request.Request(rss_url, headers=BROWSER_HEADERS)

                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        xml_data = resp.read()
                    root = ET.fromstring(xml_data)

                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    entries = root.findall(".//atom:entry", ns)

                    for entry in entries:
                        if dispatched_count >= max_alerts:
                            break

                        id_elem = entry.find("atom:id", ns)
                        title_elem = entry.find("atom:title", ns)
                        link_elem = entry.find("atom:link", ns)
                        cat_elem = entry.find("atom:category", ns)
                        content_elem = entry.find("atom:content", ns)

                        raw_id = id_elem.text if id_elem is not None and id_elem.text else str(time.time())
                        post_id = raw_id.split("/")[-1]
                        title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Clip"
                        permalink = link_elem.attrib.get("href", "") if link_elem is not None else ""
                        sub_name = cat_elem.attrib.get("term", "clips") if cat_elem is not None else "clips"
                        raw_content = content_elem.text if content_elem is not None else ""

                        # 1. Safety Check: Filter out adult language, crime, politics, and controversies
                        if not is_content_safe(title):
                            continue

                        # 2. Soccer Relevance: If soccer group, must be an actual goal or skill play
                        if category_type == "soccer" and not is_soccer_highlight(title):
                            continue

                        # 3. Video Verification: Must be a confirmed video (reject images/infographics)
                        is_video, direct_media_url = extract_media_details(permalink, raw_content)
                        if not is_video:
                            continue

                        item_id = f"reddit_{post_id}"
                        if not self.storage.is_seen(item_id):
                            encoded_title = urllib.parse.quote(title)
                            encoded_permalink = urllib.parse.quote(permalink)

                            # RapidSave 1-Click 1080p Downloader
                            download_url = f"https://rapidsave.com/info?url={encoded_permalink}"

                            # Category Customization
                            if category_type == "asmr":
                                icon = "✨"
                                category_label = "Satisfying / ASMR Video"
                                capcut_query = f"{encoded_title}+satisfying+asmr+capcut+template"
                                audio_query = f"satisfying+asmr+relaxing+trending+audio"
                                embed_color = 0x9B59B6  # Purple
                            elif category_type == "phonk":
                                icon = "🎵"
                                category_label = "Brazilian / Drift Phonk Audio"
                                capcut_query = f"brazilian+phonk+velocity+edit+capcut+template"
                                audio_query = f"brazilian+phonk+new+age+edit+audio"
                                embed_color = 0x3498DB  # Blue
                            else:
                                icon = "⚽"
                                category_label = "Soccer Goal / Skill Move"
                                capcut_query = f"{encoded_title}+velocity+edit+capcut+template"
                                audio_query = f"brazilian+phonk+soccer+edit+audio"
                                embed_color = 0xE67E22  # Orange

                            capcut_search_url = f"https://www.tiktok.com/search?q={capcut_query}"
                            audio_search_url = f"https://www.youtube.com/results?search_query={audio_query}"

                            fields = [
                                {"name": "Category", "value": f"{category_label}", "inline": True},
                                {"name": "Subreddit", "value": f"r/{sub_name}", "inline": True},
                                {"name": "Velocity", "value": f"⚡ {sort_type.upper()}", "inline": True},
                                {
                                    "name": "⬇️ Direct Video & Downloader",
                                    "value": f"[▶️ Watch Direct Video]({direct_media_url})\n[📥 1-Click 1080p MP4 Download]({download_url})",
                                    "inline": False
                                },
                                {
                                    "name": "✂️ CapCut Templates & Audio",
                                    "value": f"[Find CapCut Velocity Template]({capcut_search_url}) • [Trending Sounds]({audio_search_url})",
                                    "inline": False
                                }
                            ]

                            success = self.webhook.send_embed(
                                title=f"{icon} {title}",
                                url=direct_media_url,
                                description=f"Fresh video clip trending in r/{sub_name} ({sort_type}).",
                                fields=fields,
                                color=embed_color,
                                footer=f"Radar • {group_name}"
                            )
                            if success:
                                self.storage.mark_seen(item_id)
                                dispatched_count += 1
                                time.sleep(1)

                    time.sleep(2)

                except urllib.error.HTTPError as e:
                    logger.error(f"HTTP error on r/{combined_subs} ({sort_type}): {e.code} {e.reason}")
                except Exception as e:
                    logger.error(f"Error on r/{combined_subs} ({sort_type}): {e}")

        self.storage.save()
        logger.info(f"Scan cycle completed. Dispatched {dispatched_count} fresh video clips.")


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
