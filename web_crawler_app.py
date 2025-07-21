import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import streamlit as st
import pandas as pd

# Setup
st.set_page_config(page_title="Web Crawler", layout="wide")
st.title("🕸️ Web Contact Crawler")

# Input
url_input = st.text_input("Enter the base website URL (e.g. https://example.org)")
max_pages = st.number_input("Max pages to crawl", min_value=1, max_value=100, value=50, step=5)

def normalize_and_validate_phone(phone_str):
    digits = re.sub(r'\D', '', phone_str)
    return phone_str if len(digits) == 10 else ''

def remove_duplicate_words(text):
    seen, result = set(), []
    for w in text.split():
        if w.lower() not in seen:
            seen.add(w.lower())
            result.append(w)
    return " ".join(result)

def extract_contacts_from_html(soup):
    lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    phone_re = re.compile(r"\+?\d{1,4}?[\s\.-]?\(?\d{1,3}\)?[\s\.-]?\d{1,4}[\s\.-]?\d{1,4}[\s\.-]?\d{1,9}")
    name_re = re.compile(r"\b((?:Dr\.|Mr\.|Ms\.|Mrs\.)?\s?[A-Z][a-z]+(?:\s[A-Z]\.)?(?:\s[A-Z][a-z]+)+)\b")

    contacts = []
    for i, line in enumerate(lines):
        emails = email_re.findall(line)
        phones = phone_re.findall(line)
        if not emails and not phones:
            continue

        ctx = " ".join(lines[max(0, i-2):i+3])
        name_m = name_re.search(ctx)
        name = name_m.group(1).strip() if name_m else ""
        phone = normalize_and_validate_phone(phones[0]) if phones else ""
        email = emails[0] if emails else ""
        title = ""

        # Try to detect title
        for l in lines[max(0, i-2):i+3]:
            if any(k in l for k in ["Director", "Manager", "CEO", "Founder", "Professor", "Dr.", "Mr.", "Ms.", "Mrs."]):
                title = l.strip()
                break

        # Clean and require at least 2 fields
        name = remove_duplicate_words(name)
        title = remove_duplicate_words(title)
        if sum(bool(v) for v in [name, title, email, phone]) < 2:
            continue

        contacts.append({"name": name, "title": title, "email": email, "phone": phone})
    return contacts

def crawl_site_for_contacts(start_url, max_pages):
    visited, to_visit = set(), [start_url]
    all_contacts, all_emails = [], set()
    mission = address = donation_info = ""
    recent_events = upcoming_events = []

    pbar = st.progress(0)
    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        visited.add(url)
        st.write(f"Crawling: {url} ({len(visited)}/{max_pages})")

        try:
            r = requests.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
            soup = BeautifulSoup(r.text, "html.parser")

            # Extract contacts and emails
            contacts = extract_contacts_from_html(soup)
            for c in contacts:
                c["source_url"] = url
                if c["email"]:
                    all_emails.add(c["email"].lower())
                if not any(existing["email"] == c["email"] for existing in all_contacts):
                    all_contacts.append(c)

            # Add internal links
            base = urlparse(start_url).netloc
            for a in soup.select("a[href]"):
                full = urljoin(url, a["href"].split("#")[0])
                if urlparse(full).netloc == base and full not in visited:
                    to_visit.append(full)

        except Exception as e:
            st.error(f"Error crawling {url}: {e}")

        pbar.progress(min(len(visited)/max_pages, 1.0))

    return all_contacts, all_emails

if st.button("Start Crawling") and url_input:
    contacts, all_emails = crawl_site_for_contacts(url_input.strip(), max_pages)
    st.success(f"Finished crawling. {len(contacts)} contacts found.")

    # Display
    if contacts:
        df = pd.DataFrame(contacts)
        df["source"] = df["source_url"]
        st.table(df[["name", "title", "email", "phone", "source"]])

        csv = df.to_csv(index=False).encode()
        st.download_button("Download contacts (CSV)", csv, "contacts.csv", "text/csv")
    else:
        st.info("No contacts extracted.")

    used_emails = set(c["email"].lower() for c in contacts if c["email"])
    orphaned = sorted(all_emails - used_emails)
    if orphaned:
        st.subheader("✨ Additional (Orphaned) Emails Found")
        for e in orphaned:
            st.write(e)
