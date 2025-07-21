import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Web Contact & Info Crawler", layout="wide")
st.title("🕸️ Web Contact & Info Crawler")

url_input = st.text_input("Enter a nonprofit website URL (e.g. https://example.org)")
max_pages = st.slider("Max pages to crawl", 1, 100, 50)

# -- Helper Functions (identical to your working version) --

def normalize_and_validate_phone(phone_str):
    digits = re.sub(r'\D', '', phone_str)
    return phone_str if len(digits) == 10 else ''

def remove_duplicate_words(text):
    seen, result = set(), []
    for w in text.split():
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            result.append(w)
    return " ".join(result)

def extract_contacts_from_html(soup):
    lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    phone_re = re.compile(r"\+?\d{1,4}?[\s.-]?\(?\d{1,3}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,9}")
    name_re = re.compile(
        r"\b((?:Dr\.|Rev\.|Mr\.|Ms\.|Mrs\.)?\s?[A-Z][a-z]+(?:\s[A-Z]\.)?(?:\s[A-Z][a-z]+)+)\b"
    )
    title_keywords = [
        'Director','Manager','Coordinator','Officer','President',
        'CEO','Founder','Chair','Professor','Dr.','Mr.','Ms.','Mrs.'
    ]

    contacts = []
    for i, line in enumerate(lines):
        emails = email_re.findall(line)
        phones = phone_re.findall(line)
        if not (emails or phones):
            continue

        ctx = " ".join(lines[max(0, i-2):i+3])
        name_m = name_re.search(ctx)
        name = name_m.group(1).strip() if name_m else ""
        title = ""
        for ctx_line in lines[max(0, i-2):i+3]:
            if any(k in ctx_line for k in title_keywords):
                title = ctx_line.strip()
                break

        email = emails[0] if emails else ""
        phone = normalize_and_validate_phone(phones[0]) if phones else ""

        name = remove_duplicate_words(name)
        title = remove_duplicate_words(title)
        if sum(bool(v) for v in [name, title, email, phone]) < 2:
            continue

        contacts.append({
            "name": name,
            "title": title,
            "email": email,
            "phone": phone,
            "linkedin": ""
        })
    return contacts

# Additional extractors (mission, events, donation, etc.) – keep as-is

def crawl_site_for_contacts(url, max_pages):
    visited, to_visit = set(), [url]
    contacts, all_emails = [], set()
    mission = address = donation = ""
    recent_events = upcoming_events = []
    progress = st.progress(0)
    steps = 0

    while to_visit and steps < max_pages:
        page = to_visit.pop(0)
        visited.add(page)

        try:
            r = requests.get(page, timeout=5, headers={"User-Agent":"Mozilla/5.0"})
            soup = BeautifulSoup(r.text, "html.parser")

            # Mission, events, donation logic – same as before
            # Contact extraction:
            cs = extract_contacts_from_html(soup)
            for c in cs:
                c["source_url"] = page
                if c["email"]:
                    all_emails.add(c["email"].lower())
                if not any(d["email"] == c["email"] for d in contacts):
                    contacts.append(c)

            base = urlparse(url).netloc
            for a in soup.find_all("a", href=True):
                full = urljoin(page, a["href"].split("#")[0])
                if urlparse(full).netloc == base and full not in visited:
                    to_visit.append(full)

        except:
            pass

        steps += 1
        progress.progress(min(steps / max_pages, 1.0))

    return contacts, all_emails, mission, address, recent_events, upcoming_events, donation

if st.button("Start Crawling") and url_input:
    contacts, all_emails, mission, address, recents, upcoming, donation = crawl_site_for_contacts(url_input.strip(), max_pages)
    st.success(f"Crawling complete — {len(contacts)} contacts found")

    # Display Overview → Events → Contacts → Orphaned Emails
    # (same structure as before)
