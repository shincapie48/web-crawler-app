import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import streamlit as st
import pandas as pd

def normalize_and_validate_phone(phone_str):
    digits = re.sub(r'\D', '', phone_str)
    return phone_str if len(digits) == 10 else ''

def extract_contacts_and_emails(soup):
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    email_regex = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}')
    phone_regex = re.compile(r'\d{3}[\s\.-]?\d{3}[\s\.-]?\d{4}')
    name_regex = re.compile(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b')

    contacts, found_emails = [], set()

    for i, line in enumerate(lines):
        emails = email_regex.findall(line)
        phones = phone_regex.findall(line)
        if not emails and not phones:
            continue

        found_emails.update(e.lower() for e in emails)

        context = " ".join(lines[max(0, i - 2):i + 3])
        name_match = name_regex.search(context)

        if name_match and emails:
            name = name_match.group().strip()
            email = emails[0]
            phone = ''
            if phones:
                phone = normalize_and_validate_phone(phones[0])
            contacts.append({"name": name, "email": email, "phone": phone})
    
    return contacts, found_emails

def crawl(start_url, max_pages=5):
    visited, to_visit = set(), [start_url]
    all_contacts, all_emails = [], set()

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited: continue
        visited.add(url)

        try:
            r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla"})
            soup = BeautifulSoup(r.text, "html.parser")

            contacts, emails = extract_contacts_and_emails(soup)
            for c in contacts:
                c['source_url'] = url
                if c['email'] not in [d["email"] for d in all_contacts]:
                    all_contacts.append(c)
            all_emails.update(emails)

            base = urlparse(start_url).netloc
            for a in soup.select("a[href]"):
                full = urljoin(url, a["href"].split("#")[0])
                if urlparse(full).netloc == base and full not in visited:
                    to_visit.append(full)
        except:
            continue

    return all_contacts, all_emails

st.title("🕸️ Contact & Email Crawler")

url = st.text_input("Website URL")
if st.button("Run") and url:
    with st.spinner("Crawling..."):
        contacts, found_emails = crawl(url, max_pages=5)

    st.subheader("👥 Contacts Found")
    if contacts:
        for c in contacts:
            st.markdown(f"**[{c['name']}]({c['source_url']})** — {c['email']}  {c['phone'] or ''}")
    else:
        st.write("No contacts found.")

    st.subheader("📬 All Found Emails")
    if found_emails:
        st.write(sorted(found_emails))
    else:
        st.write("No emails found.")
