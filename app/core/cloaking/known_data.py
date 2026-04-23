"""
Built-in IP ranges, ASNs, and User-Agent patterns for known bots and ad reviewers.

Sources:
  - Facebook/Meta: https://developers.facebook.com/docs/sharing/webmasters/crawler
  - Google:        https://developers.google.com/search/docs/crawling-indexing/verifying-googlebot
  - Apple:         https://support.apple.com/en-us/101555
  - Bing:          https://learn.microsoft.com/en-us/bingwebmaster/verifying-bingbot
  - IPinfo ASN data (public)
"""

from typing import Dict, List, Tuple

# ── IP ranges ─────────────────────────────────────────────────────────────────
# Format: (cidr, asn_or_None, visitor_type, confidence, description)
# visitor_type: "bot" | "ad_review"

KNOWN_IP_RANGES: List[Tuple[str, str, float, str]] = [

    # ── Facebook / Meta ───────────────────────────────────────────────────────
    # Crawler (Open Graph scraper, link preview)
    ("31.13.24.0/21",   "bot",       0.97, "Facebook crawler AS32934"),
    ("31.13.64.0/18",   "bot",       0.97, "Facebook crawler AS32934"),
    ("66.220.144.0/20", "bot",       0.97, "Facebook crawler AS32934"),
    ("66.220.144.0/21", "bot",       0.97, "Facebook crawler AS32934"),
    ("69.63.176.0/20",  "bot",       0.97, "Facebook crawler AS32934"),
    ("69.171.224.0/19", "bot",       0.97, "Facebook crawler AS32934"),
    ("69.171.255.0/24", "bot",       0.97, "Facebook crawler AS32934"),
    ("74.119.76.0/22",  "bot",       0.97, "Facebook crawler AS32934"),
    ("103.4.96.0/22",   "bot",       0.97, "Facebook crawler AS32934"),
    ("173.252.64.0/18", "bot",       0.97, "Facebook crawler AS32934"),
    ("179.60.192.0/22", "bot",       0.97, "Facebook crawler AS32934"),
    ("185.60.216.0/22", "bot",       0.97, "Facebook crawler AS32934"),
    ("204.15.20.0/22",  "bot",       0.97, "Facebook crawler AS32934"),

    # Facebook Ads review infrastructure
    ("66.220.152.0/21", "ad_review", 0.93, "Facebook Ads review infrastructure"),
    ("66.220.144.0/20", "ad_review", 0.90, "Facebook Ads review infrastructure"),
    ("204.15.20.0/22",  "ad_review", 0.90, "Facebook Ads review infrastructure"),

    # ── Google ────────────────────────────────────────────────────────────────
    ("64.233.160.0/19",  "bot", 0.98, "Googlebot AS15169"),
    ("66.102.0.0/20",    "bot", 0.98, "Googlebot AS15169"),
    ("66.249.64.0/19",   "bot", 0.98, "Googlebot AS15169"),
    ("66.249.80.0/20",   "bot", 0.98, "Googlebot AS15169"),
    ("72.14.192.0/18",   "bot", 0.98, "Google AS15169"),
    ("74.125.0.0/16",    "bot", 0.98, "Google AS15169"),
    ("108.177.8.0/21",   "bot", 0.98, "Google AS15169"),
    ("173.194.0.0/16",   "bot", 0.98, "Google AS15169"),
    ("209.85.128.0/17",  "bot", 0.98, "Googlebot AS15169"),
    ("216.58.192.0/19",  "bot", 0.98, "Google AS15169"),
    ("216.239.32.0/19",  "bot", 0.98, "Google AS15169"),
    ("35.190.0.0/17",    "bot", 0.97, "Google Cloud / Ads AS15169"),
    ("35.235.240.0/20",  "bot", 0.97, "Google Cloud / Ads AS15169"),

    # Google Ads review
    ("66.249.64.0/19",   "ad_review", 0.92, "Google Ads review AS15169"),
    ("64.233.173.0/24",  "ad_review", 0.92, "Google Ads review AS15169"),

    # ── Bing / Microsoft ──────────────────────────────────────────────────────
    ("40.77.167.0/24",   "bot", 0.97, "Bingbot AS8075"),
    ("65.52.104.0/24",   "bot", 0.97, "Bingbot AS8075"),
    ("65.55.210.0/24",   "bot", 0.97, "Bingbot AS8075"),
    ("157.55.33.0/24",   "bot", 0.97, "Bingbot AS8075"),
    ("157.55.39.0/24",   "bot", 0.97, "Bingbot AS8075"),
    ("199.30.24.0/23",   "bot", 0.97, "Bingbot AS8075"),
    ("207.46.0.0/16",    "bot", 0.95, "Microsoft AS8075"),

    # ── Apple ─────────────────────────────────────────────────────────────────
    ("17.0.0.0/8",       "bot", 0.90, "Apple AS714 (Applebot / review)"),
    ("17.172.224.0/19",  "bot", 0.95, "Apple crawler AS714"),
    ("17.142.160.0/19",  "bot", 0.95, "Apple App Store review"),

    # ── Yandex ────────────────────────────────────────────────────────────────
    ("5.45.192.0/18",    "bot", 0.97, "Yandex AS13238"),
    ("5.255.192.0/18",   "bot", 0.97, "Yandex AS13238"),
    ("37.9.64.0/18",     "bot", 0.97, "Yandex AS13238"),
    ("37.140.128.0/18",  "bot", 0.97, "Yandex AS13238"),
    ("77.88.0.0/18",     "bot", 0.97, "Yandex AS13238"),
    ("84.201.128.0/18",  "bot", 0.97, "Yandex AS13238"),
    ("87.250.224.0/19",  "bot", 0.97, "Yandex AS13238"),
    ("93.158.128.0/18",  "bot", 0.97, "Yandex AS13238"),
    ("95.108.128.0/17",  "bot", 0.97, "Yandex AS13238"),
    ("100.43.80.0/20",   "bot", 0.97, "Yandex AS13238"),
    ("141.8.128.0/18",   "bot", 0.97, "Yandex AS13238"),
    ("178.154.128.0/18", "bot", 0.97, "Yandex AS13238"),
    ("199.21.99.0/24",   "bot", 0.97, "Yandex AS13238"),
    ("213.180.192.0/19", "bot", 0.97, "Yandex AS13238"),

    # ── Twitter / X ───────────────────────────────────────────────────────────
    ("199.16.156.0/22",  "bot", 0.95, "Twitterbot AS13414"),
    ("199.59.148.0/22",  "bot", 0.95, "Twitterbot AS13414"),
    ("192.133.76.0/22",  "bot", 0.95, "Twitter AS13414"),

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    ("108.174.0.0/20",   "bot", 0.95, "LinkedIn AS14413"),
    ("144.2.0.0/16",     "bot", 0.95, "LinkedIn AS14413"),
    ("185.63.144.0/22",  "bot", 0.95, "LinkedIn AS14413"),

    # ── Amazon / AWS ──────────────────────────────────────────────────────────
    # AWS datacenter — not directly bots, but suspicious without UA match
    ("3.0.0.0/9",        "suspicious", 0.55, "AWS AS16509 datacenter"),
    ("52.0.0.0/11",      "suspicious", 0.55, "AWS AS16509 datacenter"),
    ("54.0.0.0/8",       "suspicious", 0.55, "AWS AS16509 datacenter"),

    # ── SEO crawlers ──────────────────────────────────────────────────────────
    ("149.56.0.0/16",    "bot", 0.85, "SEMrush AS16276"),
    ("185.191.171.0/24", "bot", 0.85, "Ahrefs AS394711"),
    ("54.36.148.0/22",   "bot", 0.85, "Ahrefs AS16276"),
    ("207.46.13.0/24",   "bot", 0.80, "Majestic SEO"),
]

# ── Known ASNs ────────────────────────────────────────────────────────────────
# Format: (asn, visitor_type, confidence, description)

KNOWN_ASNS: List[Tuple[int, str, float, str]] = [
    (32934,  "bot",       0.93, "Meta/Facebook"),
    (15169,  "bot",       0.93, "Google"),
    (8075,   "bot",       0.93, "Microsoft/Bing"),
    (714,    "bot",       0.88, "Apple"),
    (13238,  "bot",       0.93, "Yandex"),
    (13414,  "bot",       0.90, "Twitter/X"),
    (14413,  "bot",       0.88, "LinkedIn"),
    (394711, "bot",       0.82, "Ahrefs"),
    (16276,  "bot",       0.75, "OVH (often SEO bots)"),
    (16509,  "suspicious",0.50, "Amazon AWS"),
    (14618,  "suspicious",0.50, "Amazon AWS legacy"),
    (396982, "suspicious",0.50, "Google Cloud"),
    (15830,  "suspicious",0.50, "Akamai CDN"),
    (20940,  "suspicious",0.50, "Akamai CDN"),
    (209,    "suspicious",0.50, "CenturyLink/Lumen datacenter"),
]

# ── User-Agent patterns ───────────────────────────────────────────────────────
# Format: (regex_pattern, visitor_type, confidence, description)
# All patterns are case-insensitive.

KNOWN_UA_PATTERNS: List[Tuple[str, str, float, str]] = [

    # ── Search engine crawlers ────────────────────────────────────────────────
    (r"\bgooglebot\b",              "bot", 0.99, "Googlebot"),
    (r"\bgooglebot-image\b",        "bot", 0.99, "Googlebot Image"),
    (r"\bgooglebot-mobile\b",       "bot", 0.99, "Googlebot Mobile"),
    (r"\bapis\.google\.com\b",      "bot", 0.97, "Google APIs"),
    (r"\badsbot-google\b",          "ad_review", 0.97, "Google Ads review bot"),
    (r"\bmediapartners-google\b",   "ad_review", 0.97, "Google AdSense"),
    (r"\bgoogle-adwords-instant\b", "ad_review", 0.97, "Google AdWords"),
    (r"\bbingbot\b",                "bot", 0.99, "Bingbot"),
    (r"\bmsnbot\b",                 "bot", 0.98, "MSNBot"),
    (r"\badidxbot\b",               "ad_review", 0.97, "Bing Ads review"),
    (r"\byandexbot\b",              "bot", 0.99, "YandexBot"),
    (r"\byandex\.com/bots\b",       "bot", 0.99, "YandexBot"),
    (r"\byandexmobilebot\b",        "bot", 0.99, "Yandex Mobile Bot"),
    (r"\byandexdirect\b",           "ad_review", 0.97, "Yandex Direct review"),
    (r"\bduckduckbot\b",            "bot", 0.99, "DuckDuckBot"),
    (r"\bbaidu\b",                  "bot", 0.96, "Baiduspider"),
    (r"\bbaiduspider\b",            "bot", 0.99, "Baiduspider"),
    (r"\bsogou\b",                  "bot", 0.95, "Sogou crawler"),
    (r"\bexabot\b",                 "bot", 0.97, "Exabot"),
    (r"\bfacebot\b",                "bot", 0.96, "Facebook bot"),

    # ── Social / link preview crawlers ────────────────────────────────────────
    (r"\bfacebookexternalhit\b",    "bot", 0.99, "Facebook link preview"),
    (r"\bfacebook\.com/externalhit", "bot", 0.99, "Facebook link preview"),
    (r"\bfacebookcatalog\b",        "ad_review", 0.97, "Facebook Catalog"),
    (r"\btwitterbot\b",             "bot", 0.99, "Twitterbot"),
    (r"\blinkedinbot\b",            "bot", 0.99, "LinkedInBot"),
    (r"\bpinterest\b",              "bot", 0.95, "Pinterest bot"),
    (r"\bslackbot\b",               "bot", 0.99, "Slackbot link preview"),
    (r"\bslack-imgproxy\b",         "bot", 0.99, "Slack image proxy"),
    (r"\bdiscordbot\b",             "bot", 0.99, "Discordbot"),
    (r"\btelegrambot\b",            "bot", 0.99, "TelegramBot"),
    (r"\bwhatsapp\b",               "bot", 0.95, "WhatsApp link preview"),
    (r"\bviber\b",                  "bot", 0.90, "Viber bot"),
    (r"\bline-poker\b",             "bot", 0.90, "LINE messenger bot"),
    (r"\bvkshare\b",                "bot", 0.97, "VK Share bot"),
    (r"\bokhttp\b",                 "bot", 0.75, "OkHttp (Android bots)"),

    # ── Apple ─────────────────────────────────────────────────────────────────
    (r"\bapplebot\b",               "bot", 0.99, "Applebot"),
    (r"\bapplesafari\b",            "bot", 0.95, "Apple Safari bot"),

    # ── SEO / audit tools ─────────────────────────────────────────────────────
    (r"\bsemrushbot\b",             "bot", 0.99, "SEMrush"),
    (r"\bahrefsbot\b",              "bot", 0.99, "Ahrefs"),
    (r"\bmj12bot\b",                "bot", 0.99, "Majestic"),
    (r"\bdotbot\b",                 "bot", 0.99, "OpenLinkProfiler"),
    (r"\bblexbot\b",                "bot", 0.99, "BLEXBot"),
    (r"\bpetalbot\b",               "bot", 0.99, "Huawei Petal Search"),
    (r"\bseokicks\b",               "bot", 0.97, "SEOkicks"),
    (r"\bscreaming.?frog\b",        "bot", 0.97, "Screaming Frog SEO"),
    (r"\bsitechecker\b",            "bot", 0.97, "SiteChecker"),
    (r"\bmagestic\b",               "bot", 0.97, "Majestic"),
    (r"\bspyfu\b",                  "bot", 0.95, "SpyFu"),
    (r"\bsimilarweb\b",             "bot", 0.97, "SimilarWeb"),
    (r"\bseoprofiler\b",            "bot", 0.95, "SEO Profiler"),
    (r"\bnetsystemsresearch\b",     "bot", 0.95, "Net Systems Research"),

    # ── Generic bot signals ───────────────────────────────────────────────────
    (r"\bcrawler\b",                "bot", 0.80, "Generic crawler UA"),
    (r"\bspider\b",                 "bot", 0.75, "Generic spider UA"),
    (r"\bscraper\b",                "bot", 0.80, "Generic scraper UA"),
    (r"\bfetcher\b",                "bot", 0.75, "Generic fetcher UA"),
    (r"\barchiver\b",               "bot", 0.75, "Generic archiver UA"),
    (r"\bmonitor\b",                "bot", 0.60, "Monitoring bot"),
    (r"\bscanner\b",                "bot", 0.65, "Scanner bot"),
    (r"\bcheck\b.*\bhttp\b",        "bot", 0.60, "HTTP check utility"),
    (r"\bwget\b",                   "bot", 0.95, "wget"),
    (r"\bcurl\b",                   "bot", 0.90, "curl"),
    (r"\bpython-requests\b",        "bot", 0.90, "Python requests library"),
    (r"\bhttpclient\b",             "bot", 0.85, "Generic HTTP client"),
    (r"\bjava\b/\d",                "bot", 0.80, "Java HTTP client"),
    (r"\bgo-http-client\b",         "bot", 0.85, "Go HTTP client"),
    (r"\bruby\b",                   "bot", 0.70, "Ruby HTTP client"),
    (r"\bphp\b",                    "bot", 0.65, "PHP HTTP client"),
    (r"\bperl\b",                   "bot", 0.80, "Perl LWP"),
    (r"\blibwww-perl\b",            "bot", 0.90, "Perl LWP"),

    # ── Uptime / synthetic monitoring ─────────────────────────────────────────
    (r"\buptimerobot\b",            "bot", 0.99, "UptimeRobot monitor"),
    (r"\bpingdom\b",                "bot", 0.99, "Pingdom monitor"),
    (r"\bnewrelic\b",               "bot", 0.99, "New Relic Synthetics"),
    (r"\bdatadog\b",                "bot", 0.99, "Datadog Synthetics"),
    (r"\bstatuscake\b",             "bot", 0.99, "StatusCake monitor"),
    (r"\bsite24x7\b",               "bot", 0.99, "Site24x7 monitor"),
    (r"\bfreshping\b",              "bot", 0.99, "Freshping monitor"),
    (r"\bzabbix\b",                 "bot", 0.95, "Zabbix monitor"),
    (r"\bnagios\b",                 "bot", 0.95, "Nagios monitor"),
    (r"\bpagerduty\b",              "bot", 0.95, "PagerDuty"),

    # ── Web archive ───────────────────────────────────────────────────────────
    (r"\bia_archiver\b",            "bot", 0.99, "Internet Archive"),
    (r"\barchive\.org\b",           "bot", 0.99, "Internet Archive"),
    (r"\bwayback\b",                "bot", 0.99, "Wayback Machine"),

    # ── Ad fraud / click fraud patterns ───────────────────────────────────────
    (r"\bphantomjs\b",              "suspicious", 0.90, "PhantomJS headless browser"),
    (r"headlesschrome",             "suspicious", 0.90, "HeadlessChrome browser"),
    (r"\bheadless\b",               "suspicious", 0.85, "Headless browser generic"),
    (r"headless",                   "suspicious", 0.80, "Headless keyword in UA"),
    (r"\bchrome-lighthouse\b",      "bot",        0.95, "Google Lighthouse audit"),
    (r"\bselenium\b",               "suspicious", 0.90, "Selenium automation"),
    (r"\bwebdriver\b",              "suspicious", 0.90, "WebDriver automation"),
    (r"\bpuppeteer\b",              "suspicious", 0.90, "Puppeteer headless"),
    (r"\bplaywright\b",             "suspicious", 0.90, "Playwright automation"),
]
