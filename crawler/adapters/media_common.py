#!/usr/bin/env python3
"""
Media crawler shared module — constants, extractors, and utilities for
industry media site adapters (Offshore Energy, OE Digital, World Oil, Splash247).

Provides:
  - Country extraction (multi-priority: FPSO name → operator → field → region → country)
  - Project name extraction (FPSO vessel name patterns)
  - Project alias normalization (cross-source dedup)
  - HTML fetching, parsing, saving with SHA256 audit trail
  - candidate_events insert helper

Each adapter imports this module and calls crawl_media_site() with its own
site_config dict. Adapters handle CLI (--dry-run, --local-only, --test).
"""

import json
import os
import re
import sys
import time
import random
import logging
from datetime import datetime, timezone
from typing import Optional
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

# Only keep articles published on or after this date.
# Historical news (pre-2023) is noise for stainless-steel business discovery.
MIN_PUBLICATION_DATE = "2023-01-01"

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0)"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fpso-crawler")

# ---- Site configs are defined in each adapter, not here -----------------

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
    "BOMESC": "China",  # Chinese contractor
    "Wison": "China",  # Chinese contractor
    "Wison New Energies": "China",  # Chinese contractor
    "Titan Wind Energy": "China",  # Chinese manufacturer
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
        ("Israel", ["israel", "israeli", "energean", "leviathan", "tamar", "karish", "tanin", "back online", "returns to operation"]),
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


# ---- Project alias mapping (cross-source normalization) ---------------
# Canonical project ID → list of known aliases.
# First alias in each list is the recommended display name.
# Mirrors src/data/project_aliases.ts — keep both in sync.

PROJECT_ALIASES = {
    # ===== Guyana — Stabroek Block =====
    "guyana-liza-1": [
        "Liza Phase 1 (FPSO Liza Destiny)",
        "Liza Phase 1", "FPSO Liza Destiny", "Liza Destiny",
        "Liza 1", "Liza Phase 1 Development", "Liza Destiny FPSO",
    ],
    "guyana-liza-2": [
        "Liza Phase 2 (FPSO Liza Unity)",
        "Liza Phase 2", "FPSO Liza Unity", "Liza Unity",
        "Liza 2", "Liza Phase 2 Development", "Liza Unity FPSO",
    ],
    "guyana-payara": [
        "Payara (FPSO Prosperity)",
        "Payara", "FPSO Prosperity", "Prosperity FPSO",
        "Payara Development", "Payara Project", "Payara Dev Project",
        "Payara FPSO", "Payara Field", "Prosperity", "FPSO Payara",
        "Payara Phase",
    ],
    "guyana-yellowtail": [
        "Yellowtail (FPSO ONE GUYANA)",
        "Yellowtail", "FPSO ONE GUYANA", "FPSO One Guyana",
        "One Guyana", "ONE GUYANA", "Yellowtail Development",
        "Yellowtail Project", "Yellowtail FPSO", "Yellowtail Field",
    ],
    "guyana-uaru": [
        "Uaru (FPSO Errea Wittu)",
        "Uaru", "FPSO Errea Wittu", "Errea Wittu",
        "Uaru Development", "Uaru Project", "Uaru FPSO", "Uaru Field",
    ],
    "guyana-whiptail": [
        "Whiptail (FPSO Jaguar)",
        "Whiptail", "FPSO Jaguar", "Jaguar FPSO",
        "Whiptail Development", "Whiptail Project",
        "Whiptail FPSO", "Whiptail Field",
    ],
    "guyana-hammerhead": [
        "Hammerhead",
        "Hammerhead", "Hammerhead Development", "Hammerhead Project",
        "Hammerhead FPSO", "Hammerhead Field",
    ],
    "guyana-longtail": [
        "Longtail",
        "Longtail", "Longtail Development", "Longtail Project",
        "Longtail FPSO", "Longtail Field",
    ],
    "guyana-gas-to-energy": [
        "Gas to Energy (Guyana)",
        "Gas to Energy", "Guyana Gas to Energy", "Gas-to-Energy",
        "Guyana Gas-to-Energy", "Gas to Energy Project",
        "Gas to Energy Guyana", "GtE Guyana", "Wales Gas to Energy",
    ],

    # ===== Brazil =====
    "brazil-maria-quiteria": [
        "FPSO Maria Quitéria",
        "FPSO Maria Quitéria", "FPSO Maria Quiteria",
        "Maria Quitéria", "Maria Quiteria",
    ],
    "brazil-almirante-tamandare": [
        "FPSO Almirante Tamandaré (Búzios)",
        "FPSO Almirante Tamandaré", "FPSO ALMIRANTE TAMANDARE",
        "Almirante Tamandaré", "ALMIRANTE TAMANDARE",
        "Almirante Tamandare", "Búzios 8 FPSO", "Buzios 8 FPSO",
    ],
    "brazil-bacalhau": [
        "FPSO Bacalhau (Equinor)",
        "FPSO Bacalhau", "FPSO BACALHAU", "Bacalhau", "BACALHAU",
        "Bacalhau FPSO", "Equinor Bacalhau", "Bacalhau Field",
    ],
    "brazil-peregrino": [
        "FPSO Peregrino (Equinor)",
        "FPSO Peregrino", "FPSO PEREGRINO", "Peregrino", "PEREGRINO",
        "Peregrino FPSO", "Equinor Peregrino", "Peregrino Field",
    ],
    "brazil-pioneiro-de-libra": [
        "FPSO Pioneiro de Libra",
        "FPSO Pioneiro de Libra", "FPSO PIONEIRO DE LIBRA",
        "Pioneiro de Libra", "PIONEIRO DE LIBRA",
        "Libra Pilot FPSO", "FPSO Pioneiro",
    ],
    "brazil-cidade-de-caraguatatuba": [
        "FPSO Cidade de Caraguatatuba (MV-27)",
        "FPSO Cidade de Caraguatatuba", "FPSO CIDADE DE CARAGUATATUBA",
        "Cidade de Caraguatatuba", "CIDADE DE CARAGUATATUBA",
        "MV-27", "FPSO CCG",
    ],
    "brazil-frade": [
        "FPSO Frade",
        "FPSO Frade", "FPSO FRADE", "Frade", "FRADE",
        "Frade FPSO", "Chevron Frade",
    ],
    "brazil-sepetiba": [
        "FPSO Cidade de Sepetiba (Sépia)",
        "FPSO Sepetiba", "FPSO SEPETIBA", "FPSO Cidade de Sepetiba",
        "Cidade de Sepetiba", "Sepetiba", "SEPETIBA",
        "Sépia FPSO", "Sepia FPSO",
    ],
    "brazil-bravo": [
        "FPSO Bravo (Petrobras)",
        "FPSO Bravo", "FPSO BRAVO", "Bravo FPSO", "BRAVO",
    ],
    "brazil-carioca": [
        "FPSO Carioca (Sépia Area)",
        "FPSO Carioca", "FPSO CARIOCA", "Carioca", "CARIOCA",
        "Carioca FPSO",
    ],
    "brazil-forte": [
        "FPSO Forte",
        "FPSO Forte", "FPSO FORTE", "Forte", "FORTE",
        "Forte FPSO",
    ],
    "suriname-fpso": [
        "Suriname FPSO (SBM Offshore)",
        "Suriname FPSO", "SBM Offshore Suriname FPSO",
        "Suriname-bound FPSO",
    ],
    "brazil-atlanta": [
        "FPSO Atlanta",
        "FPSO Atlanta", "Atlanta FPSO", "Atlanta",
        "Atlanta Field FPSO", "Enauta Atlanta",
    ],
    "brazil-alexandre-de-gusmao": [
        "FPSO Alexandre de Gusmão",
        "FPSO Alexandre de Gusmão", "FPSO ALEXANDRE DE GUSMÃO",
        "Alexandre de Gusmão", "Alexandre de Gusmao",
        "ALEXANDRE DE GUSMÃO", "FPSO Alexandre de Gusmao",
    ],
    "brazil-almirante-barroso": [
        "FPSO Almirante Barroso",
        "FPSO Almirante Barroso", "FPSO ALMIRANTE BARROSO",
        "Almirante Barroso", "ALMIRANTE BARROSO",
    ],
    "brazil-duque-de-caxias": [
        "FPSO Duque de Caxias",
        "FPSO Duque de Caxias", "FPSO Marechal Duque de Caxias",
        "Duque de Caxias", "Marechal Duque de Caxias",
    ],
    "brazil-anita-garibaldi": [
        "FPSO Anita Garibaldi",
        "FPSO Anita Garibaldi", "Anita Garibaldi",
    ],
    "brazil-anna-nery": [
        "FPSO Anna Nery",
        "FPSO Anna Nery", "Anna Nery",
    ],
    "brazil-guanabara": [
        "FPSO Guanabara",
        "FPSO Guanabara", "Guanabara FPSO", "Guanabara",
    ],
    "brazil-espirito-santo": [
        "FPSO Espirito Santo",
        "FPSO Espirito Santo", "FPSO Espírito Santo", "Espirito Santo FPSO",
    ],
    "brazil-marlim": [
        "FPSO Marlim",
        "FPSO Marlim", "FPSO Marlim Sul", "Marlim", "Marlim Sul",
    ],
    "brazil-cidade-de-angra-dos-reis": [
        "FPSO Cidade de Angra dos Reis",
        "FPSO Cidade de Angra dos Reis", "Cidade de Angra dos Reis",
    ],
    "brazil-cidade-de-ilhabela": [
        "FPSO Cidade de Ilhabela",
        "FPSO Cidade de Ilhabela", "Cidade de Ilhabela",
    ],
    "brazil-cidade-de-itaguai": [
        "FPSO Cidade de Itaguaí",
        "FPSO Cidade de Itaguaí", "FPSO Cidade de Itaguai",
        "Cidade de Itaguaí", "Cidade de Itaguai",
    ],
    "brazil-cidade-de-marica": [
        "FPSO Cidade de Maricá",
        "FPSO Cidade de Maricá", "FPSO Cidade de Marica",
        "Cidade de Maricá", "Cidade de Marica",
    ],
    "brazil-cidade-de-saquarema": [
        "FPSO Cidade de Saquarema",
        "FPSO Cidade de Saquarema", "Cidade de Saquarema",
    ],
    "brazil-cidade-de-santos": [
        "FPSO Cidade de Santos",
        "FPSO Cidade de Santos", "Cidade de Santos",
    ],
    "brazil-tartaruga-verde": [
        "Tartaruga Verde (FPSO Tartaruga Verde)",
        "Tartaruga Verde", "FPSO Tartaruga Verde",
        "Tartaruga Verde FPSO", "Tartaruga Verde Field",
    ],
    "brazil-buzios": [
        "Búzios Field FPSOs",
        "Búzios", "Buzios", "Búzios Field", "Buzios Field",
        "FPSO Búzios", "FPSO Buzios",
    ],
    "brazil-mero": [
        "Mero Field FPSOs",
        "Mero", "Mero Field", "FPSO Mero", "Libra Block Mero",
        "Alexandre de Gusmão", "FPSO Alexandre de Gusmão",
    ],
    "brazil-p-74": [
        "FPSO P-74",
        "FPSO P-74", "P-74 FPSO", "P-74",
        "PETROBRAS 74", "Petrobras 74",
    ],
    "brazil-p-75": [
        "FPSO P-75",
        "FPSO P-75", "P-75 FPSO", "P-75",
        "PETROBRAS 75", "Petrobras 75",
    ],
    "brazil-p-76": [
        "FPSO P-76",
        "FPSO P-76", "P-76 FPSO", "P-76",
        "PETROBRAS 76", "Petrobras 76",
    ],
    "brazil-p-77": [
        "FPSO P-77",
        "FPSO P-77", "P-77 FPSO", "P-77",
        "PETROBRAS 77", "Petrobras 77",
    ],
    "brazil-p-78": [
        "FPSO P-78",
        "FPSO P-78", "P-78 FPSO", "P-78",
        "PETROBRAS 78", "Petrobras 78",
    ],
    "brazil-p-79": [
        "FPSO P-79",
        "FPSO P-79", "P-79 FPSO", "P-79",
        "PETROBRAS 79", "Petrobras 79",
    ],
    "brazil-p-80": [
        "FPSO P-80",
        "FPSO P-80", "P-80 FPSO", "P-80",
    ],
    "brazil-p-81": [
        "FPSO P-81",
        "FPSO P-81", "P-81 FPSO", "P-81",
    ],
    "brazil-p-82": [
        "FPSO P-82",
        "FPSO P-82", "P-82 FPSO", "P-82",
    ],
    "brazil-p-83": [
        "FPSO P-83",
        "FPSO P-83", "P-83 FPSO", "P-83",
    ],
    "brazil-p-84": [
        "FPSO P-84",
        "FPSO P-84", "P-84 FPSO", "P-84",
    ],
    "brazil-p-85": [
        "FPSO P-85",
        "FPSO P-85", "P-85 FPSO", "P-85",
    ],

    # ===== UK — North Sea =====
    "uk-rosebank": [
        "Rosebank (FPSO Rosebank)",
        "Rosebank", "FPSO Rosebank", "Rosebank FPSO",
        "Rosebank Development", "Rosebank Project", "Rosebank Field",
        "Equinor Rosebank", "Rosebank Oil Field", "Rosebank North Sea",
    ],
    "uk-cambo": [
        "Cambo",
        "Cambo", "Cambo Field", "Cambo Development",
        "Cambo Project", "Cambo FPSO",
    ],
    "uk-schiehallion": [
        "Schiehallion (FPSO Glen Lyon)",
        "Schiehallion", "FPSO Glen Lyon", "Glen Lyon FPSO",
        "Glen Lyon", "Schiehallion Field", "Schiehallion FPSO",
    ],
    "uk-foinaven": [
        "Foinaven",
        "Foinaven", "FPSO Foinaven", "FPSO Petrojarl Foinaven",
        "Foinaven Field", "Foinaven FPSO",
    ],
    "uk-captain": [
        "Captain Field (FPSO Captain)",
        "Captain", "FPSO Captain", "Captain Field", "Captain FPSO",
    ],
    "uk-buzzard": [
        "Buzzard Field",
        "Buzzard", "Buzzard Field", "Buzzard FPSO",
    ],
    "uk-clair": [
        "Clair Field",
        "Clair", "Clair Field", "Clair Ridge", "Clair Development",
    ],
    "uk-mariner": [
        "Mariner Field",
        "Mariner", "Mariner Field", "Mariner FPSO", "Equinor Mariner",
    ],
    "uk-victory": [
        "Victory",
        "Victory", "Victory Field", "Victory Development",
        "Victory Project", "Victory FPSO", "Victory Gas Field",
    ],
    "uk-belinda": [
        "Belinda",
        "Belinda", "Belinda Field", "Belinda Development",
        "Belinda Project", "Belinda FPSO",
    ],
    "uk-triton": [
        "Triton FPSO",
        "FPSO Triton", "Triton FPSO", "Triton", "Triton Area",
    ],

    # ===== Angola =====
    "angola-agogo": [
        "FPSO Agogo",
        "FPSO Agogo", "Agogo FPSO", "Agogo",
        "Agogo Field", "Agogo Development", "Agogo Project",
        "Agogo FFD", "MODEC Agogo",
    ],
    "angola-greater-plutonio": [
        "FPSO Greater Plutonio",
        "FPSO Greater Plutonio", "Greater Plutonio",
        "FPSO Plutonio", "Plutonio FPSO",
    ],
    "angola-dalia": [
        "FPSO Dalia",
        "FPSO Dalia", "Dalia FPSO", "Dalia", "Dalia Field",
    ],
    "angola-girassol": [
        "FPSO Girassol",
        "FPSO Girassol", "Girassol FPSO", "Girassol", "Girassol Field",
    ],
    "angola-pazflor": [
        "FPSO Pazflor",
        "FPSO Pazflor", "Pazflor FPSO", "Pazflor",
    ],
    "angola-clov": [
        "FPSO CLOV",
        "FPSO CLOV", "CLOV FPSO", "CLOV", "CLOV Field",
    ],
    "angola-ndungu": [
        "FPSO Ndungu",
        "FPSO Ndungu", "Ndungu FPSO", "Ndungu", "Ndungu Field",
    ],
    "angola-kaombo": [
        "Kaombo (FPSO Kaombo Norte / Sul)",
        "Kaombo", "FPSO Kaombo Norte", "FPSO Kaombo Sul",
        "Kaombo Norte", "Kaombo Sul", "Kaombo Project",
    ],
    "angola-kizomba-a": [
        "FPSO Kizomba A",
        "FPSO Kizomba A", "Kizomba A", "Kizomba A FPSO",
    ],

    # ===== Nigeria =====
    "nigeria-zafiro": [
        "FPSO Zafiro",
        "FPSO Zafiro", "Zafiro FPSO", "Zafiro",
        "Zafiro Field", "Zafiro Development", "Zafiro Project",
        "Nigeria Zafiro",
    ],
    "nigeria-bonga": [
        "FPSO Bonga",
        "FPSO Bonga", "Bonga FPSO", "Bonga", "Bonga Field",
        "Bonga Main", "FPSO Bonga North", "FPSO Bonga South West",
    ],
    "nigeria-egina": [
        "FPSO Egina",
        "FPSO Egina", "Egina FPSO", "Egina", "Egina Field",
    ],
    "nigeria-akpo": [
        "FPSO Akpo",
        "FPSO Akpo", "Akpo FPSO", "Akpo", "Akpo Field",
    ],
    "nigeria-erha": [
        "FPSO Erha",
        "FPSO Erha", "Erha FPSO", "Erha", "Erha Field",
    ],
    "nigeria-agbami": [
        "FPSO Agbami",
        "FPSO Agbami", "Agbami FPSO", "Agbami", "Agbami Field",
    ],
    "nigeria-usan": [
        "FPSO Usan",
        "FPSO Usan", "Usan FPSO", "Usan", "Usan Field",
    ],

    # ===== Ghana =====
    "ghana-jubilee": [
        "Jubilee (FPSO Kwame Nkrumah)",
        "Jubilee", "FPSO Kwame Nkrumah", "Kwame Nkrumah",
        "Jubilee Field", "Jubilee FPSO",
    ],
    "ghana-ten": [
        "TEN (FPSO John Evans Atta Mills)",
        "TEN", "TEN Field", "FPSO John Evans Atta Mills",
        "John Evans Atta Mills", "TEN FPSO",
    ],
    "ghana-pecan": [
        "Pecan (FPSO John Agyekum Kufuor)",
        "Pecan", "Pecan Field", "FPSO John Agyekum Kufuor",
        "John Agyekum Kufuor", "Pecan FPSO", "JAK FPSO",
    ],

    # ===== Ivory Coast =====
    "ivory-coast-baleine": [
        "Baleine (FPSO Baleine)",
        "Baleine", "FPSO Baleine", "Baleine FPSO",
        "Baleine Field", "Baleine Phase", "Eni Baleine",
    ],
    "ivory-coast-baobab": [
        "Baobab",
        "Baobab", "FPSO Baobab", "Baobab FPSO",
        "Baobab Field", "Baobab Development", "Baobab Project",
    ],

    # ===== Senegal =====
    "senegal-sangomar": [
        "Sangomar (FPSO Léopold Sédar Senghor)",
        "Sangomar", "Sangomar Field",
        "FPSO Léopold Sédar Senghor", "Leopold Sedar Senghor",
        "Léopold Sédar Senghor", "Sangomar FPSO", "Sangomar Development",
    ],

    # ===== USA — Gulf of Mexico =====
    "usa-vito": [
        "Vito (FPSO Vito)",
        "Vito", "FPSO Vito", "Vito FPSO", "Vito Field", "Shell Vito",
    ],
    "usa-argos": [
        "Argos (FPSO Argos)",
        "Argos", "FPSO Argos", "Argos FPSO", "Argos Platform",
        "Mad Dog 2", "Mad Dog Phase 2", "BP Argos",
    ],
    "usa-stones": [
        "Stones (FPSO Turritella)",
        "Stones", "FPSO Stones", "FPSO Turritella",
        "Turritella", "Stones Field", "Shell Stones",
    ],
    "usa-salamanca": [
        "Salamanca (FPSO Salamanca)",
        "Salamanca", "FPSO Salamanca", "Salamanca FPSO",
    ],
    "usa-who-dat": [
        "Who Dat Field",
        "Who Dat", "Who Dat Field", "Who Dat FPSO",
    ],

    # ===== Norway =====
    "norway-johan-castberg": [
        "Johan Castberg (FPSO Johan Castberg)",
        "Johan Castberg", "FPSO Johan Castberg",
        "Johan Castberg FPSO", "Johan Castberg Field", "Castberg",
    ],
}

# Build reverse index: lowercase alias → canonical_id
_ALIAS_TO_CANONICAL = {}
for _cid, _aliases in PROJECT_ALIASES.items():
    for _a in _aliases:
        _ALIAS_TO_CANONICAL[_a.lower()] = _cid

GENERIC_WORDS_FOR_MATCH = {
    "fpso", "the", "a", "an", "for", "and", "with", "new", "first", "latest",
    "project", "vessel", "unit", "platform", "production", "storage",
    "offloading", "of", "in", "at", "to", "is", "on", "as", "by",
    "its", "will", "has", "been", "from", "was", "that", "this",
    "next", "two", "three", "four", "one", "major", "another",
    "floating", "be", "it", "or", "second", "third", "phase",
    "field", "development", "dev",
    # Junk-phrase words from title-fallback names like "FPSO from Modec for"
    # or "FPSO cooperation deal with SBM Offshore". Single-token overlap on
    # a contractor name (e.g. "modec" in "MODEC Agogo") caused false
    # canonical matches, so strip these before token scoring.
    "modec", "sbm", "offshore", "cooperation", "deal", "extension",
    "award", "contract", "order", "buys", "bags", "taps", "signed",
    "awarded", "secured", "wins", "hull", "construction", "firm",
    "newbuild", "singapore",
}


def normalize_project_name(raw_name):
    """
    Normalize a raw project name to its canonical project ID.

    Matching strategies (tried in order):
    1. Exact match (case-insensitive) against all known aliases
    2. Strip "FPSO " prefix, exact match again
    3. Keyword overlap scoring — tokenize the raw name and each project's
       alias set, compute precision/recall, pick the best match.

    Returns canonical project ID string, or None if no match found.
    Mirrors the TypeScript normalizeProjectName() in src/data/project_aliases.ts.
    """
    if not raw_name or not isinstance(raw_name, str):
        return None

    cleaned = raw_name.strip()
    if not cleaned:
        return None

    cleaned_lower = cleaned.lower()

    # -- Strategy 1: exact match --
    cid = _ALIAS_TO_CANONICAL.get(cleaned_lower)
    if cid:
        return cid

    # -- Strategy 2: strip "FPSO " prefix --
    stripped = re.sub(r"^fpso\s+", "", cleaned_lower, flags=re.IGNORECASE)
    if stripped != cleaned_lower:
        cid = _ALIAS_TO_CANONICAL.get(stripped)
        if cid:
            return cid

    # -- Strategy 3: keyword overlap scoring --
    raw_tokens = set(
        t for t in re.split(r"[\s\-–—/.,;:!?()\"']+", cleaned_lower)
        if len(t) >= 2 and t not in GENERIC_WORDS_FOR_MATCH
    )
    if not raw_tokens:
        return None

    raw_token_count = len(raw_tokens)
    best_match = None  # (canonical_id, combined_score)

    for cid, aliases in PROJECT_ALIASES.items():
        all_alias_text = " ".join(aliases).lower()
        alias_tokens = set(
            t for t in re.split(r"[\s\-–—/.,;:!?()\"']+", all_alias_text)
            if len(t) >= 2
        )

        score = sum(1 for t in raw_tokens if t in alias_tokens)

        precision = score / raw_token_count if raw_token_count > 0 else 0
        max_recall_denom = min(raw_token_count, len(alias_tokens))
        recall = score / max_recall_denom if max_recall_denom > 0 else 0

        # Require score >= 2 for multi-token inputs, or score >= 1 with
        # high precision for single-token inputs (e.g. "Stones FPSO").
        if precision >= 0.5 and recall >= 0.4:
            if score >= 2 or (score == 1 and precision >= 0.8):
                combined = precision * 0.6 + recall * 0.4
                if best_match is None or combined > best_match[1]:
                    best_match = (cid, combined)

    return best_match[0] if best_match else None


def get_display_name(canonical_id):
    """Return the recommended display name for a canonical project ID."""
    aliases = PROJECT_ALIASES.get(canonical_id)
    return aliases[0] if aliases else canonical_id


# Legacy 4-value status taxonomy replaced by 9 lifecycle phases
# (migration 025). Ordered early→late; extract_project_info returns the
# latest phase whose keyword matches.
STATUS_PATTERNS = {
    "Delivery": [
        "delivered", "delivery", "completed", "first oil",
        "production start", "operational", "in operation", "on stream",
        "started production", "commenced production", "onstation",
        "on station", "sailaway", "sail away", "achieved first oil",
        "producing", "production commenced",
    ],
    "Commissioning": [
        "commissioning", "commissioned", "start-up", "startup",
        "hook-up", "hook up", "mechanical completion",
    ],
    "Construction": [
        "under construction", "being built", "construction",
        "building", "fabrication", "under development",
        "steel cut", "first steel", "keel laying", "hull launch",
        "topsides", "integration", "outfitting", "dry dock",
    ],
    "Procurement": [
        "procurement", "tender", "bid", "purchase", "vendor registration",
        "long-lead", "long lead",
    ],
    "EPC Award": [
        "epc contract", "contract awarded", "letter of intent", "LOI",
        "MoU", "memorandum", "agreement signed", "secured contract",
        "won contract", "awarded contract",
    ],
    "Approval": [
        "approved", "approval", "sanctioned", "fid",
        "final investment decision", "development consent",
        "permit granted", "license granted", "eia approved",
    ],
    "Design": [
        "FEED", "pre-FEED", "front-end engineering", "detailed design",
        "engineering design",
    ],
    "Planning": [
        "planned", "planning", "proposed", "study",
        "development plan", "field development plan",
        "environmental impact", "eia",
    ],
    "Concept": [
        "concept", "conceptual", "pre-feasibility", "feasibility",
        "preliminary",
    ],
}

# ---- News media blacklist -----------------------------------------------
# Trade media and news outlets are publishers, never procurement-chain
# entities. Any entity name hitting this list is skipped at extraction
# time and stripped from stored chain values. DEMO sources included.
NEWS_MEDIA_BLACKLIST = [
    "reuters", "bloomberg", "paper advance", "offshore energy",
    "offshore magazine", "world oil", "splash247", "splash 247",
    "upstream", "rigzone", "energy voice", "tradewinds", "gcaptain",
    "marine link", "marinelink", "oe digital", "riviera",
    "world fertilizer", "sugar online", "chemical week",
    "hydrocarbon processing", "lng prime", "pharmaceutical technology",
    "world nuclear news", "thinkgeoenergy", "mining.com",
    "global water intelligence", "demo",
]


def is_news_media_name(name):
    """True when `name` looks like a news outlet / trade media title."""
    n = (name or "").strip().lower()
    if len(n) < 3:
        return False
    return any(m in n for m in NEWS_MEDIA_BLACKLIST)


def sanitize_chain(chain):
    """Drop news-media names from a comma/semicolon-separated chain string.

    Used wherever a chain value is persisted or displayed, so a polluted
    row can never re-enter projects or reach a contact path.
    """
    if not chain:
        return ""
    parts = [p.strip() for p in re.split(r"[,;]", chain)]
    return ", ".join(p for p in parts if p and not is_news_media_name(p))


# ---- FPSO procurement entity extraction ---------------------------------

PROCUREMENT_ENTITIES = {
    # FPSO Contractors / Shipyards
    "SBM Offshore": "Contractor/Shipyard",
    "MODEC": "Contractor/Shipyard",
    "Yinson": "Contractor/Shipyard",
    "Bumi Armada": "Contractor/Shipyard",
    "BW Offshore": "Contractor/Shipyard",
    "Bluewater": "Contractor/Shipyard",
    "Teekay": "Contractor/Shipyard",
    "Altera Infrastructure": "Contractor/Shipyard",
    "MISC Berhad": "Contractor/Shipyard",
    "COSCO Shipping": "Contractor/Shipyard",
    "COSCO": "Contractor/Shipyard",
    "Seatrium": "Contractor/Shipyard",
    "Sembcorp Marine": "Contractor/Shipyard",
    "Keppel Offshore": "Contractor/Shipyard",
    "Keppel O&M": "Contractor/Shipyard",
    "Samsung Heavy Industries": "Contractor/Shipyard",
    "Hyundai Heavy Industries": "Contractor/Shipyard",
    "Hanwha Ocean": "Contractor/Shipyard",
    "Daewoo Shipbuilding": "Contractor/Shipyard",
    "DSME": "Contractor/Shipyard",
    # Topsides EPC
    "TechnipFMC": "Topsides EPC",
    "Technip": "Topsides EPC",
    "Petrofac": "Topsides EPC",
    "Saipem": "Topsides EPC",
    "Worley": "Topsides EPC",
    "Wood Group": "Topsides EPC",
    "Wood PLC": "Topsides EPC",
    "Aker Solutions": "Topsides EPC",
    "Aibel": "Topsides EPC",
    "McDermott": "Topsides EPC",
    "Subsea 7": "Topsides EPC",
    "Fluor": "Topsides EPC",
    "Bechtel": "Topsides EPC",
    "KBR": "Topsides EPC",
    # Key Equipment Suppliers
    "Siemens Energy": "Equipment Supplier",
    "Siemens": "Equipment Supplier",
    "ABB": "Equipment Supplier",
    "GE Power": "Equipment Supplier",
    "General Electric": "Equipment Supplier",
    "MAN Energy Solutions": "Equipment Supplier",
    "Wärtsilä": "Equipment Supplier",
    "Wartsila": "Equipment Supplier",
    "Mitsubishi Heavy Industries": "Equipment Supplier",
    "Rolls-Royce": "Equipment Supplier",
    "Caterpillar": "Equipment Supplier",
    "Solar Turbines": "Equipment Supplier",
    "Baker Hughes": "Equipment Supplier",
    "Schlumberger": "Equipment Supplier",
    "SLB": "Equipment Supplier",
    "Halliburton": "Equipment Supplier",
    "NOV": "Equipment Supplier",
    "National Oilwell Varco": "Equipment Supplier",
    "Cameron": "Equipment Supplier",
    "FMC Technologies": "Equipment Supplier",
    "OneSubsea": "Equipment Supplier",
    "Alfa Laval": "Equipment Supplier",
    "Sulzer": "Equipment Supplier",
    "Flowserve": "Equipment Supplier",
    "Emerson": "Equipment Supplier",
    "Honeywell": "Equipment Supplier",
    "Yokogawa": "Equipment Supplier",
    "Kongsberg": "Equipment Supplier",
}


# Role evidence required before an entity counts as a procurement-chain
# member. A bare mention ("X's CEO said", "X shares fell") is not enough —
# the text must show X in an EPC/contractor/shipyard/supplier role.
PROCUREMENT_ROLE_PATTERNS = [
    r"epc", r"epcc", r"contract", r"award", r"contractor", r"engineering",
    r"construction", r"shipyard", r"\byard\b", r"letter of intent", r"\bloi\b",
    r"tender", r"fabricat", r"conversion", r"supply", r"supplier", r"signed",
    r"selected", r"wins?", r"secured", r"agreement", r"build",
]

_ROLE_WINDOW = 160  # context chars examined around each entity mention


def extract_procurement(text):
    """Scan article text for known FPSO procurement entities.

    Matches against PROCUREMENT_ENTITIES dictionary (contractors/shipyards,
    topsides EPC firms, and equipment suppliers). Uses word-boundary regex
    to avoid false positives on short names (e.g. ABB inside "scabbard").
    Deduplicates substring matches (e.g. "Technip" inside "TechnipFMC").

    Guards:
    - news-media names are never extracted (NEWS_MEDIA_BLACKLIST);
    - an entity only counts when the surrounding context shows an explicit
      role ("EPC contract awarded to X", "contractor X", "engineering by X",
      "construction by X", shipyard/supplier wording). No role evidence →
      no extraction — never guess.

    Only FPSO-relevant entities are in the dictionary, so non-FPSO articles
    naturally produce empty results.

    Returns comma-separated string of matched entity names, or empty string.
    """
    if not text:
        return ""
    matches = []
    text_lower = text.lower()
    for entity_name in PROCUREMENT_ENTITIES:
        if is_news_media_name(entity_name):
            continue
        pattern = rf"\b{re.escape(entity_name.lower())}\b"
        for m in re.finditer(pattern, text_lower):
            window = text_lower[
                max(0, m.start() - _ROLE_WINDOW):m.end() + _ROLE_WINDOW]
            if any(re.search(rp, window) for rp in PROCUREMENT_ROLE_PATTERNS):
                matches.append(entity_name)
                break
    # Deduplicate: remove shorter entity if it is a substring of
    # a longer matched entity (e.g. "Technip" inside "TechnipFMC").
    if len(matches) > 1:
        matches.sort(key=len, reverse=True)
        filtered = []
        for m in matches:
            m_lower = m.lower()
            if not any(m_lower != kept.lower() and m_lower in kept.lower()
                       for kept in filtered):
                filtered.append(m)
        matches = filtered
    return ", ".join(matches) if matches else ""


# ---- Technical spec extraction from article text -----------------------
# Strictly based on source text. When uncertain, returns None — never guesses.

def _parse_int_from_match(val_str: str) -> Optional[int]:
    """Parse matched numeric string to int. Returns None on failure or zero."""
    if not val_str:
        return None
    try:
        # Remove thousands separators; handle both "." and "," as separators
        cleaned = re.sub(r"[.,](?=\d{3}(?:[.,]|\b))", "", val_str)
        # Remove remaining punctuation
        cleaned = re.sub(r"[.,]", "", cleaned)
        n = int(float(cleaned))
        return n if n > 0 else None
    except (ValueError, TypeError):
        return None


def extract_water_depth_from_article(text: str) -> Optional[int]:
    """Extract water depth in meters from article text.
    Matches patterns like "水深 2140 米", "water depth of 1,500 m",
    "in 2,000 meters of water", "profundidade de 2.200 m".
    """
    if not text:
        return None
    patterns = [
        # "X meters of water" / "X m water depth"
        r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:meters?|m)\s+(?:of\s+)?water\s+depth",
        r"water\s+depth\s*(?:of\s+)?(?::\s*)?(?:approximately\s+)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:m|meters?)",
        r"in\s+(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:m|meters?)\s+(?:of\s+)?water",
        # Portuguese
        r"l[âa]mina\s+d['’]?[áa]gua\s*(?:de\s+)?(?:aproximadamente\s+)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:m|metros?)",
        r"profundidade\s*(?:de\s+)?(?:aproximadamente\s+)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:m|metros?)",
        # Chinese
        r"水深\s*[:：]?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*米",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            n = _parse_int_from_match(m.group(1))
            if n is not None and 10 <= n <= 5000:
                return n
    return None


def extract_oil_capacity_from_article(text: str) -> Optional[int]:
    """Extract oil production capacity in bpd from article text.
    Matches "150,000 barrels per day", "produção de 180 mil bbl/d", etc.
    """
    if not text:
        return None
    patterns = [
        # "X barrels per day" / "X bpd" / "X bbl/d"
        r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:barrels?\s+per\s+day|bpd|bbl/?d)",
        # "capacity of X bpd"
        r"(?:capacity|production|output)\s*(?:of\s+)?(?:up\s+to\s+)?(?:approximately\s+)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:bpd|barrels?\s+per\s+day|bbl/?d)",
        # Portuguese: "produção de X bbl/d" / "X mil barris por dia"
        r"produ[çc][ãa]o\s*(?:de\s+)?(?:at[ée]\s+)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:mil\s+)?(?:bbl/?d|barris)",
        # "X-million-barrel-per-day"
        r"(\d{1,3}(?:[.,]\d+)?)\s*[-]?\s*million[-]?\s*(?:barrels?\s+per\s+day|bpd)",
        # Chinese
        r"(?:产能|产量|日产)\s*[:：]?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:万)?\s*(?:桶|bbl)/?(?:天|d|日)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val_str = m.group(1)
            # Handle "X million barrels" case separately
            n = _parse_int_from_match(val_str)
            if n is not None:
                if "million" in m.group(0).lower():
                    n = n * 1000000
                if 1000 <= n <= 500000:
                    return n
    return None


def extract_gas_capacity_from_article(text: str) -> Optional[int]:
    """Extract gas production capacity in million m³/d from article text.
    Matches "5 MMcmd", "3 million cubic meters per day", "produção de gás de 8 Mm³/d".
    """
    if not text:
        return None
    patterns = [
        # "X MMcmd" / "X million cubic meters per day"
        r"(\d{1,3}(?:[.,]\d+)?)\s*(?:MMcmd|million\s+(?:cubic\s+)?m(?:eters?)?[³3]?\s*(?:per\s+day|/?d))",
        # "X Mm³/d" / "X Mm3/d"
        r"(\d{1,3}(?:[.,]\d+)?)\s*Mm[³3]/?d",
        # Portuguese: "produção de gás de X milhões de m³/d"
        r"(?:g[áa]s|gas)\s*(?:capacity|produ[çc][ãa]o)\s*(?:de\s+)?(?:at[ée]\s+)?(\d{1,3}(?:[.,]\d+)?)\s*(?:milh[õo]es?|million)",
        # Chinese
        r"(?:天然气|燃气)\s*(?:产能|产量)\s*[:：]?\s*(\d{1,3}(?:[.,]\d+)?)\s*(?:百万|Million)\s*(?:立方米|m[³3])",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                val_clean = m.group(1).replace(",", "").replace(".", "")
                # Check for decimal (e.g. "3.5")
                if "." in m.group(1) or "," in m.group(1):
                    n = int(float(m.group(1).replace(",", ".")))
                else:
                    n = int(val_clean)
                if 1 <= n <= 100:
                    return n
            except (ValueError, TypeError):
                continue
    return None


def extract_hull_type_from_article(text: str) -> Optional[str]:
    """Extract FPSO hull type from article text.
    Matches known configurations: turret, spread-moored, conversion, newbuild, FLNG, FSO.
    """
    if not text:
        return None
    text_lower = text.lower()
    hull_types = [
        ("Turret", [r"\bturret\b", r"internal\s+turret", r"external\s+turret",
                    r"turret\s+moor(?:ed|ing)?", r"turret\s+system"]),
        ("Spread Moored", [r"spread\s+moored?", r"spread\s+mooring",
                           r"spread[- ]moored?", r"spread\s+moor"]),
        ("FLNG conversion", [r"flng\s+conversion", r"lng\s+conversion",
                              r"converted\s+(?:to\s+)?(?:flng|lng)"]),
        ("Newbuild", [r"\bnewbuild\b", r"new(?:ly)?[\s-]built",
                      r"purpose[\s-]built"]),
        ("Conversion", [r"\bconversion\b", r"converted\s+(?:tanker|vlcc|supertanker|hull)"]),
        ("FSO", [r"\bfso\b", r"floating\s+storage\s+(?:and\s+)?offloading"]),
    ]
    matched = []
    for name, patterns in hull_types:
        for pat in patterns:
            if re.search(pat, text_lower):
                matched.append(name)
                break
    return ", ".join(matched) if matched else None


def extract_operator_from_article(text: str) -> Optional[str]:
    """Extract operator name from article text using OPERATOR_COUNTRY lookup.
    Only returns operators strongly tied to known countries (non-None mapping).
    """
    if not text:
        return None
    op_keys = sorted(
        [k for k, v in OPERATOR_COUNTRY.items() if v is not None],
        key=len, reverse=True,
    )
    for op_name in op_keys:
        if re.search(rf"\b{re.escape(op_name)}\b", text, re.IGNORECASE):
            return op_name
    return None


def extract_basin_from_article(text: str) -> Optional[str]:
    """Extract sedimentary basin name from article text using REGION_TO_COUNTRY.
    Returns basin name if found in the known basins list.
    """
    if not text:
        return None
    # Known basins with country mapping
    basin_names = [
        "Santos Basin", "Campos Basin", "Espírito Santo Basin",
        "Espirito Santo Basin", "Sergipe-Alagoas Basin", "Potiguar Basin",
        "Ceará Basin", "Foz do Amazonas Basin", "Pelotas Basin",
        "Stabroek Block", "Guyana-Suriname Basin",
        "Kwanza Basin", "Lower Congo Basin", "Niger Delta Basin",
        "Tano Basin", "Rovuma Basin", "Browse Basin", "Carnarvon Basin",
        "Bonaparte Basin", "Sarawak Basin", "Sabah Basin",
        "Kutei Basin", "Cuu Long Basin", "Nam Con Son Basin",
        "Krishna Godavari Basin", "Orange Basin", "Jeanne d'Arc Basin",
        "Nile Delta Basin", "Levant Basin",
        # Portuguese names
        "Bacia de Santos", "Bacia de Campos",
    ]
    text_lower = text.lower()
    for basin in sorted(basin_names, key=len, reverse=True):
        if basin.lower() in text_lower:
            return basin
    return None


def extract_field_name_from_article(text: str) -> Optional[str]:
    """Extract oil/gas field name from article text using UNIQUE_FIELD_OWNER."""
    if not text:
        return None
    text_lower = text.lower()
    for field_name in sorted(UNIQUE_FIELD_OWNER.keys(), key=len, reverse=True):
        if field_name.lower() in text_lower:
            return field_name
    return None


def extract_tech_specs_from_article(text: str) -> dict:
    """Extract all technical specifications from article text.
    Returns dict with nullable int/text values. All extractions are
    strictly based on source text — uncertain fields are None.
    """
    if not text:
        return {
            "water_depth_m": None,
            "oil_capacity_bpd": None,
            "gas_capacity_mmcmd": None,
            "hull_type": None,
            "field_name": None,
            "operator_name": None,
            "basin": None,
        }
    return {
        "water_depth_m": extract_water_depth_from_article(text),
        "oil_capacity_bpd": extract_oil_capacity_from_article(text),
        "gas_capacity_mmcmd": extract_gas_capacity_from_article(text),
        "hull_type": extract_hull_type_from_article(text),
        "field_name": extract_field_name_from_article(text),
        "operator_name": extract_operator_from_article(text),
        "basin": extract_basin_from_article(text),
    }


def extract_corrosive_media(text: str) -> dict:
    """Extract corrosive media parameters (H2S, CO2, sour service, chloride)
    from FPSO project article text.

    Strict extraction: only returns True when a keyword is explicitly found
    in the source text. Never infers from context (e.g. "pre-salt" alone
    does NOT imply CO2 — the text must say "CO2" or "carbon dioxide").

    Returns:
        {
            h2s: bool,
            co2: bool,
            sour_service: bool,   # "sour gas" / "sour service" explicitly stated
            chloride: bool,
            details: str,         # surrounding text snippets for manual review
        }
    """
    result = {
        "h2s": False,
        "co2": False,
        "sour_service": False,
        "chloride": False,
        "details": "",
    }

    if not text:
        return result

    text_lower = text.lower()
    snippets = []

    # ---- H2S / hydrogen sulfide ----
    h2s_patterns = [
        r"\bh2s\b",
        r"hydrogen\s+sulf?ide",
        r"hydrogen\s+sulphide",
    ]
    for pat in h2s_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 50)
            snippet = text[start:end].replace("\n", " ").strip()
            snippets.append(f"[H2S] {snippet}")
            result["h2s"] = True
            break  # one match is enough for boolean
        if result["h2s"]:
            break

    # ---- CO2 / carbon dioxide ----
    co2_patterns = [
        r"\bco2\b",
        r"carbon\s+dioxide",
    ]
    for pat in co2_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 50)
            snippet = text[start:end].replace("\n", " ").strip()
            snippets.append(f"[CO2] {snippet}")
            result["co2"] = True
            break
        if result["co2"]:
            break

    # ---- Sour service / sour gas (explicitly stated) ----
    sour_patterns = [
        r"\bsour\s+(?:gas|service|environment|field|crude)\b",
        r"\bacid\s+gas\b",
    ]
    for pat in sour_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 50)
            snippet = text[start:end].replace("\n", " ").strip()
            snippets.append(f"[sour] {snippet}")
            result["sour_service"] = True
            break
        if result["sour_service"]:
            break

    # ---- Chloride ----
    chloride_patterns = [
        r"\bchloride[s]?\b",
        r"\bchlorine\b",
    ]
    for pat in chloride_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 50)
            snippet = text[start:end].replace("\n", " ").strip()
            snippets.append(f"[chloride] {snippet}")
            result["chloride"] = True
            break
        if result["chloride"]:
            break

    # ---- Operating temperature (record for context, not boolean) ----
    temp_patterns = [
        r"(?:operating|design)\s+temperature\s*(?:of\s+)?(?:up\s+to\s+)?(\d{2,4})\s*[°º]?\s*[CF]",
        r"temperature\s*(?:of\s+)?(?:up\s+to\s+)?(\d{2,4})\s*[°º]?\s*[CF]",
    ]
    for pat in temp_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 50)
            snippet = text[start:end].replace("\n", " ").strip()
            snippets.append(f"[temperature] {snippet}")
            break
        if any("temperature" in s for s in snippets):
            break

    result["details"] = " | ".join(snippets) if snippets else ""
    return result


# Words that are not real project names even if they follow "FPSO"
GENERIC_WORDS = {
    "the", "a", "an", "for", "and", "with", "new", "first", "latest",
    "project", "vessel", "unit", "platform", "production", "storage",
    "offloading", "of", "in", "at", "to", "is", "on", "as", "by",
    "its", "will", "has", "been", "from", "was", "that", "this",
    "next", "two", "three", "four", "one", "major", "another",
    "floating", "fpso", "be", "it", "or", "second", "third",
}


# ---- Project info extraction -----------------------------------------


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

    # ---- phase ----
    # Dict is ordered early→late; keep the LAST matching phase so the
    # latest lifecycle stage wins.
    phase = "Unknown"
    text_lower = text.lower()
    for label, keywords in STATUS_PATTERNS.items():
        if any(kw in text_lower for kw in keywords):
            phase = label

    return project_name, country, phase


# ---- Crawl helpers ---------------------------------------------------

def build_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


def _safe_decode_response(r):
    """Decode response body to text, preferring UTF-8.
    Uses response.apparent_encoding (chardet) when server omits charset.
    Falls back to UTF-8 with replacement chars as last resort.
    Returns decoded text string."""
    content_type = r.headers.get("Content-Type", "")
    # If server explicitly declares charset, trust it
    if "charset" in content_type.lower():
        return r.text
    # Try UTF-8 first (most web content is UTF-8)
    try:
        return r.content.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # Fall back to apparent encoding (chardet-based)
    apparent = getattr(r, "apparent_encoding", None)
    if apparent and apparent.lower().replace("-", "") != "utf8":
        try:
            return r.content.decode(apparent)
        except (UnicodeDecodeError, LookupError):
            pass
    # Last resort: UTF-8 with replacement chars (preserves what we can)
    return r.content.decode("utf-8", errors="replace")


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


def save_raw_html_media(html_text, site_config, supabase=None):
    """Save raw HTML for a crawled site and record in source_documents."""
    import hashlib as _hashlib
    from pathlib import Path as _Path
    base_dir = _Path(__file__).resolve().parent.parent  # crawler/ (media_common.py is in adapters/)
    data_dir = base_dir / "data" / "media"
    data_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\-]", "_", site_config["name"].lower())
    filepath = data_dir / f"{TODAY}_{safe_name}.html"
    filepath.write_text(html_text, encoding="utf-8")
    sha256 = _hashlib.sha256(html_text.encode("utf-8")).hexdigest()
    # Save SHA256 sidecar
    hash_path = data_dir / f"{TODAY}_{safe_name}.html.sha256"
    hash_path.write_text(f"{sha256}  {TODAY}_{safe_name}.html\n")
    log.info("Saved raw HTML: %s (SHA256=%s, %d bytes)",
             filepath.name, sha256[:16], len(html_text.encode("utf-8")))
    # Save to source_documents
    if supabase:
        try:
            original_url = site_config.get("urls", [""])[0]
            table = supabase.table("source_documents")
            table.insert({
                "file_name": filepath.name,
                "file_path": str(filepath),
                "file_hash_sha256": sha256,
                "file_type": "HTML",
                "file_size_bytes": len(html_text.encode("utf-8")),
                "publication_date": TODAY,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "original_url": original_url,
            }).execute()
            log.info("Saved to source_documents: %s", filepath.name)
        except Exception:
            log.debug("source_documents insert skipped (table may not exist yet).")
    return filepath


def crawl_media_site(site_config, session, supabase=None):
    """Crawl one site, return list of article dicts."""
    articles = []
    log.info("--- %s ---", site_config["name"])

    r = fetch_search_page(site_config, session)
    if r is None:
        log.warning("  All search URLs failed, skipping.")
        return articles

    # Decode response safely (UTF-8 preferred, fallback to chardet)
    html_text = _safe_decode_response(r)

    # Save raw HTML to source_documents for audit trail
    save_raw_html_media(html_text, site_config, supabase=supabase)

    soup = BeautifulSoup(html_text, "html.parser")
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
            if not link:
                # Try parent <a> tag (some sites wrap heading in <a>)
                parent_a = title_el.find_parent("a")
                if parent_a:
                    link = parent_a.get("href", "")
            if not link:
                # Try any direct <a> child in the container element
                any_a = elem.find("a", href=True)
                if any_a:
                    link = any_a.get("href", "")
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

            # ---- Fetch full article body for richer extraction ----
            full_text = f"{title} {summary}"
            if link:
                try:
                    article_r = fetch_url(link, session)
                    if article_r:
                        article_html = _safe_decode_response(article_r)
                        article_soup = BeautifulSoup(article_html, "html.parser")
                        article_body = (
                            article_soup.find("article")
                            or article_soup.find("div", class_=re.compile(r"content|article|post|entry|single"))
                        )
                        if article_body:
                            article_text = article_body.get_text(" ", strip=True)
                            full_text = f"{title} {summary} {article_text}"
                        else:
                            full_text = f"{title} {summary} {article_soup.get_text(' ', strip=True)}"
                except Exception:
                    pass  # fall back to listing-page title+summary

            # date
            raw_date = parse_date(elem, date_selectors)

            # ---- Time filter: skip articles published before 2023 ----
            if raw_date and raw_date < MIN_PUBLICATION_DATE:
                log.info("  SKIP (too old: %s): %s", raw_date, title[:60])
                continue
            if not raw_date:
                # No date found — keep but flag for lower confidence downstream
                log.info("  KEEP (no date, low confidence): %s", title[:60])

            project_name, country, phase = extract_project_info(title, summary)

            procurement = extract_procurement(full_text)
            tech_specs = extract_tech_specs_from_article(full_text)
            corrosive = extract_corrosive_media(full_text)

            articles.append({
                "name": project_name,
                "country": country or "",
                "flag": country_to_flag(country or ""),
                "status": phase or "Unknown",  # legacy key kept for row readers
                "phase": phase or "",
                "summary": (summary or title)[:500],
                "source_name": site_config["name"],
                "source_url": link or "",
                "source_date": raw_date or "",
                "stainless_steel": "",
                "application": "",
                "event_type": "ARTICLE_MENTION",
                "evidence_quote": (summary or title)[:500],
                "publication_date": raw_date or "",
                "procurement_chain": procurement,
                "corrosive_media": corrosive,
                **tech_specs,
            })
            log.info("  %s | %s | %s", phase, country or "?", project_name[:50])

        except Exception:
            log.warning("  Parse error in %s element", site_config["name"], exc_info=True)

    return articles


# ---- candidate_events insert -----------------------------------------


def insert_candidate_events(supabase, articles):
    """
    Insert all articles into candidate_events table.
    Maps crawler article fields to candidate_events columns:
      name → project_name_raw, country → country, summary → summary,
      source_name → source_name, source_url → source_url,
      event_type → event_type, evidence_quote → evidence_quote,
      publication_date → publication_date.
    Before inserting, checks if (project_name_raw, event_type, summary)
    already exists — skips if duplicate.  Returns count of inserted rows.
    """
    inserted = 0
    skipped = 0
    table = supabase.table("candidate_events")

    for a in articles:
        try:
            project_name = a.get("name", "")
            event_type = a.get("event_type", "ARTICLE_MENTION")
            summary = a.get("summary", "")

            # Dedup: skip if (project_name_raw, event_type, summary) already exists
            existing = table.select("id") \
                .eq("project_name_raw", project_name) \
                .eq("event_type", event_type) \
                .eq("summary", summary) \
                .limit(1) \
                .execute()
            if existing.data:
                skipped += 1
                continue

            record = {
                "project_name_raw": a.get("name", ""),
                "country": a.get("country", ""),
                "summary": a.get("summary", ""),
                "source_name": a.get("source_name", ""),
                "source_url": a.get("source_url", ""),
                "review_status": "pending",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "event_type": a.get("event_type", "ARTICLE_MENTION"),
                "evidence_quote": (a.get("evidence_quote")
                                   or a.get("summary", ""))[:500],
                "publication_date": a.get("publication_date")
                                    or a.get("source_date", ""),
                "procurement_chain": a.get("procurement_chain", ""),
                "phase": a.get("phase", ""),
                # 技术规格字段
                "water_depth_m": a.get("water_depth_m"),
                "oil_capacity_bpd": a.get("oil_capacity_bpd"),
                "gas_capacity_mmcmd": a.get("gas_capacity_mmcmd"),
                "hull_type": a.get("hull_type"),
                "field_name": a.get("field_name"),
                "operator_name": a.get("operator_name"),
                "basin": a.get("basin"),
                "corrosive_media": json.dumps(a.get("corrosive_media", {})) if a.get("corrosive_media") else None,
            }
            table.insert(record).execute()
            inserted += 1
        except Exception:
            log.warning("  candidate_events insert error: %s",
                        a.get("name", "?"), exc_info=True)

    if skipped:
        log.info("Dedup: skipped %d duplicate(s)", skipped)
    return inserted
