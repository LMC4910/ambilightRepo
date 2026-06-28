"""Generate ambilight/notifications/brand_colors.py from the simple-icons dataset.

Sources the official brand hex for a curated list of the ~500 apps/services that
most commonly produce desktop / forwarded-phone notifications. simple-icons is the
authoritative colour source (CC0, official brand-guideline hexes). A handful of top
apps were removed from simple-icons on trademark requests (all Microsoft products,
LinkedIn, Slack, Amazon); those are supplemented with web-verified official hexes.

Usage:
    curl -sL https://cdn.jsdelivr.net/npm/simple-icons@latest/data/simple-icons.json -o si.json
    python scripts/gen_brand_colors.py si.json ambilight/notifications/brand_colors.py
"""
import json
import re
import sys

SI = json.load(open(sys.argv[1], encoding="utf-8"))


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# Build lookup: normalized slug / title / aliases -> hex
INDEX = {}
def _add(k, h):
    k = norm(k)
    if k and k not in INDEX:
        INDEX[k] = h

for e in SI:
    _add(e["slug"], e["hex"])
    _add(e["title"], e["hex"])
    al = e.get("aliases", {})
    for a in al.get("aka", []) or []:
        _add(a, e["hex"])
    loc = al.get("loc", {})
    if isinstance(loc, dict):
        for a in loc.values():
            _add(a, e["hex"])
    for dup in al.get("dup", []) or []:
        if isinstance(dup, dict):
            _add(dup.get("title", ""), dup.get("hex", e["hex"]))


# Web-verified official hexes for brands NOT in simple-icons (trademark removals).
# Sources: usbrandcolors.com, brandpalettes.com, official brand guidelines.
SUPPLEMENTS = {
    "Microsoft": "00A4EF",
    "Microsoft Teams": "464EB8",
    "Microsoft Outlook": "0078D4",
    "Outlook": "0078D4",
    "Microsoft Office": "D83B01",
    "Microsoft Word": "2B579A",
    "Microsoft Excel": "217346",
    "Microsoft PowerPoint": "C43E1C",
    "Microsoft OneNote": "7719AA",
    "OneDrive": "0364B8",
    "Microsoft OneDrive": "0364B8",
    "Skype": "00AFF0",
    "Xbox": "107C10",
    "Minecraft": "6CA046",
    "Windows": "0078D4",
    "Microsoft Store": "0078D4",
    "Microsoft Edge": "0C59A4",
    "LinkedIn": "0A66C2",
    "Slack": "4A154B",
    "Amazon": "FF9900",
    "Amazon Prime": "00A8E1",
    "Prime Video": "00A8E1",
    "Amazon Alexa": "00CAFF",
    "Audible": "F8991C",
    "Kindle": "FF9900",
    "Goodreads": "553B08",
    "Twitch Prime": "9146FF",
}

# Iconic, well-documented official brand colours for popular apps that are NOT in
# current simple-icons (removed on trademark requests over the years). Values are
# the primary logo colour from each brand's guidelines / press kit.
EXTRA_SUPPLEMENTS = {
    "Salesforce": "00A1E0", "Hulu": "1CE783", "Walmart": "0071CE", "Costco": "005DAA",
    "Best Buy": "0046BE", "Wayfair": "7B189F", "Flipkart": "2874F0", "Mercado Libre": "FFE600",
    "Alibaba": "FF6A00", "Temu": "FB7701", "SHEIN": "000000", "Sephora": "000000",
    "Kayak": "FF690F", "Skyscanner": "0770E3", "Lime": "00DD00", "Bolt": "34D186",
    "Nintendo": "E60012", "Nintendo Switch": "E60012", "Blizzard": "00AEFF",
    "Garena": "EE3424", "Among Us": "C51111", "Apex Legends": "CD3333", "Bethesda": "000000",
    "Kraken": "5741D9", "MetaMask": "F6851B", "Trust Wallet": "3375BB", "Ledger": "000000",
    "Plaid": "000000", "Bybit": "F7A600", "Mint": "3EB489", "Chime": "1EC677",
    "Skrill": "862165", "Heroku": "430098", "Twilio": "F22F46", "SendGrid": "1A82E2",
    "Segment": "52BD94", "CodePen": "000000", "Pipedrive": "017737", "Salesforce ": "00A1E0",
    "Reuters": "FF8000", "The Economist": "E3120B", "The Verge": "5200FF", "USA Today": "009BFF",
    "Politico": "BD1B21", "Al Jazeera": "FA9000", "BBC": "000000", "Bloomberg": "000000",
    "Forbes": "000000", "Wired": "000000", "The New York Times": "000000", "Vice": "000000",
    "The Wall Street Journal": "000000", "NPR": "000000", "Bumble": "FFC629", "Hinge": "000000",
    "Calm": "3C6FFF", "WHOOP": "000000", "Oura": "000000", "Zwift": "FC6719",
    "MyFitnessPal": "0066EE", "Samsung Health": "1428A0", "Eventbrite": "F05537",
    "Canva": "00C4CC", "Midjourney": "000000", "OpenTable": "DA3743", "Chipotle": "A81612",
    "Pocket": "EF4056", "Yahoo!": "6001D2", "Pluto TV": "FFF200", "Vudu": "3399FF",
    "Lazada": "0F146D", "OpenAI": "000000", "ChatGPT": "000000", "Twitch": "9146FF",
    "Disney+": "113CCF", "AWS": "FF9900", "Amazon Web Services": "FF9900",
    "Microsoft Azure": "0078D4", "Visual Studio Code": "007ACC", "Visual Studio": "5C2D91",
    "Microsoft Authenticator": "0078D4", "Microsoft Bing": "008373", "Microsoft To Do": "2564CF",
    "Hacker News": "FF6600", "Peacock": "000000",
}
SUPPLEMENTS.update(EXTRA_SUPPLEMENTS)

# Curated, popularity-ordered list of notification-relevant apps/brands.
# Each item: "Name"  OR  ("Name", "simple-icons-slug")  OR  ("Name", "slug", "alias1", "alias2"...)
# slug=None/omitted -> resolve by normalized name. Aliases are extra match keys
# (e.g. the un-prefixed display name an app may report).
CURATED = [
    # --- Messaging / chat ---
    "WhatsApp", ("Messenger", "messenger", "Facebook Messenger"), "Telegram", "Signal",
    "Discord", ("Slack", None), "Microsoft Teams", "Skype", "WeChat", "Line", "Viber",
    "KakaoTalk", "Snapchat", ("Google Chat", "googlechat"), ("Google Messages", "googlemessages", "Messages"),
    "Zoom", ("Webex", "webex", "Cisco Webex"), "Telegram", "Threema", "Session", "Element",
    "Matrix", "Rocket.dot Chat", ("Rocket.Chat", "rocketdotchat"), "Mattermost", "GroupMe",
    "Tox", "Wire", "Jitsi", "BlueJeans", "GoToMeeting", "Whereby", "Discord",
    ("WhatsApp Business", "whatsapp"), "Beeper", "Telegram",
    # --- Social ---
    ("X", "x", "Twitter"), "Instagram", "Facebook", "TikTok", "Reddit", "LinkedIn",
    "Pinterest", "Tumblr", "Mastodon", "Bluesky", "Threads", ("VK", "vk"), "Sina Weibo",
    "Quora", "Nextdoor", "Clubhouse", "BeReal", "Flickr", "Vimeo", "Dribbble", "Behance",
    "Medium", "Substack", "Patreon", "OnlyFans", "Bilibili", "Douban", "Odnoklassniki",
    "Xing", "Meetup", "Strava", "Letterboxd", "Goodreads", "Untappd", "Yelp", "Foursquare",
    "Trustpilot", "Producthunt", "Hashnode", "DevTo", ("Dev.to", "devdotto"), "Polywork",
    # --- Email ---
    "Gmail", "Microsoft Outlook", ("Yahoo!", "yahoo", "Yahoo Mail"), "Proton Mail",
    ("Proton Mail", "protonmail"), "Thunderbird", "Spark", ("Zoho", "zoho", "Zoho Mail"),
    "Fastmail", "HEY", ("Apple Mail", None, "Mail"), "Mailchimp", "Mailgun", "Postmark",
    "SendGrid", "Front", "Tutanota", "GMX", "ProtonMail",
    # --- Productivity / notes / PM ---
    "Notion", "Trello", "Asana", "Jira", "Confluence", "ClickUp", ("Monday", "mondaydotcom"),
    ("monday.com", "mondaydotcom"), "Linear", "Todoist", ("Microsoft Word", None),
    ("Microsoft Excel", None), ("Microsoft PowerPoint", None), ("Microsoft OneNote", None, "OneNote"),
    "Evernote", "Obsidian", "Basecamp", "Airtable", "Coda", "Miro", "Figma", "FigJam",
    "Canva", "Notion", "Roam Research", "Logseq", "Bear", "Things", "TickTick",
    "Microsoft To Do", "Google Keep", "Standard Notes", "Joplin", "Dropbox Paper",
    "Smartsheet", "Wrike", "Teamwork", "Podio", "Shortcut", "Height", "Pivotal Tracker",
    "Toggl", "Clockify", "RescueTime", "Notability", "GoodNotes", "Zapier", "IFTTT",
    "Make", "n8n", "Airfocus", "ProductBoard", "Aha", "Fellow", "Loom", "Calendly",
    ("Google Calendar", "googlecalendar"), "Fantastical", "Cron", "Doodle",
    # --- Dev / engineering / ops ---
    "GitHub", "GitLab", "Bitbucket", "Jenkins", "CircleCI", "Travis CI", "Sentry",
    "Datadog", "PagerDuty", "Opsgenie", "Grafana", "Prometheus", "New Relic", "Splunk",
    "Docker", ("npm", "npm"), "Vercel", "Netlify", "Cloudflare", "Heroku", "DigitalOcean",
    "Stack Overflow", "Stack Exchange", "CodePen", "Replit", "Glitch", "Render", "Railway",
    "Fly.io", "Supabase", "PlanetScale", "MongoDB", "Redis", "PostgreSQL", "MySQL",
    "Elastic", "Kibana", "Kubernetes", "Terraform", "Ansible", "GitKraken", "Sourcetree",
    "Postman", "Insomnia", "Swagger", "Snyk", "SonarQube", "Codecov", "Coveralls",
    "Bugsnag", "Rollbar", "LogRocket", "Honeycomb", "Pingdom", "UptimeRobot", "StatusPage",
    "Launchdarkly", "Bitrise", "TeamCity", "Bamboo", "Argo CD", "GitHub Actions",
    "Visual Studio Code", "Visual Studio", "JetBrains", "IntelliJ IDEA", "PyCharm",
    "WebStorm", "Android Studio", "Xcode", "Gradle", "Apache Maven", "Yarn", "pnpm",
    # --- Cloud / hosting / storage ---
    "Amazon Web Services", ("AWS", "amazonwebservices"), "Microsoft Azure",
    "Google Cloud", "Dropbox", "Google Drive", "OneDrive", "iCloud", ("Box", "box"),
    "MEGA", "pCloud", "Nextcloud", "ownCloud", "Backblaze", "Sync",
    # --- Finance / payments / crypto ---
    "PayPal", "Stripe", "Venmo", "Cash App", "Wise", "Revolut", "Coinbase", "Binance",
    "Robinhood", "Square", "Zelle", "Klarna", "Afterpay", "Chime", "Monzo", "N26",
    "Wealthfront", "Betterment", "Kraken", "Crypto.com", "MetaMask", "Trust Wallet",
    "Ledger", "Blockchain.com", "KuCoin", "OKX", "Bybit", "Gemini", "Plaid", "Adyen",
    "Mastercard", "Visa", "American Express", "Discover", "PayPal", "Skrill", "Payoneer",
    "QuickBooks", "Xero", "FreshBooks", "Wave", "Expensify", "Mint", "YNAB",
    # --- Shopping / e-commerce ---
    "Amazon", "eBay", "Etsy", "Walmart", "Target", "AliExpress", "Alibaba", "Shopify",
    "Wish", "Mercado Libre", "Shopee", "Lazada", "Flipkart", "Rakuten", "Wayfair",
    "IKEA", "Best Buy", "Costco", "Newegg", "Temu", "SHEIN", "ASOS", "Zara", "H&M",
    "Nike", "Adidas", "Under Armour", "Sephora", "Instacart", "Gumtree",
    # --- Media / music / streaming ---
    "Spotify", "YouTube", "YouTube Music", "Netflix", "Apple Music", "Apple TV",
    "Disney+", ("Disney+", "disneyplus"), "Hulu", "Twitch", "SoundCloud", "Deezer",
    "Tidal", "Prime Video", "HBO Max", ("Max", "max"), "Plex", "Pandora", "Audible",
    "iHeartRadio", "Bandcamp", "Last.fm", "Shazam", "Crunchyroll", "Funimation", "Vudu",
    "Paramount+", "Peacock", "Sling TV", "DAZN", "Pluto TV", "Tubi", "Mixcloud",
    "Napster", "Qobuz", "Stitcher", "Pocket Casts", "Overcast", "Castbox",
    "Google Podcasts", "Apple Podcasts", "YouTube TV",
    # --- Gaming ---
    "Steam", "Epic Games", ("Battle.net", "battledotnet"), "Riot Games", ("EA", "ea"),
    "Electronic Arts", "Ubisoft", "GOG.com", "Xbox", "PlayStation", "Roblox", "Minecraft",
    "Twitch", "Nintendo", "Nintendo Switch", "Rockstar Games", "Bethesda", "Activision",
    "Blizzard", "Valve", "itch.io", "Humble Bundle", "Origin", "Rumble", "Faceit",
    "Garena", "Supercell", "Among Us", "Genshin Impact", "League of Legends", "Valorant",
    "Fortnite", "Call of Duty", "Apex Legends", "Dota 2", "Counter-Strike", "PUBG",
    "Razer", "Logitech G", "SteelSeries", "Corsair", "NVIDIA", "AMD", "Intel",
    # --- Browsers ---
    "Google Chrome", "Firefox", ("Microsoft Edge", None, "Edge"), "Brave", "Opera",
    "Vivaldi", "Tor Browser", "DuckDuckGo", "Arc", "Safari", "Opera GX",
    # --- News ---
    "Google News", "Apple News", "BBC", "CNN", "The New York Times", "Reuters",
    "The Guardian", "The Washington Post", "Bloomberg", "Financial Times",
    "The Wall Street Journal", "Forbes", "TechCrunch", "The Verge", "Engadget", "Wired",
    "Ars Technica", "Hacker News", "Al Jazeera", "AP News", "USA Today", "NPR", "Vice",
    "BuzzFeed", "Vox", "Politico", "The Economist", "Flipboard", "Feedly", "Pocket",
    # --- Travel / maps / mobility ---
    "Google Maps", "Waze", "Uber", "Lyft", "Airbnb", "Booking.com", "Expedia", "Agoda",
    "Hotels.com", "Trip.com", "Tripadvisor", "Skyscanner", "Kayak", "Hopper", "Grab",
    "Bolt", "Ola", "Lime", "Bird", "BlaBlaCar", "Trainline", "Citymapper", "Komoot",
    "Delta Air Lines", "United Airlines", "American Airlines", "Southwest Airlines",
    "Lufthansa", "Emirates", "Ryanair", "easyJet", "Qatar Airways", "Marriott", "Hilton",
    # --- Food delivery / restaurants ---
    "DoorDash", "Uber Eats", "Grubhub", "Deliveroo", "Just Eat", "Postmates", "Zomato",
    "Swiggy", "Foodpanda", "Wolt", "Caviar", "Seamless", "OpenTable", "McDonald's",
    "Starbucks", "Domino's", "Pizza Hut", "KFC", "Chipotle", "Dunkin'",
    # --- Dating ---
    "Tinder", "Bumble", "Hinge", "OkCupid", "Grindr", "Badoo", "Match", "PlentyOfFish",
    "Happn", "Coffee Meets Bagel",
    # --- Health / fitness ---
    "Fitbit", "Garmin", "MyFitnessPal", "Peloton", "Strava", "Headspace", "Calm",
    "WHOOP", "Oura", "Withings", "Samsung Health", "Google Fit", "Nike Run Club",
    "Zwift", "Flo", "Clue", "Noom", "Duolingo", "Babbel", "Khan Academy", "Coursera",
    "Udemy", "edX", "Skillshare", "Brilliant", "Quizlet", "Photomath", "Memrise",
    # --- Security / VPN / utilities ---
    "1Password", "Bitwarden", "LastPass", "Dashlane", "NordVPN", "ExpressVPN",
    "Proton VPN", ("Proton VPN", "protonvpn"), "Surfshark", "Mullvad", "Malwarebytes",
    "Norton", "McAfee", "Bitdefender", "Kaspersky", "Avast", "AVG", "Authy", "Okta",
    "Duo", "Cloudflare WARP", "Tailscale", "Pi-hole", "AdGuard",
    # --- Smart home / IoT ---
    "Google Home", "Amazon Alexa", "Philips Hue", "Ring", "Nest", "SmartThings", "Wyze",
    "Tuya", "Home Assistant", "IFTTT", "Sonos", "Roku", "Chromecast", "Apple HomeKit",
    "Tesla", "Arlo", "Eufy", "TP-Link", "Ubiquiti",
    # --- Google / Apple / Microsoft ecosystem extras ---
    "Google", "Google Photos", "Google Translate", "Google Lens", "Google Pay",
    "Google Play", "Google Meet", "Google Classroom", "Google Analytics", "Google Ads",
    "Apple", "App Store", "Apple Wallet", "FaceTime", "Find My", "Apple Podcasts",
    "Microsoft", "Microsoft Store", "Microsoft Authenticator", "Microsoft Bing", "Copilot",
    "Windows", "OneDrive",
    # --- Misc popular ---
    "Notion", "Telegram", "Twitch", "ChatGPT", ("OpenAI", "openai"), "Claude",
    ("Anthropic", "anthropic"), "Gemini", ("Google Gemini", "googlegemini"),
    "Perplexity", "Midjourney", "Hugging Face", "Replika", "Character.AI", "Notion AI",
    "Grammarly", "DeepL", "Wikipedia", "Internet Archive", "WordPress", "Ghost", "Wix",
    "Squarespace", "Webflow", "Framer", "Zendesk", "Intercom", "Freshdesk", "HubSpot",
    "Salesforce", "Pipedrive", "Drift", "Crisp", "Help Scout", "Twilio", "Vonage",
    "Mixpanel", "Amplitude", "Segment", "Hotjar", "Optimizely", "Typeform", "SurveyMonkey",
    "Eventbrite", "Ticketmaster", "StubHub", "Patreon", "Ko-fi", "Buy Me a Coffee",
    "GoFundMe", "Kickstarter", "Indiegogo", "Cameo", "Discogs",
]


def resolve(entry):
    if isinstance(entry, str):
        name, slug, aliases = entry, None, []
    else:
        name = entry[0]
        slug = entry[1] if len(entry) > 1 else None
        aliases = list(entry[2:]) if len(entry) > 2 else []
    if name in SUPPLEMENTS:
        return name, SUPPLEMENTS[name], aliases
    hexv = None
    if slug:
        hexv = INDEX.get(norm(slug))
    if hexv is None:
        hexv = INDEX.get(norm(name))
    return name, hexv, aliases


def hex_to_rgb(h):
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)]


out = {}          # normalized key -> [r,g,b]
resolved_names = set()
missed_names = set()

for entry in CURATED:
    name, hexv, aliases = resolve(entry)
    if name in resolved_names:
        continue
    if hexv is None:
        missed_names.add(name)
        continue
    missed_names.discard(name)
    resolved_names.add(name)
    rgb = hex_to_rgb(hexv)
    keys = [norm(name)] + [norm(a) for a in aliases]
    # auto un-prefix common company words so "Microsoft Outlook" also matches "Outlook"
    n = norm(name)
    for pfx in ("microsoft", "google", "apple", "amazon", "meta"):
        if n.startswith(pfx) and len(n) > len(pfx) + 2:
            keys.append(n[len(pfx):])
    for k in keys:
        out.setdefault(k, rgb)

print(f"resolved={len(resolved_names)}  keys={len(out)}  misses={len(missed_names)}")
if missed_names:
    print("MISSES:", ", ".join(sorted(missed_names)))

# Emit module
lines = []
for k in sorted(out):
    lines.append(f'    "{k}": ({out[k][0]}, {out[k][1]}, {out[k][2]}),')
body = "\n".join(lines)

# Appended verbatim (plain string, so literal braces need no escaping) after the
# generated BRAND_COLORS dict + brand_color(). Handles forwarded/mirrored
# notifications (Phone Link etc.) by detecting the real source app from the text.
_EXTRA = r'''

# --- Forwarded / mirrored notifications -------------------------------------
# Bridges that relay phone notifications to the desktop report *themselves* as the
# originating app (an Instagram DM mirrored by Phone Link shows up as "Phone Link").
# For these we detect the real source app from the notification text and use ITS
# brand colour instead of the bridge's.
_FORWARDERS = frozenset({
    "phonelink", "linktowindows", "yourphone", "yourphonecompanion",
    "intelunison", "dellmobileconnect", "samsungflow", "samsungdex",
    "airdroid", "pushbullet", "kdeconnect", "mobileconnect",
})

# Curated, distinctive source-app names safe to match inside free notification text
# (word-boundary matched). Short/ambiguous names (e.g. "Line", "X") are excluded so
# ordinary message wording can't trigger a false colour. Every name is a brand in
# the table above.
_SOURCE_BRAND_NAMES = (
    "Microsoft Teams", "Facebook Messenger", "Google Chat", "Booking.com",
    "Uber Eats", "Cash App", "Instagram", "WhatsApp", "Messenger", "Facebook",
    "Snapchat", "Telegram", "Signal", "TikTok", "Twitter", "Discord", "Slack",
    "WeChat", "Viber", "KakaoTalk", "Reddit", "LinkedIn", "Pinterest", "Tinder",
    "Bumble", "Hinge", "Threads", "Grindr", "Tumblr", "Mastodon", "Bluesky",
    "Skype", "Zoom", "Gmail", "Outlook", "YouTube", "Spotify", "Twitch", "Netflix",
    "SoundCloud", "Uber", "Lyft", "DoorDash", "Grubhub", "Deliveroo", "Zomato",
    "Swiggy", "PayPal", "Venmo", "Revolut", "Coinbase", "Binance", "Robinhood",
    "Zelle", "Klarna", "Amazon", "Etsy", "AliExpress", "Airbnb", "GitHub", "GitLab",
    "Strava", "Duolingo", "Notion", "Trello", "Asana", "Jira",
)


def _compile_source_patterns():
    pats = []
    # Longest names first so e.g. "Uber Eats" wins over "Uber".
    for nm in sorted(_SOURCE_BRAND_NAMES, key=len, reverse=True):
        rgb = brand_color(nm)
        if rgb is None:
            continue
        body = r"\s+".join(re.escape(p) for p in nm.split())
        pats.append((re.compile(r"\b" + body + r"\b", re.IGNORECASE), rgb))
    return pats


_SOURCE_PATTERNS = _compile_source_patterns()


def is_forwarder(app_name: Optional[str], app_id: Optional[str] = None) -> bool:
    """True when a notification comes from a phone-mirroring / relay bridge whose
    own name is not the real source app (Phone Link, Link to Windows, ...)."""
    if _norm(app_name) in _FORWARDERS:
        return True
    if app_id:
        nid = _norm(app_id)
        return any(f in nid for f in _FORWARDERS)
    return False


def brand_color_from_text(text: Optional[str]) -> Optional[RGB]:
    """Detect a known source-app brand mentioned in *text* and return its colour.

    For forwarded notifications whose attributed app is a bridge, the real app is
    named in the title/body (e.g. "Instagram: liked your photo"). Matched against a
    curated, distinctive set with word boundaries so ordinary wording doesn't fire.
    """
    if not text:
        return None
    for pat, rgb in _SOURCE_PATTERNS:
        if pat.search(text):
            return rgb
    return None
'''

module = f'''"""
Brand-colour table (auto-generated — do not hand-edit)
======================================================
Maps a normalised app/brand name to its official logo RGB colour, used by the
Notification Flash to colour a flash by the originating app even when the live
notification carries no icon bytes (e.g. Phone Link forwards) — and to suggest
colours in the per-app UI. Regenerate with ``scripts/gen_brand_colors.py``.

Colour source: the simple-icons project (CC0; official brand-guideline hexes),
supplemented with web-verified official hexes for brands simple-icons removed on
trademark requests (Microsoft products, LinkedIn, Slack, Amazon).

This is a *fallback/suggestion* layer: an explicit per-app override or keyword
rule always wins (see ``NotificationFlashService.resolve_color``).
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

RGB = Tuple[int, int, int]

# Company prefixes stripped when matching, so an app reporting itself as either
# "Microsoft Outlook" or "Outlook" resolves to the same brand.
_PREFIXES = ("microsoft", "google", "apple", "amazon", "meta")


def _norm(s: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# normalised name -> (r, g, b)
BRAND_COLORS: dict = {{
{body}
}}


def brand_color(app_name: Optional[str], app_id: Optional[str] = None) -> Optional[RGB]:
    """Return the official brand RGB for an app, or ``None`` if unknown.

    Matches the display name first (most reliable), then a company-prefix-stripped
    form, then scans tokens of the AUMID/bundle-id ``app_id`` for a known brand.
    """
    name = _norm(app_name)
    if name in BRAND_COLORS:
        return BRAND_COLORS[name]
    for pfx in _PREFIXES:
        if name.startswith(pfx) and len(name) > len(pfx) + 2:
            stripped = name[len(pfx):]
            if stripped in BRAND_COLORS:
                return BRAND_COLORS[stripped]
    # Fall back to the app id (e.g. AUMID "com.squirrel.Discord.Discord"): try the
    # whole normalised id, then each alphanumeric token, longest first so
    # "discord" wins over a short generic token.
    if app_id:
        nid = _norm(app_id)
        if nid in BRAND_COLORS:
            return BRAND_COLORS[nid]
        tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", app_id) if len(t) >= 3]
        for tok in sorted(tokens, key=len, reverse=True):
            t = _norm(tok)
            # Skip bare publisher tokens (e.g. the "Microsoft" in a Phone Link
            # AUMID "Microsoft.YourPhone..."); otherwise every app from a big
            # publisher would borrow the parent brand's colour.
            if t in _PREFIXES:
                continue
            if t in BRAND_COLORS:
                return BRAND_COLORS[t]
    return None
''' + _EXTRA

open(sys.argv[2], "w", encoding="utf-8").write(module)
print("wrote", sys.argv[2])
