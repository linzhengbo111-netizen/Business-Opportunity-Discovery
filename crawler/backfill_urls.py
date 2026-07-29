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

# Standalone script: search for real article URLs for empty-source_url projects

import requests, time, json, os, sys, re

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from supabase import create_client

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FPSOCrawler/1.0)",
}

PROJECTS = [
    ("FPSO Maria Quitéria", [
        "Maria Quitéria FPSO Petrobras",
        "Maria Quitéria Brazil FPSO",
    ], ["petrobras", "brazil", "santos", "campos", "quitéria"]),
    ("FPSO Agogo", [
        "Agogo FPSO MODEC Angola",
        "Agogo Angola FPSO TotalEnergies",
    ], ["modec", "angola", "totalenergies", "agogo"]),
    ("FPSO Zafiro", [
        "Zafiro FPSO Nigeria",
        "Zafiro Nigeria offshore FPSO",
    ], ["zafiro", "nigeria", "exxonmobil"]),
    ("FPSO Rosebank", [
        "Rosebank FPSO Equinor North Sea",
        "Rosebank UK FPSO",
    ], ["rosebank", "equinor", "north sea", "uk"]),
    ("FPSO Atlanta", [
        "Atlanta FPSO Enauta Brazil",
        "Atlanta FPSO Santos Basin",
    ], ["atlanta", "enauta", "brazil", "santos"]),
    ("FPSO Baobab", [
        "Baobab FPSO Ivory Coast",
        "Baobab Côte d'Ivoire FPSO",
        "Baobab FPSO Africa",
    ], ["baobab", "ivory coast", "côte d'ivoire", "vaalco", "ci", "africa"]),
]

SITES = [
    ("Offshore Energy", "https://www.offshore-energy.biz/wp-json/wp/v2/posts"),
    ("Splash247", "https://splash247.com/wp-json/wp/v2/posts"),
]

def search_wp_api(api_base, search_term, per_page=10):
    url = f"{api_base}?search={requests.utils.quote(search_term)}&per_page={per_page}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        posts = r.json()
        if not isinstance(posts, list):
            return []
        results = []
        for post in posts:
            title = post.get('title', {}).get('rendered', '')
            link = post.get('link', '')
            excerpt = post.get('excerpt', {}).get('rendered', '')
            excerpt = re.sub(r'<[^>]+>', '', excerpt)
            results.append((title, link, excerpt))
        return results
    except Exception:
        return []

def score_match(title, excerpt, proj_name, hints):
    score = 0
    text = (title + ' ' + excerpt).lower()
    title_lower = title.lower()
    
    # Score each project word
    proj_words = [w for w in proj_name.lower().replace('fpso ', '').split() if len(w) > 2]
    for w in proj_words:
        if w in title_lower:
            score += 40
        elif w in text:
            score += 15
    
    # Score hints
    for h in hints:
        if h.lower() in text:
            score += 8
    
    # FPSO in title
    if 'fpso' in title_lower:
        score += 5
    
    return score

if __name__ == "__main__":
    supa_url = os.getenv('SUPABASE_URL') or os.getenv('VITE_SUPABASE_URL')
    supa_key = os.getenv('SUPABASE_ANON_KEY') or os.getenv('VITE_SUPABASE_ANON_KEY')
    supabase = create_client(supa_url, supa_key)
    
    updates = []
    not_found = []
    
    for proj_name, search_terms, hints in PROJECTS:
        print(f"\n{'='*60}")
        print(f"Project: {proj_name}")
        
        best_match = None
        best_score = 0
        best_url = None
        best_source = None
        
        for site_name, api_base in SITES:
            if best_score >= 60:
                break
            for term in search_terms:
                if best_score >= 60:
                    break
                print(f"  [{site_name}] '{term}'")
                results = search_wp_api(api_base, term)
                for title, link, excerpt in results:
                    score = score_match(title, excerpt, proj_name, hints)
                    if score > best_score:
                        best_score = score
                        best_match = title
                        best_url = link
                        best_source = site_name
                time.sleep(0.3)
        
        if best_url and best_score >= 20:
            print(f"  MATCH (score={best_score}): {best_match[:130]}")
            print(f"  -> {best_url}")
            updates.append((proj_name, best_url, best_score, best_source))
        else:
            print(f"  NO MATCH (best={best_score}, candidate={best_match[:80] if best_match else 'none'})")
            not_found.append(proj_name)
    
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(updates)} found, {len(not_found)} not found")
    
    # Update Supabase
    if updates:
        table = supabase.table("projects")
        total = 0
        for proj_name, url, score, source in updates:
            resp = table.select("id, source_url").eq("name", proj_name).execute()
            if resp.data:
                for row in resp.data:
                    if not row.get('source_url') or row['source_url'].strip() == '':
                        table.update({"source_url": url}).eq("id", row['id']).execute()
                        total += 1
                        print(f"  DB updated id={row['id']}: {proj_name[:50]} -> {source}")
        print(f"\nTotal DB records updated: {total}")
    
    print(f"\nNot found:")
    for p in not_found:
        print(f"  - {p}")
    print("\nDone.")

