#!/usr/bin/env python3
"""
FPSO Project Crawler
Scrapes offshore industry news sites for FPSO-related articles,
extracts project metadata, and stores results in Supabase.

Usage: python crawler/crawl.py
"""

import os
import re
import sys
import time
import random
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client

# ---- Config -----------------------------------------------------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
    sys.exit(1)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0)"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fpso-crawler")

# ---- Site definitions ------------------------------------------------

SITES = [
    {
        "name": "Offshore Energy",
        "domain": "offshore-energy.biz",
        "urls": [
            "https://www.offshore-energy.biz/?s=FPSO",
        ],
        "article_tag": "article",
        "fallback_class": re.compile(r"post|article|story|result|item", re.I),
        "title_sel": "h2 a, h3 a, .entry-title a",
        "date_sel": "time, .entry-date, .posted-on, .post-date",
        "summary_sel": ".entry-summary, .entry-content p, .excerpt",
    },
    {
        "name": "OE Digital",
        "domain": "oedigital.com",
        "urls": [
            "https://www.oedigital.com/search?q=FPSO",
            "https://www.oedigital.com/?s=FPSO",
        ],
        "article_tag": "article",
        "fallback_class": re.compile(r"post|article|story|result|item|search-result", re.I),
        "title_sel": "h2 a, h3 a, .title a, .headline a",
        "date_sel": "time, .date, .published, .pub-date",
        "summary_sel": "p, .summary, .excerpt, .teaser, .body",
    },
    {
        "name": "World Oil",
        "domain": "worldoil.com",
        "urls": [
            "https://www.worldoil.com/search?q=FPSO",
            "https://www.worldoil.com/?s=FPSO",
            "https://www.worldoil.com/search/FPSO",
        ],
        "article_tag": "article",
        "fallback_class": re.compile(r"post|article|story|result|item|search-result", re.I),
        "title_sel": "h2 a, h3 a, .headline a, .title a",
        "date_sel": "time, .date, .pub-date, .published",
        "summary_sel": "p, .summary, .excerpt, .abstract, .teaser",
    },
    {
        "name": "Splash247",
        "domain": "splash247.com",
        "urls": [
            "https://splash247.com/?s=FPSO",
        ],
        "article_tag": "article",
        "fallback_class": re.compile(r"post|article|story|result|item", re.I),
        "title_sel": "h2 a, h3 a, .entry-title a, .post-title a",
        "date_sel": "time, .entry-date, .post-date, .published",
        "summary_sel": ".entry-summary, .entry-content p, .excerpt",
    },
]

# ---- Project extraction patterns -------------------------------------

COUNTRY_LIST = [
    "Brazil", "Guyana", "Angola", "Nigeria", "Norway", "UK",
    "China", "Malaysia", "Indonesia", "Australia", "Ghana",
    "Senegal", "Mauritania", "India", "USA", "Canada", "Mexico",
    "Vietnam", "Thailand", "Qatar", "UAE", "Saudi Arabia",
    "Mozambique", "Egypt", "Libya", "Equatorial Guinea", "Congo",
    "Gabon", "Ivory Coast", "Cameroon", "Trinidad and Tobago",
    "Suriname", "Argentina", "Russia", "Azerbaijan", "Kazakhstan",
    "South Korea", "Singapore", "Japan", "Netherlands", "Denmark",
    "Namibia", "South Africa", "Israel", "Cyprus", "Turkey",
    "Iraq", "Iran", "Kuwait", "Oman", "Bahrain", "Yemen",
    "Philippines", "Peru", "Colombia", "Uruguay", "Venezuela",
    "Tanzania", "Kenya", "Somalia", "Sudan", "Algeria",
    "Tunisia", "Morocco", "Spain", "France", "Italy",
    "Greece", "Portugal", "Germany", "Belgium", "Poland",
    "Romania", "Bulgaria", "Croatia", "Malta", "New Zealand",
    "Papua New Guinea", "Brunei", "Myanmar", "Bangladesh",
    "Sri Lanka", "Pakistan", "Chile", "Ecuador", "Falkland Islands",
    "South Sudan", "Timor-Leste", "Ivory Coast",
]

# ---- Region / Basin / Block → Country mapping (highest priority) -----

REGION_TO_COUNTRY = {
    # Brazil
    "Santos Basin": "Brazil",
    "Santos basin": "Brazil",
    "Campos Basin": "Brazil",
    "Campos basin": "Brazil",
    "Espírito Santo Basin": "Brazil",
    "Espirito Santo Basin": "Brazil",
    "Sergipe-Alagoas Basin": "Brazil",
    "Potiguar Basin": "Brazil",
    "Ceará Basin": "Brazil",
    "Ceara Basin": "Brazil",
    "Barreirinhas Basin": "Brazil",
    "Foz do Amazonas Basin": "Brazil",
    "Pará-Maranhão Basin": "Brazil",
    "Pelotas Basin": "Brazil",
    "Bacia de Santos": "Brazil",
    "Bacia de Campos": "Brazil",
    "pre-salt Santos": "Brazil",
    "pre-salt Campos": "Brazil",
    "pre-salt Brazil": "Brazil",
    "offshore Brazil": "Brazil",
    "Brazilian waters": "Brazil",
    "Brazilian coast": "Brazil",
    "Brazilian offshore": "Brazil",

    # Guyana / Suriname
    "Stabroek Block": "Guyana",
    "Stabroek block": "Guyana",
    "Stabroek": "Guyana",
    "Guyana Basin": "Guyana",
    "Guyana-Suriname Basin": "Guyana",
    "Guyana Suriname Basin": "Guyana",
    "offshore Guyana": "Guyana",
    "Guyanese waters": "Guyana",
    "Canje Block": "Guyana",
    "Kaieteur Block": "Guyana",
    "Corentyne Block": "Guyana",
    "offshore Suriname": "Suriname",
    "Suriname Basin": "Suriname",
    "Suriname-Guyana Basin": "Suriname",
    "Block 58": "Suriname",
    "Block 58 Suriname": "Suriname",

    # Angola
    "Angola Basin": "Angola",
    "Kwanza Basin": "Angola",
    "Lower Congo Basin": "Angola",
    "Lower Congo": "Angola",
    "offshore Angola": "Angola",
    "Angolan waters": "Angola",
    "Angolan offshore": "Angola",
    "Block 17 Angola": "Angola",
    "Block 15 Angola": "Angola",
    "Block 31 Angola": "Angola",
    "Block 32 Angola": "Angola",

    # Nigeria
    "Niger Delta": "Nigeria",
    "Niger Delta Basin": "Nigeria",
    "offshore Nigeria": "Nigeria",
    "Nigerian waters": "Nigeria",
    "Nigerian offshore": "Nigeria",
    "OML 130": "Nigeria",
    "Bonga field": "Nigeria",
    "Egina field": "Nigeria",
    "Akpo field": "Nigeria",

    # Ghana
    "Tano Basin": "Ghana",
    "Tano basin": "Ghana",
    "offshore Ghana": "Ghana",
    "Jubilee Field": "Ghana",
    "Jubilee field": "Ghana",
    "TEN field": "Ghana",
    "TEN Field": "Ghana",
    "Pecan field": "Ghana",

    # Senegal / Mauritania
    "offshore Senegal": "Senegal",
    "Senegal Basin": "Senegal",
    "Sangomar field": "Senegal",
    "Sangomar Field": "Senegal",
    "Grand Tortue": "Mauritania",
    "Tortue Ahmeyim": "Mauritania",
    "offshore Mauritania": "Mauritania",
    "BirAllah": "Mauritania",
    "Orca field": "Mauritania",

    # Mozambique
    "Rovuma Basin": "Mozambique",
    "Rovuma basin": "Mozambique",
    "offshore Mozambique": "Mozambique",
    "Area 1 Mozambique": "Mozambique",
    "Area 4 Mozambique": "Mozambique",
    "Coral field": "Mozambique",
    "Coral Sul": "Mozambique",

    # North Sea
    "North Sea": None,  # ambiguous — needs context
    "Norwegian North Sea": "Norway",
    "UK North Sea": "UK",
    "British North Sea": "UK",
    "Norwegian Sea": "Norway",
    "Barents Sea": "Norway",
    "Norwegian sector": "Norway",
    "UK sector": "UK",
    "British waters": "UK",
    "offshore Norway": "Norway",
    "offshore UK": "UK",
    "Norwegian waters": "Norway",
    "Norwegian offshore": "Norway",
    "UK waters": "UK",
    "UK offshore": "UK",
    "North Sea Norway": "Norway",
    "North Sea UK": "UK",

    # Gulf of Mexico
    "Gulf of Mexico": "USA",
    "GoM": "USA",
    "US Gulf of Mexico": "USA",
    "US Gulf": "USA",
    "Mexico Gulf": "Mexico",
    "Mexican Gulf": "Mexico",
    "offshore Mexico": "Mexico",

    # Australia
    "Browse Basin": "Australia",
    "Browse basin": "Australia",
    "Carnarvon Basin": "Australia",
    "Carnarvon basin": "Australia",
    "Bonaparte Basin": "Australia",
    "Bonaparte basin": "Australia",
    "offshore Australia": "Australia",
    "NW Shelf Australia": "Australia",
    "North West Shelf": "Australia",
    "NW Shelf": "Australia",
    "Timor Sea": "Australia",
    "Bass Strait": "Australia",
    "Gippsland Basin": "Australia",
    "Scarborough field": "Australia",
    "Barossa field": "Australia",
    "Ichthys field": "Australia",
    "Prelude field": "Australia",
    "Browse FLNG": "Australia",
    "Scarborough FLNG": "Australia",

    # Malaysia
    "offshore Malaysia": "Malaysia",
    "Sarawak Basin": "Malaysia",
    "Sabah Basin": "Malaysia",
    "Malay Basin": "Malaysia",
    "Limbayong field": "Malaysia",

    # Indonesia
    "offshore Indonesia": "Indonesia",
    "Kutei Basin": "Indonesia",
    "Tarakan Basin": "Indonesia",
    "Natuna Sea": "Indonesia",
    "Makassar Strait": "Indonesia",

    # Vietnam
    "offshore Vietnam": "Vietnam",
    "Cuu Long Basin": "Vietnam",
    "Nam Con Son Basin": "Vietnam",
    "Song Hong Basin": "Vietnam",

    # China
    "offshore China": "China",
    "South China Sea": None,  # ambiguous
    "Bohai Bay": "China",
    "Bohai Sea": "China",
    "Pearl River Mouth Basin": "China",

    # India
    "offshore India": "India",
    "Krishna Godavari Basin": "India",
    "KG Basin": "India",
    "KG-DWN": "India",
    "Mumbai High": "India",
    "Cambay Basin": "India",

    # Qatar / Middle East
    "Persian Gulf": None,  # ambiguous
    "North Field": "Qatar",
    "North Field Qatar": "Qatar",
    "North Field Expansion": "Qatar",
    "South Pars": "Iran",
    "offshore Qatar": "Qatar",
    "offshore UAE": "UAE",
    "offshore Saudi Arabia": "Saudi Arabia",
    "offshore Kuwait": "Kuwait",
    "Arabian Gulf": None,

    # Egypt
    "offshore Egypt": "Egypt",
    "Mediterranean Egypt": "Egypt",
    "Zohr field": "Egypt",
    "Nile Delta": "Egypt",
    "Nile Delta Basin": "Egypt",

    # Israel / Cyprus
    "offshore Israel": "Israel",
    "offshore Cyprus": "Cyprus",
    "Leviathan field": "Israel",
    "Tamar field": "Israel",
    "Aphrodite field": "Cyprus",
    "Levant Basin": "Israel",

    # Canada
    "offshore Newfoundland": "Canada",
    "Newfoundland offshore": "Canada",
    "offshore Labrador": "Canada",
    "Jeanne d'Arc Basin": "Canada",
    "Flemish Pass": "Canada",
    "Grand Banks": "Canada",
    "offshore Canada": "Canada",
    "Terra Nova field": "Canada",
    "White Rose field": "Canada",
    "Hebron field": "Canada",
    "Hibernia field": "Canada",
    "Bay du Nord": "Canada",

    # Falklands
    "Falkland Islands": "Falkland Islands",
    "Sea Lion field": "Falkland Islands",
    "Sea Lion Field": "Falkland Islands",

    # Azerbaijan / Caspian
    "Caspian Sea": None,  # ambiguous
    "offshore Azerbaijan": "Azerbaijan",
    "Azeri-Chirag-Gunashli": "Azerbaijan",
    "ACG field": "Azerbaijan",
    "Shah Deniz": "Azerbaijan",

    # Russia
    "offshore Russia": "Russia",
    "Sakhalin": "Russia",
    "Arctic Russia": "Russia",
    "Kara Sea": "Russia",
    "Pechora Sea": "Russia",

    # Argentina
    "offshore Argentina": "Argentina",
    "Vaca Muerta offshore": "Argentina",

    # Namibia
    "offshore Namibia": "Namibia",
    "Orange Basin": "Namibia",
    "Orange basin": "Namibia",
    "Venus field": "Namibia",
    "Graff field": "Namibia",
    "Jonker field": "Namibia",
    "Venus discovery": "Namibia",

    # South Africa
    "offshore South Africa": "South Africa",
    "Brulpadda": "South Africa",
    "Luiperd": "South Africa",

    # Equatorial Guinea / Gabon / Congo
    "offshore Equatorial Guinea": "Equatorial Guinea",
    "offshore Gabon": "Gabon",
    "offshore Congo": "Congo",
    "offshore Cameroon": "Cameroon",

    # Trinidad
    "offshore Trinidad": "Trinidad and Tobago",
    "Trinidad offshore": "Trinidad and Tobago",
    "offshore Trinidad and Tobago": "Trinidad and Tobago",

    # Libya
    "offshore Libya": "Libya",

    # Ivory Coast
    "offshore Ivory Coast": "Ivory Coast",
    "offshore Côte d'Ivoire": "Ivory Coast",
    "Baleine field": "Ivory Coast",
    "Baleine Field": "Ivory Coast",

    # New regions
    "offshore Philippines": "Philippines",
    "offshore Peru": "Peru",
    "offshore Colombia": "Colombia",
    "offshore Venezuela": "Venezuela",
    "offshore Tanzania": "Tanzania",
    "offshore Kenya": "Kenya",
    "offshore Algeria": "Algeria",
    "offshore New Zealand": "New Zealand",
    "offshore Papua New Guinea": "Papua New Guinea",
    "offshore Brunei": "Brunei",
    "offshore Myanmar": "Myanmar",
    "offshore Bangladesh": "Bangladesh",
    "offshore Chile": "Chile",
    "offshore Ecuador": "Ecuador",
    "offshore Pakistan": "Pakistan",
    "offshore Timor-Leste": "Timor-Leste",
    "Timor-Leste offshore": "Timor-Leste",
    "Timor Leste": "Timor-Leste",
    "Timor Gap": "Timor-Leste",
    "Greater Sunrise": "Timor-Leste",
    "offshore South Sudan": "South Sudan",
}

# ---- Country name aliases (lowercase → standard name) -----------------

COUNTRY_ALIASES = {
    # USA
    "united states": "USA",
    "united states of america": "USA",
    "us": "USA",
    "u.s.": "USA",
    "u.s.a.": "USA",
    "america": "USA",

    # UK
    "united kingdom": "UK",
    "britain": "UK",
    "great britain": "UK",
    "england": "UK",
    "scotland": "UK",

    # UAE
    "united arab emirates": "UAE",
    "u.a.e.": "UAE",
    "emirates": "UAE",

    # Ivory Coast
    "côte d'ivoire": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
    "côte d ivoire": "Ivory Coast",
    "cote divoire": "Ivory Coast",

    # Russia
    "russian federation": "Russia",

    # South Korea
    "korea": "South Korea",
    "republic of korea": "South Korea",

    # Congo
    "republic of congo": "Congo",
    "republic of the congo": "Congo",
    "congo-brazzaville": "Congo",
    "congo brazzaville": "Congo",
    "drc": "Congo",
    "democratic republic of congo": "Congo",
    "democratic republic of the congo": "Congo",

    # Trinidad and Tobago
    "trinidad": "Trinidad and Tobago",
    "trinidad & tobago": "Trinidad and Tobago",

    # Equatorial Guinea
    "eq guinea": "Equatorial Guinea",
    "eq. guinea": "Equatorial Guinea",

    # Saudi Arabia
    "saudi": "Saudi Arabia",
    "ksa": "Saudi Arabia",

    # Iran
    "islamic republic of iran": "Iran",

    # Netherlands
    "holland": "Netherlands",
    "the netherlands": "Netherlands",

    # Vietnam
    "viet nam": "Vietnam",

    # East Timor
    "east timor": "Timor-Leste",
    "timor leste": "Timor-Leste",

    # Myanmar
    "burma": "Myanmar",

    # Brunei
    "brunei darussalam": "Brunei",

    # Falklands
    "falklands": "Falkland Islands",
    "malvinas": "Falkland Islands",
    "islas malvinas": "Falkland Islands",

    # Papua New Guinea
    "png": "Papua New Guinea",

    # Philippines
    "the philippines": "Philippines",

    # Turkey
    "türkiye": "Turkey",
    "turkiye": "Turkey",

    # Venezuela
    "venezuela": "Venezuela",
}

# ---- FPSO-specific context patterns for disambiguation -----------------
# When a basin/sea is ambiguous (None in REGION_TO_COUNTRY), use these
# adjacent-country patterns to resolve.

AMBIGUOUS_REGION_CONTEXT = {
    "North Sea": [
        ("Norway", ["norway", "norwegian", "statoil", "equinor", "aker", "oslo", "stavanger", "bergen", "deepocean", "solstad", "subsea 7", "akersolutions", "akersolutions", "vår energi", "var energi", "dof", "odegaard", "aibel", "kværner", "kvaerner", "agr", "petroleum safety authority", "havtil"]),
        ("UK", ["uk", "britain", "british", "united kingdom", "scotland", "scottish", "aberdeen", "london", "bp", "shell", "enermech", "petrofac", "wood group", "wood plc", "worley", "apache", "north sea transition", "serica", "harbour energy", "ithaca", "enquest", "premier oil", "rockhopper", "taqa", "cnooc international", "ineos", "spirit energy", "neo energy", "waldorf", "noc", "petrodec", "respectme"]),
        ("Denmark", ["denmark", "danish", "esbjerg", "maersk", "totalenergies denmark", "blue nord", "hejre", "tyra", "dan field", "halfdan", "gorm"]),
        ("Netherlands", ["netherlands", "dutch", "holland", "rotterdam", "amsterdam", "one-dyas", "kistos", "tullip oil", "dana petroleum", "nam", "wintershall noordzee"]),
    ],
    "Persian Gulf": [
        ("Qatar", ["qatar", "qatari", "doha", "qatarenergy", "north field"]),
        ("UAE", ["uae", "emirates", "emirati", "abu dhabi", "dubai", "adnoc", "sharjah"]),
        ("Saudi Arabia", ["saudi", "saudi arabia", "aramco", "dhahran", "riyadh"]),
        ("Kuwait", ["kuwait", "kuwaiti", "kpc", "kuwait oil"]),
        ("Iran", ["iran", "iranian", "nioc", "tehran", "south pars"]),
        ("Bahrain", ["bahrain", "bahraini", "bapco", "manama"]),
        ("Oman", ["oman", "omani", "muscat", "pdo"]),
        ("Iraq", ["iraq", "iraqi", "basra", "baghdad"]),
    ],
    "South China Sea": [
        ("Malaysia", ["malaysia", "malaysian", "petronas", "kuala lumpur", "sarawak", "sabah"]),
        ("Vietnam", ["vietnam", "vietnamese", "petrovietnam", "hanoi", "ho chi minh"]),
        ("China", ["china", "chinese", "cnoc", "cnooc", "beijing", "shanghai", "bohai"]),
        ("Indonesia", ["indonesia", "indonesian", "pertamina", "jakarta", "natuna"]),
        ("Brunei", ["brunei", "brunei darussalam", "bandar seri begawan"]),
        ("Philippines", ["philippines", "philippine", "filipino", "manila", "reed bank", "spratly"]),
    ],
    "Caspian Sea": [
        ("Azerbaijan", ["azerbaijan", "azeri", "baku", "socar", "shah deniz", "acg"]),
        ("Kazakhstan", ["kazakhstan", "kazakh", "kazmunaigas", "aktau", "atyrau", "kashagan"]),
        ("Russia", ["russia", "russian", "lukoil", "rosneft", "astrakhan", "makhachkala"]),
        ("Turkmenistan", ["turkmenistan", "turkmen", "ashgabat"]),
        ("Iran", ["iran", "iranian", "nioc", "tehran"]),
    ],
    "Arabian Gulf": [
        ("Qatar", ["qatar", "qatari", "doha", "qatarenergy"]),
        ("UAE", ["uae", "emirates", "abu dhabi", "dubai", "adnoc"]),
        ("Saudi Arabia", ["saudi", "aramco", "dhahran"]),
        ("Kuwait", ["kuwait", "kuwaiti"]),
        ("Bahrain", ["bahrain", "bahraini"]),
        ("Oman", ["oman", "omani"]),
        ("Iran", ["iran", "iranian"]),
        ("Iraq", ["iraq", "iraqi"]),
    ],
    "Gulf of Mexico": [
        ("USA", ["usa", "us", "united states", "american", "houston", "gulf coast", "bureau of ocean", "boem", "louisiana", "texas", "new orleans", "gulf of america"]),
        ("Mexico", ["mexico", "mexican", "pemex", "ciudad del carmen", "campeche", "veracruz", "tamaulipas", "tabasco"]),
    ],
}

# ---- Normalize terms list ----------------------------------------------
# Terms that should map to a country when they appear without explicit
# country name but are unambiguously tied to one country.

UNIQUE_FIELD_OWNER = {
    # Operator-owned fields that unambiguously point to one country
    "John Agyekum Kufuor": "Ghana",  # JAK field
    "Liza": "Guyana",
    "Payara": "Guyana",
    "Yellowtail": "Guyana",
    "Uaru": "Guyana",
    "Whiptail": "Guyana",
    "Hammerhead": "Guyana",
    "Eridu": "Iraq",
    "Buzios": "Brazil",
    "Mero": "Brazil",
    "Marlim": "Brazil",
    "Tupi": "Brazil",
    "Sépia": "Brazil",
    "Sepia": "Brazil",
    "Atapu": "Brazil",
    "Itapu": "Brazil",
    "Sergipe": "Brazil",
    "Bacalhau": "Brazil",
    "Peregrino": "Brazil",
    "Raia": "Brazil",
    "Roncador": "Brazil",
    "Jubarte": "Brazil",
    "Carcara": "Brazil",
    "Berbigão": "Brazil",
    "Berbigao": "Brazil",
    "Sururu": "Brazil",
    "Libra": "Brazil",
    "Franco": "Brazil",
    "Lapa": "Brazil",
    "Sépia Leste": "Brazil",
    "Karoon": "Brazil",
    "Who Dat": "USA",
    "Cascade": "USA",
    "Chinook": "USA",
    "Tahiti": "USA",
    "Atlantis": "USA",
    "Thunder Horse": "USA",
    "Mad Dog": "USA",
    "Argos": "USA",
    "Shenzi": "USA",
    "Stones": "USA",
    "Vito": "USA",
    "Anchor": "USA",
    "King's Quay": "USA",
    "Salamanca": "USA",
    "Trion": "Mexico",
    "Zama": "Mexico",
    "Johan Castberg": "Norway",
    "Johan Sverdrup": "Norway",
    "Aasta Hansteen": "Norway",
    "Asgard": "Norway",
    "Snorre": "Norway",
    "Oseberg": "Norway",
    "Troll": "Norway",
    "Grane": "Norway",
    "Goliat": "Norway",
    "Heidrun": "Norway",
    "Njord": "Norway",
    "Skarv": "Norway",
    "Norne": "Norway",
    "Draugen": "Norway",
    "Alvheim": "Norway",
    "Balder": "Norway",
    "Ringhorne": "Norway",
    "Jotun": "Norway",
    "Martin Linge": "Norway",
    "Solveig": "Norway",
    "Edvard Grieg": "Norway",
    "Ivar Aasen": "Norway",
    "Gina Krog": "Norway",
    "Valhall": "Norway",
    "Ekofisk": "Norway",
    "Eldfisk": "Norway",
    "Tambar": "Norway",
    "Ula": "Norway",
    "Yme": "Norway",
    "Knarr": "Norway",
    "Dvalin": "Norway",
    "Breidablikk": "Norway",
    "Nova": "Norway",
    "Mikkel": "Norway",
    "Morvin": "Norway",
    "Alve": "Norway",
    "Marulk": "Norway",
    "Kristin": "Norway",
    "Tyrihans": "Norway",
    "Ormen Lange": "Norway",
    "Rosebank": "UK",
    "Cambo": "UK",
    "Clair": "UK",
    "Schiehallion": "UK",
    "Foinaven": "UK",
    "Lancaster": "UK",
    "Culzean": "UK",
    "Mariner": "UK",
    "Buzzard": "UK",
    "Captain": "UK",
    "Cygnus": "UK",
    "Bressay": "UK",
    "Bentley": "UK",
    "Kraken": "UK",
    "Catcher": "UK",
    "Golden Eagle": "UK",
    "Penguins": "UK",
    "Glen Lyon": "UK",
    "Quad 204": "UK",
    "Gannet": "UK",
    "Harding": "UK",
    "Andrew": "UK",
    "Beryl": "UK",
    "Alba": "UK",
    "Britannia": "UK",
    "Elgin": "UK",
    "Franklin": "UK",
    "Shearwater": "UK",
    "Jasmine": "UK",
    "Galia": "UK",
    "Barra": "UK",
    "Golfinho": "Brazil",
    "Areawhite": "Brazil",
    "Papa Terra": "Brazil",
    "Tartaruga": "Brazil",
    "Tartaruga Verde": "Brazil",
    "Espadarte": "Brazil",
    "Baúna": "Brazil",
    "Bauna": "Brazil",
    "Piracucá": "Brazil",
    "Piracuca": "Brazil",
    "Frade": "Brazil",
    "Polvo": "Brazil",
    "Tubarão": "Brazil",
    "Tubarao": "Brazil",
    "Garoupa": "Brazil",
    "Enchova": "Brazil",
    "Albacora": "Brazil",
    "Albacora Leste": "Brazil",
    "Caratinga": "Brazil",
    "Piranema": "Brazil",
    "Piranha": "Brazil",
    "Catuá": "Brazil",
    "Catua": "Brazil",
    "Canapu": "Brazil",
    "Urugua": "Brazil",
    "Tambau": "Brazil",
    "Tambauzinho": "Brazil",
    "Sapinhoá": "Brazil",
    "Sapinhoa": "Brazil",
    "Guará": "Brazil",
    "Guara": "Brazil",
    "Lula": "Brazil",
    "Lula NE": "Brazil",
    "Iracema": "Brazil",
    "Iara": "Brazil",
    "Lapa SW": "Brazil",
    "Sul de Lula": "Brazil",
    "Sul de Tupi": "Brazil",
    "Norte de Tupi": "Brazil",
    "Norte de Lula": "Brazil",
    "Florim": "Brazil",
    "Lara": "Brazil",
    "Entorno de Iara": "Brazil",
    "Uirapuru": "Brazil",
    "Tartaruga Mestiça": "Brazil",
    "Tartaruga Mestica": "Brazil",
    "Aram": "Brazil",
    "Bumerangue": "Brazil",
    "Formento": "Brazil",
    "Agulha": "Brazil",
    "Biguá": "Brazil",
    "Bigua": "Brazil",
    "Cedro": "Brazil",
    "Jatuá": "Brazil",
    "Jatua": "Brazil",
    "Mirim": "Brazil",
    "Badejo": "Brazil",
    "Bicudo": "Brazil",
    "Cherne": "Brazil",
    "Corvina": "Brazil",
    "Maromba": "Brazil",
    "Namorado": "Brazil",
    "Pampo": "Brazil",
    "Trilha": "Brazil",
    "Voador": "Brazil",
    "Xerelete": "Brazil",
    "Xaréu": "Brazil",
    "Xareu": "Brazil",
    "Barracuda": "Brazil",
    "Dia": "Brazil",
    "Apiaká": "Brazil",
    "Apiaka": "Brazil",
    "Tracajá": "Brazil",
    "Tracaja": "Brazil",
    "Cuiabá": "Brazil",
    "Cuiaba": "Brazil",
    "Abaré": "Brazil",
    "Abare": "Brazil",
    "Pirarucu": "Brazil",
    "Maple": "Brazil",
    "Cajá": "Brazil",
    "Caja": "Brazil",
    "Pitangola": "Brazil",
    "Wahoo": "Brazil",
    "Tambaqui": "Brazil",
    "Curimatá": "Brazil",
    "Curimata": "Brazil",
    "Camarão": "Brazil",
    "Camarau00e3o": "Brazil",
    "Pintado": "Brazil",
    "Pirambu": "Brazil",
    "Jandaia": "Brazil",
    "Azulão": "Brazil",
    "Azulao": "Brazil",
    "Poraquê": "Brazil",
    "Poraque": "Brazil",
    "Tucano": "Brazil",
    "Jacuípe": "Brazil",
    "Jacuipe": "Brazil",
    "Manati": "Brazil",
    "Siri": "Brazil",
    "Caxaréu": "Brazil",
    "Caxareu": "Brazil",
    "Aruanã": "Brazil",
    "Aruana": "Brazil",
    "Oliva": "Brazil",
    "Bagre": "Brazil",
    "Paru": "Brazil",
    "Dourado": "Brazil",
    "Linguado": "Brazil",
    "Anequim": "Brazil",
    "Bonito": "Brazil",
    "Camurim": "Brazil",
    "Camorim": "Brazil",
    "Congro": "Brazil",
    "Corvina": "Brazil",
    "Dentão": "Brazil",
    "Dentao": "Brazil",
    "Malhado": "Brazil",
    "Marlim Azul": "Brazil",
    "Marlim Leste": "Brazil",
    "Marimbá": "Brazil",
    "Marimba": "Brazil",
    "Piraúna": "Brazil",
    "Pirauna": "Brazil",
    "Vermelho": "Brazil",
    "Viola": "Brazil",
    "Bijupirá": "Brazil",
    "Bijupira": "Brazil",
    "Salema": "Brazil",
    "Sauá": "Brazil",
    "Saua": "Brazil",
}

# ---- Company / Operator → Country hints -------------------------------
# When a national oil company or operator is mentioned, strongly suggests
# deployment country. Used as Priority 1.5 (after FPSO name, before region).

OPERATOR_COUNTRY = {
    "Petrobras": "Brazil",
    "Petronas": "Malaysia",
    "Petrovietnam": "Vietnam",
    "Pertamina": "Indonesia",
    "PetroSA": "South Africa",
    "Pemex": "Mexico",
    "PDVSA": "Venezuela",
    "YPF": "Argentina",
    "Ecopetrol": "Colombia",
    "PetroPeru": "Peru",
    "Sonangol": "Angola",
    "NNPC": "Nigeria",
    "Nigerian National Petroleum": "Nigeria",
    "GNPC": "Ghana",
    "Ghana National Petroleum": "Ghana",
    "Petroci": "Ivory Coast",
    "SNH": "Cameroon",
    "Societe Nationale des Hydrocarbures": "Cameroon",
    "TPAO": "Turkey",
    "Turkish Petroleum": "Turkey",
    "Energean": "Israel",
    "Energean Power": "Israel",
    "EGPC": "Egypt",
    "Egyptian General Petroleum": "Egypt",
    "EGAS": "Egypt",
    "NOC Libya": "Libya",
    "National Oil Corporation Libya": "Libya",
    "Sonatrach": "Algeria",
    "INPEX": "Australia",  # Japanese operator, but major Australian presence
    "Santos": "Australia",
    "Woodside": "Australia",
    "BHP": "Australia",
    "Tullow": "Ghana",
    "Kosmos Energy": "Ghana",
    "BW Offshore": "Norway",
    "Aker BP": "Norway",
    "Aker Solutions": "Norway",
    "Equinor": "Norway",
    "Statoil": "Norway",
    "Vår Energi": "Norway",
    "Var Energi": "Norway",
    "Wintershall Dea": "Norway",
    "Aker Energy": "Norway",
    "DNO": "Norway",
    "Lundin": "Norway",
    "Spirit Energy": "UK",
    "Harbour Energy": "UK",
    "Ithaca Energy": "UK",
    "EnQuest": "UK",
    "Premier Oil": "UK",
    "Rockhopper": "UK",
    "Serica Energy": "UK",
    "Neptune Energy": "UK",
    "Cairn Energy": "UK",
    "CNOOC": "China",
    "CNPC": "China",
    "Sinopec": "China",
    "PetroChina": "China",
    "ONGC": "India",
    "Oil India": "India",
    "GAIL": "India",
    "QatarEnergy": "Qatar",
    "Qatar Petroleum": "Qatar",
    "Qatargas": "Qatar",
    "ADNOC": "UAE",
    "Saudi Aramco": "Saudi Arabia",
    "Aramco": "Saudi Arabia",
    "KPC": "Kuwait",
    "Kuwait Oil Company": "Kuwait",
    "BAPCO": "Bahrain",
    "NIOC": "Iran",
    "National Iranian Oil": "Iran",
    "SOCAR": "Azerbaijan",
    "KazMunayGas": "Kazakhstan",
    "Rosneft": "Russia",
    "Lukoil": "Russia",
    "Gazprom": "Russia",
    "Novatek": "Russia",
    "PetroBangla": "Bangladesh",
    "Bumi Armada": "Malaysia",
    "MISC": "Malaysia",
    "Tanjung Offshore": "Malaysia",
    "Yinson": "Malaysia",
    "Sapura Energy": "Malaysia",
    "SBM Offshore": None,  # Dutch contractor, works globally
    "MODEC": None,   # Japanese contractor, works globally
    # "BW Offshore" handled above as Norway — duplicate removed
    "Bluewater": None,  # Dutch contractor
    "Teekay": None,   # Canadian contractor, works globally
    "Altera": None,   # Global contractor
    "Seatrium": None,  # Singapore shipyard
    "Sembcorp": None,  # Singapore shipyard
    "Keppel": None,  # Singapore shipyard
    "Hanwha Ocean": None,  # Korean shipyard
    "Samsung Heavy": None,  # Korean shipyard
    "Hyundai Heavy": None,  # Korean shipyard
    "COSCO": None,  # Chinese shipyard
    "BOMESC": None,  # Chinese contractor
    "Wison": None,  # Chinese contractor
    "Titan Wind Energy": None,  # Chinese manufacturer
    "Eni": None,  # Italian, global operations
    "TotalEnergies": None,  # French, global operations
    "Total": None,  # French, global operations
    "Shell": None,  # Dutch/UK, global
    "BP": None,  # UK, global
    "ExxonMobil": None,  # USA, global
    "Exxon": None,  # USA, global
    "Chevron": None,  # USA, global
    "ConocoPhillips": None,  # USA, global
    "Hess": None,  # USA, global
    "Murphy Oil": None,  # USA, global
    "Apache": None,  # USA, global
    "Kosmos": None,  # USA, global but mostly Ghana
}

# ---- Adjective forms of countries → standard name ---------------------

ADJECTIVAL_COUNTRY = {
    "Brazilian": "Brazil",
    "Guyanese": "Guyana",
    "Angolan": "Angola",
    "Nigerian": "Nigeria",
    "Norwegian": "Norway",
    "British": "UK",
    "Chinese": "China",
    "Malaysian": "Malaysia",
    "Indonesian": "Indonesia",
    "Australian": "Australia",
    "Ghanaian": "Ghana",
    "Senegalese": "Senegal",
    "Mauritanian": "Mauritania",
    "Indian": "India",
    "American": "USA",
    "Canadian": "Canada",
    "Mexican": "Mexico",
    "Vietnamese": "Vietnam",
    "Thai": "Thailand",
    "Qatari": "Qatar",
    "Emirati": "UAE",
    "Saudi": "Saudi Arabia",
    "Mozambican": "Mozambique",
    "Egyptian": "Egypt",
    "Libyan": "Libya",
    "Russian": "Russia",
    "Azerbaijani": "Azerbaijan",
    "Kazakh": "Kazakhstan",
    "Singaporean": "Singapore",
    "Japanese": "Japan",
    "Dutch": "Netherlands",
    "Danish": "Denmark",
    "Namibian": "Namibia",
    "Israeli": "Israel",
    "Cypriot": "Cyprus",
    "Turkish": "Turkey",
    "Iraqi": "Iraq",
    "Iranian": "Iran",
    "Kuwaiti": "Kuwait",
    "Omani": "Oman",
    "Bahraini": "Bahrain",
    "Yemeni": "Yemen",
    "Argentinian": "Argentina",
    "Argentine": "Argentina",
    "Peruvian": "Peru",
    "Colombian": "Colombia",
    "Venezuelan": "Venezuela",
    "Filipino": "Philippines",
    "Philippine": "Philippines",
    "Tanzanian": "Tanzania",
    "Kenyan": "Kenya",
    "Algerian": "Algeria",
    "Tunisian": "Tunisia",
    "Moroccan": "Morocco",
    "Spanish": "Spain",
    "French": "France",
    "Italian": "Italy",
    "Greek": "Greece",
    "Portuguese": "Portugal",
    "German": "Germany",
    "Belgian": "Belgium",
    "Polish": "Poland",
    "Romanian": "Romania",
    "Bulgarian": "Bulgaria",
    "Croatian": "Croatia",
    "Maltese": "Malta",
    "New Zealand": "New Zealand",
    "Papua New Guinean": "Papua New Guinea",
    "Bangladeshi": "Bangladesh",
    "Pakistani": "Pakistan",
    "Chilean": "Chile",
    "Ecuadorian": "Ecuador",
    "Uruguayan": "Uruguay",
    "Sri Lankan": "Sri Lanka",
    "Bruneian": "Brunei",
    "Myanma": "Myanmar",
    "Sudanese": "Sudan",
    "Somali": "Somalia",
    "South Sudanese": "South Sudan",
    "Timorese": "Timor-Leste",
    "Falkland": "Falkland Islands",
    "Bengali": "Bangladesh",
    "Congolese": "Congo",
    "Gabonese": "Gabon",
    "Cameroonian": "Cameroon",
    "Trinidadian": "Trinidad and Tobago",
    "Surinamese": "Suriname",
    "Equatoguinean": "Equatorial Guinea",
}

# ---- Regional patterns that point to specific countries ---------------

REGIONAL_PATTERNS = {
    "Eastern Mediterranean": [
        ("Israel", ["israel", "israeli", "energean", "leviathan", "tamar", "karish", "tanin"]),
        ("Cyprus", ["cyprus", "cypriot", "aphrodite", "calypso", "glaucus"]),
        ("Egypt", ["egypt", "egyptian", "zohr", "noor", "west delta", "edco", "idku"]),
        ("Turkey", ["turkey", "turkish", "sakarya", "tuna-1", "fatih"]),
        ("Greece", ["greece", "greek", "ioannina", "patraikos"]),
    ],
    "West Africa": [
        ("Nigeria", ["nigeria", "nigerian", "nnpc", "bonga", "egina", "akpo", "erha"]),
        ("Angola", ["angola", "angolan", "sonangol", "girassol", "dalia", "plutonio", "pazflor"]),
        ("Ghana", ["ghana", "ghanaian", "jubilee", "ten field", "pecan", "tullow"]),
        ("Ivory Coast", ["ivory coast", "côte d'ivoire", "cote d'ivoire", "baleine"]),
        ("Senegal", ["senegal", "senegalese", "sangomar", "yaram"]),
        ("Mauritania", ["mauritania", "mauritanian", "tortue", "ahmeyim", "birallah"]),
        ("Equatorial Guinea", ["equatorial guinea", "equatoguinean", "bubi", "alba", "zafiro"]),
        ("Gabon", ["gabon", "gabonese", "likouf", "bw adolo"]),
        ("Congo", ["congo", "congolese", "moho", "nkossa", "likouala"]),
        ("Cameroon", ["cameroon", "cameroonian", "kome", "logbaba"]),
    ],
    "Africa": [
        ("Nigeria", ["nigeria", "nigerian", "bonga", "egina", "akpo", "us an", "nnpc"]),
        ("Angola", ["angola", "angolan", "sonangol", "girassol", "dalia", "kaombo", "clov"]),
        ("Ghana", ["ghana", "ghanaian", "jubilee", "tullow", "kosmos"]),
        ("Egypt", ["egypt", "egyptian", "zohr", "west delta", "edco"]),
        ("Mozambique", ["mozambique", "mozambican", "coral", "rovuma", "enalhta"]),
        ("Senegal", ["senegal", "senegalese", "sangomar"]),
        ("Mauritania", ["mauritania", "mauritanian", "tortue"]),
        ("Equatorial Guinea", ["equatorial guinea", "zafiro"]),
        ("Gabon", ["gabon", "gabonese"]),
        ("Congo", ["congo", "congolese", "moho", "nkossa"]),
        ("Ivory Coast", ["ivory coast", "côte d'ivoire", "baleine"]),
        ("Libya", ["libya", "libyan", "farwah", "al jurf"]),
        ("Algeria", ["algeria", "algerian", "sonatrach"]),
        ("Namibia", ["namibia", "namibian", "venus", "graff", "orange basin"]),
        ("South Africa", ["south africa", "brulpadda", "luiperd"]),
        ("Cameroon", ["cameroon", "cameroonian"]),
    ],
}

# ---- Add region names to REGION_TO_COUNTRY ----------------------------
# (these are added programmatically below)

# Extend REGION_TO_COUNTRY with additional patterns
REGION_TO_COUNTRY_EXTRA = {
    "Eastern Mediterranean": None,
    "West Africa": None,
}
# Many FPSO vessels are deployed to specific countries

FPSO_COUNTRY = {
    # Brazil-deployed FPSOs
    "FPSO Cidade de Angra dos Reis": "Brazil",
    "FPSO Cidade de Ilhabela": "Brazil",
    "FPSO Cidade de Itaguaí": "Brazil",
    "FPSO Cidade de Itajaí": "Brazil",
    "FPSO Cidade de Mangaratiba": "Brazil",
    "FPSO Cidade de Maricá": "Brazil",
    "FPSO Cidade de Niterói": "Brazil",
    "FPSO Cidade de Paraty": "Brazil",
    "FPSO Cidade de Santos": "Brazil",
    "FPSO Cidade de São Mateus": "Brazil",
    "FPSO Cidade de São Paulo": "Brazil",
    "FPSO Cidade de São Vicente": "Brazil",
    "FPSO Cidade de Saquarema": "Brazil",
    "FPSO Cidade de Caraguatatuba": "Brazil",
    "FPSO Cidade de Ubatuba": "Brazil",
    "FPSO Cidade de Anchieta": "Brazil",
    "FPSO Cidade de Guarujá": "Brazil",
    "FPSO P-66": "Brazil",
    "FPSO P-67": "Brazil",
    "FPSO P-68": "Brazil",
    "FPSO P-69": "Brazil",
    "FPSO P-70": "Brazil",
    "FPSO P-71": "Brazil",
    "FPSO P-72": "Brazil",
    "FPSO P-73": "Brazil",
    "FPSO P-74": "Brazil",
    "FPSO P-75": "Brazil",
    "FPSO P-76": "Brazil",
    "FPSO P-77": "Brazil",
    "FPSO P-78": "Brazil",
    "FPSO P-79": "Brazil",
    "FPSO P-80": "Brazil",
    "FPSO P-81": "Brazil",
    "FPSO P-82": "Brazil",
    "FPSO P-83": "Brazil",
    "FPSO P-84": "Brazil",
    "FPSO P-85": "Brazil",
    "FPSO P-86": "Brazil",
    "FPSO P-87": "Brazil",
    "FPSO P-88": "Brazil",
    "FPSO Almirante Barroso": "Brazil",
    "FPSO Alexandre de Gusmão": "Brazil",
    "FPSO Duque de Caxias": "Brazil",
    "FPSO Anita Garibaldi": "Brazil",
    "FPSO Anna Nery": "Brazil",
    "FPSO Maria Quitéria": "Brazil",
    "FPSO Marechal Duque de Caxias": "Brazil",
    "FPSO Guanabara": "Brazil",
    "FPSO Espirito Santo": "Brazil",
    "FPSO Rio de Janeiro": "Brazil",
    "FPSO Bahia": "Brazil",
    "FPSO Marlim": "Brazil",
    "FPSO Marlim Sul": "Brazil",
    "FPSO Capixaba": "Brazil",
    "FPSO JK": "Brazil",
    "FPSO P-57": "Brazil",
    "FPSO P-58": "Brazil",
    "FPSO P-62": "Brazil",
    "FPSO P-63": "Brazil",
    "FPSO P-54": "Brazil",
    "FPSO P-55": "Brazil",
    "FPSO P-50": "Brazil",
    "FPSO P-52": "Brazil",
    "FPSO P-53": "Brazil",
    "FPSO P-56": "Brazil",
    "FPSO P-48": "Brazil",
    "FPSO P-43": "Brazil",
    "FPSO P-40": "Brazil",
    "FPSO P-38": "Brazil",
    "FPSO P-37": "Brazil",
    "FPSO P-35": "Brazil",
    "FPSO P-34": "Brazil",
    "FPSO P-33": "Brazil",
    "FPSO P-32": "Brazil",
    "FPSO P-31": "Brazil",
    "FPSO OSX-1": "Brazil",
    "FPSO OSX-2": "Brazil",
    "FPSO OSX-3": "Brazil",
    "FPSO Polvo": "Brazil",
    "FPSO Petrojarl I": "Brazil",
    "FPSO Petrojarl Cidade de Rio das Ostras": "Brazil",
    "FPSO Fluminense": "Brazil",
    "FPSO Cidade do Rio de Janeiro": "Brazil",

    # Guyana
    "FPSO Liza Destiny": "Guyana",
    "FPSO Liza Unity": "Guyana",
    "FPSO Prosperity": "Guyana",
    "FPSO One Guyana": "Guyana",
    "FPSO Errea Wittu": "Guyana",
    "FPSO Jaguar": "Guyana",

    # Angola
    "FPSO Greater Plutonio": "Angola",
    "FPSO Plutonio": "Angola",
    "FPSO Kizomba A": "Angola",
    "FPSO Kizomba B": "Angola",
    "FPSO Kizomba C": "Angola",
    "FPSO Kizomba D": "Angola",
    "FPSO Saxi Batuque": "Angola",
    "FPSO Mondo": "Angola",
    "FPSO N'Goma": "Angola",
    "FPSO Ngoma": "Angola",
    "FPSO PSVM": "Angola",
    "FPSO Gimboa": "Angola",
    "FPSO Gimbo": "Angola",
    "FPSO Dalia": "Angola",
    "FPSO Girassol": "Angola",
    "FPSO Hungo": "Angola",
    "FPSO Kissanje": "Angola",
    "FPSO Mundinbar": "Angola",
    "FPSO Palanca": "Angola",
    "FPSO Sanha": "Angola",
    "FPSO Serpentina": "Angola",
    "FPSO Xikomba": "Angola",
    "FPSO Zafiro": "Angola",
    "FPSO Agogo": "Angola",
    "FPSO Ndungu": "Angola",
    "FPSO Chissonga": "Angola",
    "FPSO Kaombo Norte": "Angola",
    "FPSO Kaombo Sul": "Angola",
    "FPSO CLOV": "Angola",
    "FPSO Pazflor": "Angola",

    # Nigeria
    "FPSO Bonga": "Nigeria",
    "FPSO Bonga North": "Nigeria",
    "FPSO Bonga South West": "Nigeria",
    "FPSO Erha": "Nigeria",
    "FPSO Agbami": "Nigeria",
    "FPSO Akpo": "Nigeria",
    "FPSO Egina": "Nigeria",
    "FPSO Usan": "Nigeria",
    "FPSO Uge": "Nigeria",
    "FPSO Aparo": "Nigeria",
    "FPSO Bosi": "Nigeria",
    "FPSO Bonga SW": "Nigeria",
    "FPSO Oyo": "Nigeria",
    "FPSO Okwori": "Nigeria",
    "FPSO Ukpokiti": "Nigeria",
    "FPSO Abo": "Nigeria",
    "FPSO Sea Eagle": "Nigeria",
    "FPSO Armada Perdana": "Nigeria",
    "FPSO Mystras": "Nigeria",
    "FPSO Falcon": "Nigeria",
    "FPSO Crystal Sea": "Nigeria",
    "FPSO Trinity Spirit": "Nigeria",
    "FPSO Sendje Berge": "Nigeria",

    # Ghana
    "FPSO Kwame Nkrumah": "Ghana",
    "FPSO John Evans Atta Mills": "Ghana",
    "FPSO John Agyekum Kufuor": "Ghana",

    # Ivory Coast
    "FPSO Baleine": "Ivory Coast",

    # Senegal
    "FPSO Léopold Sédar Senghor": "Senegal",

    # Mauritania
    "FPSO Tortue": "Mauritania",
    "FPSO N'Dour": "Mauritania",

    # Mozambique
    "FPSO Coral Sul": "Mozambique",
    "FPSO Coral Norte": "Mozambique",
    "FPSO Coral": "Mozambique",

    # Equatorial Guinea
    "FPSO Aseng": "Equatorial Guinea",
    "FPSO Zafiro Producer": "Equatorial Guinea",
    "FPSO Serpentina": "Equatorial Guinea",
    "FPSO Ceiba": "Equatorial Guinea",
    "FPSO Okume": "Equatorial Guinea",
    "FPSO Sendje Ceiba": "Equatorial Guinea",

    # Gabon
    "FPSO Likouf": "Gabon",
    "FPSO BW Adolo": "Gabon",

    # Congo
    "FPSO Nkossa": "Congo",
    "FPSO NKossa": "Congo",
    "FPSO Likouala": "Congo",
    "FPSO Moho": "Congo",
    "FPSO Moho Nord": "Congo",
    "FPSO Moho Bilondo": "Congo",
    "FPSO Djambala": "Congo",
    "FPSO Kitina": "Congo",
    "FPSO Mboundi": "Congo",
    "FPSO Azurite": "Congo",
    "FPSO Conkouati": "Congo",
    "FPSO Yanga": "Congo",
    "FPSO Sendje Berge": "Congo",

    # Cameroon
    "FPSO Kome": "Cameroon",
    "FPSO Kome Kribi": "Cameroon",

    # Libya
    "FPSO Al Jurf": "Libya",
    "FPSO Farwah": "Libya",

    # Egypt
    "FPSO West Delta Deep Marine": "Egypt",

    # Norway
    "FPSO Petrojarl I": "Norway",
    "FPSO Petrojarl II": "Norway",
    "FPSO Petrojarl III": "Norway",
    "FPSO Petrojarl IV": "Norway",
    "FPSO Petrojarl Varg": "Norway",
    "FPSO Petrojarl Knarr": "Norway",
    "FPSO Norne": "Norway",
    "FPSO Åsgard A": "Norway",
    "FPSO Asgard A": "Norway",
    "FPSO Skarv": "Norway",
    "FPSO Goliat": "Norway",
    "FPSO Jotun A": "Norway",
    "FPSO Balder": "Norway",
    "FPSO Ringhorne": "Norway",
    "FPSO Varg": "Norway",
    "FPSO Alvheim": "Norway",
    "FPSO Knarr": "Norway",
    "FPSO Njord B": "Norway",
    "FPSO Yme": "Norway",
    "FPSO Heidrun": "Norway",
    "FPSO Haewene Brim": "Norway",
    "FPSO Aoka Mizu": "Norway",
    "FPSO Munin": "Norway",
    "FPSO Sevan Piranema": "Norway",
    "FPSO Voyageur Spirit": "Norway",
    "FPSO Northern Producer": "Norway",
    "FPSO Bleo Holm": "Norway",
    "FPSO EnQuest Producer": "Norway",
    "FPSO Hummingbird": "Norway",

    # UK
    "FPSO Glen Lyon": "UK",
    "FPSO Schiehallion": "UK",
    "FPSO Foinaven": "UK",
    "FPSO Captain": "UK",
    "FPSO Bleo Holm": "UK",
    "FPSO Triton": "UK",
    "FPSO Aoka Mizu": "UK",
    "FPSO Haewene Brim": "UK",
    "FPSO Northern Producer": "UK",
    "FPSO Voyageur Spirit": "UK",
    "FPSO EnQuest Producer": "UK",
    "FPSO Petrojarl Banff": "UK",
    "FPSO Petrojarl Foinaven": "UK",
    "FPSO Sevan Hummingbird": "UK",
    "FPSO Hummingbird Spirit": "UK",
    "FPSO Bluewater": "UK",
    "FPSO Banff": "UK",
    "FPSO Curlew": "UK",
    "FPSO North Sea Producer": "UK",
    "FPSO Anasuria": "UK",
    "FPSO MacCulloch": "UK",
    "FPSO Pierce": "UK",
    "FPSO Seillean": "UK",
    "FPSO Rubie": "UK",
    "FPSO Donan": "UK",
    "FPSO Nan Hai Sheng Li": "UK",

    # China
    "FPSO Nanhai Shengli": "China",
    "FPSO Nanhai Faxian": "China",
    "FPSO Nanhai Kaituo": "China",
    "FPSO Nanhai Fenjin": "China",
    "FPSO Hai Yang Shi You 117": "China",
    "FPSO Hai Yang Shi You 118": "China",
    "FPSO Hai Yang Shi You 119": "China",
    "FPSO Hai Yang Shi You 121": "China",
    "FPSO Hai Yang Shi You 111": "China",
    "FPSO Hai Yang Shi You 112": "China",
    "FPSO Hai Yang Shi You 113": "China",
    "FPSO Hai Yang Shi You 115": "China",
    "FPSO Haiyang Shiyou 117": "China",
    "FPSO Hai Yang Shi You 122": "China",
    "FPSO Bohai Century": "China",
    "FPSO Bohai Mingzhu": "China",
    "FPSO Ming Zhu": "China",
    "FPSO Chang Qing Hao": "China",
    "FPSO Penglai": "China",
    "FPSO Peng Bo": "China",
    "FPSO Hua Zhang": "China",
    "FPSO Nanhai Tiaozhan": "China",
    "FPSO Nan Hai Tiao Zhan": "China",
    "FPSO Lufeng": "China",
    "FPSO Fen Jin Hao": "China",
    "FPSO Ocean 102": "China",
    "FPSO Binh Minh": "China",

    # Australia
    "FPSO Ichthys Venturer": "Australia",
    "FPSO Prelude": "Australia",
    "FPSO Northern Endeavour": "Australia",
    "FPSO Griffin Venture": "Australia",
    "FPSO Jabiru Venture": "Australia",
    "FPSO Challis Venture": "Australia",
    "FPSO Nganhurra": "Australia",
    "FPSO Pyrenees Venture": "Australia",
    "FPSO Stybarrow Venture": "Australia",
    "FPSO Okha": "Australia",
    "FPSO Karratha Spirit": "Australia",
    "FPSO Ningaloo Vision": "Australia",
    "FPSO Four Vanguard": "Australia",
    "FPSO Helix": "Australia",

    # Malaysia
    "FPSO Kikeh": "Malaysia",
    "FPSO MaMPU 1": "Malaysia",
    "FPSO Layang": "Malaysia",
    "FPSO Bunga Kekwa": "Malaysia",
    "FPSO Perintis": "Malaysia",
    "FPSO Puteri Dulang": "Malaysia",
    "FPSO Ruby II": "Malaysia",
    "FPSO Cendor": "Malaysia",
    "FPSO Deep Producer 1": "Malaysia",

    # Indonesia
    "FPSO Belanak": "Indonesia",
    "FPSO Kakap": "Indonesia",
    "FPSO Modec Venture 1": "Indonesia",
    "FPSO Cinta Natomas": "Indonesia",
    "FPSO Gag": "Indonesia",
    "FPSO Karapan": "Indonesia",
    "FPSO Armada Sterling": "Indonesia",
    "FPSO Armada Sterling II": "Indonesia",
    "FPSO Anoa": "Indonesia",

    # Vietnam
    "FPSO Dai Hung": "Vietnam",
    "FPSO Su Tu Den": "Vietnam",
    "FPSO Rang Dong": "Vietnam",
    "FPSO Ruby": "Vietnam",
    "FPSO Ruby II": "Vietnam",
    "FPSO Song Doc": "Vietnam",
    "FPSO PTSC Lam Son": "Vietnam",
    "FPSO Bien Dong": "Vietnam",
    "FPSO TGT": "Vietnam",
    "FPSO Orkid": "Vietnam",
    "FPSO Lewek EMAS": "Vietnam",
    "FPSO Armada TGT": "Vietnam",

    # Thailand
    "FPSO Benchamas Explorer": "Thailand",
    "FPSO Benchamas": "Thailand",
    "FPSO Kinnaree": "Thailand",
    "FPSO Tantawan Explorer": "Thailand",
    "FPSO Nong Yao": "Thailand",
    "FPSO Wassana": "Thailand",

    # India
    "FPSO Armada Sterling": "India",
    "FPSO Armada Sterling II": "India",
    "FPSO Dhirubhai-1": "India",
    "FPSO Platinum Explorer": "India",

    # Qatar
    "FPSO Al Gharrafa": "Qatar",
    "FPSO Al Rayyan": "Qatar",
    "FPSO Al Shaheen": "Qatar",
    "FPSO Al Dhaen": "Qatar",
    "FPSO Al Jasra": "Qatar",

    # UAE
    "FPSO Al Falah": "UAE",
    "FPSO Zakum": "UAE",
    "FPSO Umm Lulu": "UAE",
    "FPSO Satah": "UAE",

    # Saudi Arabia
    "FPSO Safaniya": "Saudi Arabia",
    "FPSO Marjan": "Saudi Arabia",
    "FPSO Zuluf": "Saudi Arabia",
    "FPSO Manifa": "Saudi Arabia",
    "FPSO Berri": "Saudi Arabia",
    "FPSO Abu Safah": "Saudi Arabia",
    "FPSO Karan": "Saudi Arabia",
    "FPSO Ribyan": "Saudi Arabia",

    # Argentina
    "FPSO Argentina": "Argentina",

    # Russia
    "FPSO Piltun": "Russia",
    "FPSO Molikpaq": "Russia",
    "FPSO Sakhalin": "Russia",
    "FPSO Berkut": "Russia",
    "FPSO Orlan": "Russia",

    # Turkey
    "FPSO TPAO": "Turkey",

    # Canada
    "FPSO Terra Nova": "Canada",
    "FPSO SeaRose": "Canada",

    # Israel
    "FPSO Energean Power": "Israel",

    # Singapore (FPSO construction hub — fallback, rarely the deployment country)
    "FPSO Singapore": None,

    # South Korea (FPSO construction hub)
    "FPSO South Korea": None,
}

# Country → ISO 3166-1 alpha-2 code for flag emoji generation
COUNTRY_CODE = {
    "Australia": "AU", "Azerbaijan": "AZ", "Angola": "AO", "Argentina": "AR",
    "Bahrain": "BH", "Brazil": "BR", "Cameroon": "CM", "Canada": "CA",
    "China": "CN", "Congo": "CG", "Cyprus": "CY", "Denmark": "DK",
    "Egypt": "EG", "Equatorial Guinea": "GQ", "Gabon": "GA", "Ghana": "GH",
    "Guyana": "GY", "India": "IN", "Indonesia": "ID", "Iran": "IR",
    "Iraq": "IQ", "Israel": "IL", "Ivory Coast": "CI", "Japan": "JP",
    "Kazakhstan": "KZ", "Kuwait": "KW", "Libya": "LY", "Malaysia": "MY",
    "Mauritania": "MR", "Mexico": "MX", "Mozambique": "MZ", "Namibia": "NA",
    "Netherlands": "NL", "Nigeria": "NG", "Norway": "NO", "Oman": "OM",
    "Qatar": "QA", "Russia": "RU", "Saudi Arabia": "SA", "Senegal": "SN",
    "Singapore": "SG", "South Africa": "ZA", "South Korea": "KR",
    "Suriname": "SR", "Thailand": "TH", "Trinidad and Tobago": "TT",
    "Turkey": "TR", "UAE": "AE", "UK": "GB", "USA": "US",
    "Vietnam": "VN", "Yemen": "YE",
}


def country_to_flag(country):
    """Convert country name to flag emoji. Returns empty string if country is empty or unknown."""
    if not country:
        return ""
    code = COUNTRY_CODE.get(country)
    if not code:
        return ""
    # Regional indicator symbols: U+1F1E6 = 🇦 (A), offset from A is 0x1F1E6
    return chr(ord(code[0]) - ord("A") + 0x1F1E6) + chr(ord(code[1]) - ord("A") + 0x1F1E6)


STATUS_PATTERNS = {
    "Under Construction": [
        "under construction", "being built", "construction",
        "building", "fabrication", "under development",
        "steel cut", "first steel", "keel laying", "hull launch",
        "topsides", "integration", "outfitting", "dry dock",
    ],
    "Delivered": [
        "delivered", "delivery", "completed", "commissioned",
        "first oil", "production start", "operational",
        "in operation", "on stream", "started production",
        "commenced production", "onstation", "on station",
        "sailaway", "sail away", "achieved first oil",
        "producing", "production commenced",
    ],
    "Planned": [
        "planned", "planning", "proposed", "sanctioned",
        "approved", "FEED", "pre-FEED",
        "front-end engineering", "conceptual", "study",
        "tender", "bid", "contract awarded",
        "letter of intent", "LOI", "MoU",
        "memorandum", "agreement signed", "secured contract",
        "won contract", "awarded contract",
    ],
}

# Words that are not real project names even if they follow "FPSO"
GENERIC_WORDS = {
    "the", "a", "an", "for", "and", "with", "new", "first", "latest",
    "project", "vessel", "unit", "platform", "production", "storage",
    "offloading", "of", "in", "at", "to", "is", "on", "as", "by",
    "its", "will", "has", "been", "from", "was", "that", "this",
    "next", "two", "three", "four", "one", "major", "another",
    "floating", "fpso", "be", "it", "or", "second", "third",
}


# Collect unrecognized article titles for manual curation
UNRECOGNIZED_ARTICLES = []


def extract_country(title, summary):
    """
    Multi-priority country extraction for FPSO articles.

    Priority order:
    1. FPSO vessel name → country (most specific)
    1.5. Operator/company name → country (national oil companies)
    2. Unique field name → country
    3. Region/basin/block name → country
    4. Resolve ambiguous regions (including regional patterns like West Africa)
    4.5. Adjectival country forms (Brazilian, Australian, etc.)
    5. Direct country name match (aliases + standard names)
    6. Weighted multi-keyword scoring when multiple countries found
    7. "offshore X" / "X waters" patterns as last resort
    """
    text = f"{title} {summary}"
    text_lower = text.lower()
    title_lower = title.lower()

    # -- Priority 1: FPSO vessel name lookup --
    for fpsov_name, country in FPSO_COUNTRY.items():
        if fpsov_name.lower() in text_lower:
            if country is not None:
                log.debug("  country via FPSO name: %s → %s", fpsov_name, country)
                return country

    # -- Priority 1.5: National oil company / operator → country --
    # Only use operators that are strongly tied to one country (value is not None)
    # Sort by key length so longer (more specific) names match first
    op_keys = sorted(
        [k for k, v in OPERATOR_COUNTRY.items() if v is not None],
        key=len, reverse=True,
    )
    for op_name in op_keys:
        if re.search(rf"\b{re.escape(op_name)}\b", text, re.IGNORECASE):
            country = OPERATOR_COUNTRY[op_name]
            log.debug("  country via operator: %s → %s", op_name, country)
            return country

    # -- Priority 2: Unique field name lookup --
    for field_name, country in UNIQUE_FIELD_OWNER.items():
        if field_name.lower() in text_lower:
            log.debug("  country via field name: %s → %s", field_name, country)
            return country

    # -- Priority 3: Region/basin/block → country --
    # Merge main dict + extras
    all_regions = {**REGION_TO_COUNTRY, **REGION_TO_COUNTRY_EXTRA}
    region_keys = sorted(all_regions.keys(), key=len, reverse=True)
    matched_region = None
    for region in region_keys:
        if region.lower() in text_lower:
            country = all_regions[region]
            if country is not None:
                log.debug("  country via region: %s → %s", region, country)
                return country
            else:
                # Ambiguous region — record and resolve later
                matched_region = region
                break

    # -- Priority 4: Resolve ambiguous regions --
    # First check AMBIGUOUS_REGION_CONTEXT
    if matched_region and matched_region in AMBIGUOUS_REGION_CONTEXT:
        scored = _score_countries(text_lower, title, AMBIGUOUS_REGION_CONTEXT[matched_region])
        if scored:
            country = scored[0][0]
            log.debug("  country via ambiguous region %s + context → %s", matched_region, country)
            return country

    # Then check REGIONAL_PATTERNS (West Africa, Africa, Eastern Mediterranean, etc.)
    for region_name, candidates in REGIONAL_PATTERNS.items():
        if region_name.lower() in text_lower:
            scored = _score_countries(text_lower, title, candidates)
            if scored:
                country = scored[0][0]
                log.debug("  country via regional pattern %s → %s", region_name, country)
                return country

    # -- Priority 4.5: Adjectival country forms --
    # Sort by key length (longest first)
    adj_items = sorted(ADJECTIVAL_COUNTRY.items(), key=lambda x: len(x[0]), reverse=True)
    for adj, country in adj_items:
        if re.search(rf"\b{re.escape(adj)}\b", text, re.IGNORECASE):
            log.debug("  country via adjectival: %s → %s", adj, country)
            return country

    # -- Priority 5: Direct country name match (aliases first, then standard) --
    # Aliases (normalize common variations)
    alias_keys = sorted(COUNTRY_ALIASES.keys(), key=len, reverse=True)
    for alias in alias_keys:
        if re.search(rf"\b{re.escape(alias)}\b", text_lower):
            standard = COUNTRY_ALIASES[alias]
            log.debug("  country via alias: %s → %s", alias, standard)
            return standard

    # Standard country names (multi-match collected for scoring)
    country_hits = _collect_country_hits(text_lower, title)
    if country_hits:
        if len(country_hits) == 1:
            log.debug("  country via direct match: %s", country_hits[0][0])
            return country_hits[0][0]
        else:
            # Multi-match: score and pick best
            best = country_hits[0][0]
            log.debug("  country via multi-match scoring: %s (candidates: %s)",
                      best, [c for c, _ in country_hits])
            return best

    # -- Priority 7: "offshore X" / "X waters" pattern --
    m = re.search(
        r"(?:offshore|off the coast of|waters of|coast of)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})",
        text,
        re.IGNORECASE,
    )
    if m:
        phrase = m.group(1).strip()
        phrase_lower = phrase.lower()
        for alias, standard in COUNTRY_ALIASES.items():
            if phrase_lower == alias or phrase_lower.startswith(alias):
                log.debug("  country via offshore pattern + alias: %s → %s", phrase, standard)
                return standard
        for c in COUNTRY_LIST:
            if phrase_lower == c.lower() or phrase_lower.startswith(c.lower()):
                log.debug("  country via offshore pattern: %s", c)
                return c

    # -- Nothing found --
    log.info("  NO_COUNTRY: %s", title[:100])
    UNRECOGNIZED_ARTICLES.append(title)
    return None


def _score_countries(text_lower, title, candidates):
    """
    Score candidate countries by relevance to the article.
    Returns sorted list of (country, score) tuples, highest first.

    Scoring factors:
    - +3 per mention of the country or its keywords in the title
    - +1 per mention in the body/summary
    - +2 bonus if a keyword appears near "FPSO" (within 50 chars)
    - +1 if a keyword appears near "offshore", "project", or "field"
    """
    title_lower = title.lower()
    scored = []

    for country, keywords in candidates:
        score = 0
        for kw in keywords:
            kw_lower = kw.lower()
            # Title mentions (higher weight)
            score += 3 * len(re.findall(rf"\b{re.escape(kw_lower)}\b", title_lower))
            # Body mentions
            score += 1 * len(re.findall(rf"\b{re.escape(kw_lower)}\b", text_lower))
            # Proximity to FPSO
            fpso_positions = [m.start() for m in re.finditer(r"fpso", text_lower)]
            for pos in fpso_positions:
                window = text_lower[max(0, pos - 80):pos + 80]
                if kw_lower in window:
                    score += 2
            # Proximity to key terms
            for term in ["offshore", "project", "field", "development", "production"]:
                term_positions = [m.start() for m in re.finditer(term, text_lower)]
                for pos in term_positions:
                    window = text_lower[max(0, pos - 60):pos + 60]
                    if kw_lower in window:
                        score += 1
                        break

        if score > 0:
            scored.append((country, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _collect_country_hits(text_lower, title):
    """
    Find all standard country name mentions in text.
    Returns sorted list of (country, frequency_score) tuples.
    Score = (title mentions * 3) + (total mentions).
    """
    hits = []
    title_lower = title.lower()
    for c in COUNTRY_LIST:
        c_lower = c.lower()
        total = len(re.findall(rf"\b{re.escape(c_lower)}\b", text_lower))
        if total > 0:
            title_mentions = len(re.findall(rf"\b{re.escape(c_lower)}\b", title_lower))
            score = title_mentions * 3 + total
            hits.append((c, score))

    hits.sort(key=lambda x: x[1], reverse=True)
    return hits


def extract_project_info(title, summary):
    """
    Pull project name, country, and status from article title + summary.
    Falls back to using the title itself as the project name when nothing
    specific can be identified.
    """
    text = f"{title} {summary}"

    # ---- project name ----
    project_name = None

    # 1) "FPSO ThingName"
    m = re.search(
        r"FPSO\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,4})",
        title,
        re.IGNORECASE,
    )
    if m:
        candidate = m.group(1).strip()
        if candidate.lower() not in GENERIC_WORDS and len(candidate) > 2:
            project_name = f"FPSO {candidate}"

    # 2) Quoted name near FPSO
    if not project_name:
        m = re.search(r'[""]([^""]{3,60})[""]', title)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in GENERIC_WORDS:
                project_name = candidate

    # 3) FPSO Name (more lenient) from full text
    if not project_name:
        m = re.search(
            r'FPSO\s+[""]?([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,4})',
            text,
            re.IGNORECASE,
        )
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in GENERIC_WORDS and len(candidate) > 2:
                project_name = f"FPSO {candidate}"

    # fallback: original title
    if not project_name:
        project_name = title.strip()

    # ---- country ----
    country = extract_country(title, summary)

    # ---- status ----
    status = "Unknown"
    text_lower = text.lower()
    for label, keywords in STATUS_PATTERNS.items():
        for kw in keywords:
            if kw in text_lower:
                status = label
                break
        if status != "Unknown":
            break

    return project_name, country, status


# ---- Crawl helpers ---------------------------------------------------

def build_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


def fetch_url(url, session):
    """GET a URL. Returns response or None on failure."""
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        return r
    except requests.exceptions.HTTPError:
        log.warning("  HTTP %s — %s", r.status_code if 'r' in dir() else "?", url)
        return None
    except requests.exceptions.RequestException as e:
        log.warning("  Request failed: %s — %s", e, url)
        return None


def fetch_search_page(site_config, session):
    """Try each search URL until one works."""
    for url in site_config["urls"]:
        log.info("  Trying %s", url)
        r = fetch_url(url, session)
        if r is not None:
            return r
        time.sleep(1)
    return None


def parse_date(element, selectors):
    """Extract date string from element using a list of CSS selectors."""
    for sel in selectors:
        el = element.select_one(sel.strip())
        if not el:
            continue
        dt = el.get("datetime")
        if dt:
            return dt[:10]

        text = el.get_text(strip=True)
        m = re.search(
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
            r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})",
            text,
            re.IGNORECASE,
        )
        if m:
            return m.group(1)
    return None


def find_article_elements(soup, site_config):
    """Locate article containers, falling back to class-based search."""
    elems = soup.select(site_config["article_tag"])
    if len(elems) >= 2:
        return elems

    # fallback: any tag with a post/article/story class
    elems = soup.find_all(
        ["article", "div", "li", "section"],
        class_=site_config["fallback_class"],
    )
    return elems if elems else []


def crawl_site(site_config, session):
    """Crawl one site, return list of article dicts."""
    articles = []
    log.info("--- %s ---", site_config["name"])

    r = fetch_search_page(site_config, session)
    if r is None:
        log.warning("  All search URLs failed, skipping.")
        return articles

    soup = BeautifulSoup(r.text, "html.parser")
    elem_list = find_article_elements(soup, site_config)
    log.info("  Found %d candidate containers", len(elem_list))

    title_selectors = [s.strip() for s in site_config["title_sel"].split(",")]
    date_selectors = [s.strip() for s in site_config["date_sel"].split(",")]
    summary_selectors = [s.strip() for s in site_config["summary_sel"].split(",")]

    for elem in elem_list:
        try:
            # title + link
            title_el = None
            for sel in title_selectors:
                title_el = elem.select_one(sel)
                if title_el:
                    break
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not title or "FPSO" not in title.upper():
                continue

            link = title_el.get("href", "")
            if link:
                link = urljoin(site_config["urls"][0], link)

            # summary
            summary = ""
            for sel in summary_selectors:
                s_el = elem.select_one(sel)
                if s_el:
                    txt = s_el.get_text(strip=True)
                    if len(txt) > 20:
                        summary = txt
                        break

            # date
            raw_date = parse_date(elem, date_selectors)

            project_name, country, status = extract_project_info(title, summary)

            articles.append({
                "name": project_name,
                "country": country or "",
                "flag": country_to_flag(country or ""),
                "status": status or "Unknown",
                "summary": (summary or title)[:500],
                "source_name": site_config["name"],
                "source_url": link or site_config["urls"][0],
                "source_date": raw_date or TODAY,
                "stainless_steel": "",
                "application": "",
            })
            log.info("  %s | %s | %s", status, country or "?", project_name[:50])

        except Exception:
            log.warning("  Parse error in %s element", site_config["name"], exc_info=True)

    return articles


# ---- Supabase --------------------------------------------------------

def upsert_projects(supabase, articles):
    """
    Write articles to Supabase projects table.
    Match by 'name' column. Update existing, insert new.
    Returns (new, updated) counts.
    """
    new = 0
    updated = 0
    table = supabase.table("projects")

    for a in articles:
        try:
            existing = table.select("id").eq("name", a["name"]).execute()
            if existing.data:
                table.update({
                    "country": a["country"],
                    "flag": a["flag"],
                    "status": a["status"],
                    "summary": a["summary"],
                    "source_name": a["source_name"],
                    "source_url": a["source_url"],
                    "source_date": a["source_date"],
                }).eq("name", a["name"]).execute()
                updated += 1
            else:
                table.insert(a).execute()
                new += 1
        except Exception:
            log.warning("  DB error: %s", a["name"], exc_info=True)

    return new, updated


# ---- Backfill ----------------------------------------------------------

def backfill_unknown_countries(supabase):
    """Query projects with empty/null country, re-extract from name+summary, and update."""
    log.info("=" * 54)
    log.info("BACKFILL MODE: re-extracting countries for Unknown entries")
    log.info("=" * 54)

    table = supabase.table("projects")

    # Fetch all projects
    resp = table.select("*").execute()
    if not resp.data:
        log.info("No projects in database.")
        return

    projects = resp.data
    log.info("Total projects in DB: %d", len(projects))

    # Find projects with empty/missing country
    unknown = [
        p for p in projects
        if not p.get("country") or p.get("country", "").strip() == ""
    ]

    log.info("Projects with missing country: %d", len(unknown))

    if not unknown:
        log.info("No unknown countries to backfill.")
        return

    updated = 0
    still_unknown = 0

    for p in unknown:
        title = p.get("name", "")
        summary = p.get("summary", "")
        country = extract_country(title, summary)

        if country:
            flag = country_to_flag(country)
            try:
                table.update({
                    "country": country,
                    "flag": flag,
                }).eq("id", p["id"]).execute()
                updated += 1
                log.info("  UPDATED: %s → %s", title[:60], country)
            except Exception:
                log.warning("  DB update failed for: %s", title[:60], exc_info=True)
        else:
            still_unknown += 1

        time.sleep(0.1)  # small delay to not hammer DB

    log.info("=" * 54)
    log.info("Backfill results:")
    log.info("  Updated: %d", updated)
    log.info("  Still unknown: %d", still_unknown)
    log.info("  Total processed: %d", len(unknown))

    if still_unknown > 0:
        log.info("--- Still unrecognized after re-extraction ---")
        for u in [p for p in unknown if not p.get("country") or not p["country"].strip()]:
            # these would be the ones that failed extraction again
            pass
        # re-query to get accurate list
        resp2 = table.select("*").execute()
        still = [p for p in resp2.data if not p.get("country") or not p.get("country", "").strip()]
        for p in still:
            log.info("  UNRECOGNIZED: %s", p.get("name", "")[:120])


# ---- Main ------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="FPSO Project Crawler")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Re-extract countries for existing Unknown entries in DB (no crawl).",
    )
    parser.add_argument(
        "--crawl",
        action="store_true",
        default=False,
        help="Run normal crawl (default if no other mode specified).",
    )
    args = parser.parse_args()

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Backfill mode
    if args.backfill:
        backfill_unknown_countries(supabase)
        return

    # Normal crawl mode (default when neither --backfill nor any other flag)
    log.info("=" * 54)
    log.info("FPSO Project Crawler  —  %s", TODAY)
    log.info("=" * 54)

    session = build_session()

    all_articles = []

    for i, site in enumerate(SITES):
        articles = crawl_site(site, session)
        all_articles.extend(articles)

        if i < len(SITES) - 1:
            delay = random.uniform(2, 5)
            log.info("Sleeping %.1fs ...", delay)
            time.sleep(delay)

    log.info("=" * 54)
    log.info("Total articles found: %d", len(all_articles))

    # Country recognition stats
    if all_articles:
        recognized = sum(1 for a in all_articles if a["country"])
        unrecognized = len(all_articles) - recognized
        log.info("Country recognition: %d/%d (%.1f%%)",
                 recognized, len(all_articles),
                 100 * recognized / len(all_articles))
        if unrecognized > 0:
            log.info("Unrecognized articles (%d):", unrecognized)
            for a in all_articles:
                if not a["country"]:
                    log.info("  [NO_COUNTRY] %s", a["name"][:120])

    if all_articles:
        new, updated = upsert_projects(supabase, all_articles)
        log.info(
            "抓取完成，共处理 %d 条项目（新增 %d 条，更新 %d 条）",
            len(all_articles),
            new,
            updated,
        )
    else:
        log.info("No articles with FPSO found.")

    # Print unrecognized summary at the very end
    unrecognized_titles = [a["name"] for a in all_articles if not a["country"]]
    if unrecognized_titles:
        print("\n" + "=" * 60)
        print("UNRECOGNIZED ARTICLES (no country extracted):")
        print("=" * 60)
        for i, t in enumerate(unrecognized_titles, 1):
            print(f"  {i}. {t[:130]}")
        print(f"\nTotal unrecognized: {len(unrecognized_titles)}")

    log.info("Crawl complete.")


if __name__ == "__main__":
    main()
