# web_crawler_app.py

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import streamlit as st
import pandas as pd

# Normalizes and validates US-like phone numbers
def normalize_and_validate_phone(phone_str):
    digits = re.sub(r'\D', '', phone_str)
    return phone_str if len(digits) == 10 else ''

def remove_duplicate_words(text):
    seen = set()
    result = []
    for word in text.split():
        key = word.lower()
        if key not in seen:
            seen.add(key)
            result.append(word)
    return ' '.join(result)

def extract_contacts_from_html(soup):
    lines = [line.strip() for line in soup.get_text(separator='\n').split('\n') if line.strip()]
    email_regex = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    phone_regex = re.compile(r'\+?\d{1,4}?[\s.-]?\(?\d{1,3}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,9}')
    name_regex = re.compile(r'\b((?:Dr\.|Rev\.|Mr\.|Ms\.|Mrs\.)?\s?[A-Z][a-z]+(?:\s[A-Z]\.)?(?:\s[A-Z][a-z]+)+)\b')
    title_keywords = ['Director', 'Manager', 'Coordinator', 'Officer', 'President', 'CEO', 'Founder', 'Chair', 'Professor', 'Dr.', 'Mr.', 'Ms.', 'Mrs.']
    contacts = []

    for i, line in enumerate(lines):
        emails = email_regex.findall(line)
        phones = phone_regex.findall(line)
        if not (emails or phones):
            continue

        context_lines = lines[max(0, i - 2):min(len(lines), i + 3)]
        context = ' '.join(context_lines)

        name, title = '', ''
        name_match = name_regex.search(context)
        if name_match:
            name = name_match.group(1).strip()

        for ctx_line in context_lines:
            for keyword in title_keywords:
                if keyword in ctx_line:
                    title = ctx_line.strip()
                    break
            if title:
                break

        if name and title and name in title:
            title = title.replace(name, '').strip(',;:- ').strip()
        elif title and not name:
            if ',' in title:
                parts = title.split(',')
                first_part = parts[0].strip()
                if name_regex.match(first_part):
                    name = first_part
                    title = ','.join(parts[1:]).strip()

        email = emails[0] if emails else ''
        phone = ''
        if phones:
            for p in phones:
                validated = normalize_and_validate_phone(p)
                if validated:
                    phone = validated
                    break

        if not (name or title):
            if not (email.lower().startswith('info@') if email else False):
                continue

        cleaned_name = remove_duplicate_words(name)
        cleaned_title = remove_duplicate_words(title)

        contact_info = {
            'name': cleaned_name,
            'title': cleaned_title,
            'email': email,
            'phone': phone,
            'linkedin': ''
        }

        non_empty_fields = sum(bool(v.strip()) for v in contact_info.values() if v != 'linkedin')
        if non_empty_fields >= 2:
            contacts.append(contact_info)

    return contacts

def extract_mission_and_address(soup):
    text = soup.get_text(separator='\n')
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    mission, address = '', ''

    for line in lines:
        if any(keyword in line.lower() for keyword in ['our mission', 'we exist to', 'mission is to']):
            mission = line
            break

    address_regex = re.compile(r'\d{1,6} .+?, [A-Za-z\s]+, [A-Z]{2} \d{5}')
    for line in lines:
        match = address_regex.search(line)
        if match:
            address = match.group()
            break

    return mission, address

def extract_event_summaries(soup):
    text = soup.get_text(separator='\n')
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    recent_events, upcoming_events = [], []

    for i, line in enumerate(lines):
        lower = line.lower()
        if any(k in lower for k in ['recent events', 'past events', 'highlights', 'recap']):
            recent_events.extend(lines[i+1:i+6])
        elif any(k in lower for k in ['upcoming events', 'calendar', 'save the date', 'future events']):
            upcoming_events.extend(lines[i+1:i+6])

    return list(dict.fromkeys([e for e in recent_events if len(e) < 200]))[:5], \
           list(dict.fromkeys([e for e in upcoming_events if len(e) < 200]))[:5]

def extract_linkedin_profiles(soup):
    return [a['href'].strip() for a in soup.find_all('a', href=True)
            if 'linkedin.com/in/' in a['href'] or 'linkedin.com/company/' in a['href']]

def get_internal_links(base_url, soup):
    base_domain = urlparse(base_url).netloc
    return set(
        urljoin(base_url, a['href']).split('#')[0]
        for a in soup.find_all('a', href=True)
        if urlparse(urljoin(base_url, a['href'])).netloc == base_domain
    )

def detect_donation_platform(base_url, soup):
    keywords = ['donate', 'give', 'support']
    known_platforms = ['givecloud', 'givemsmart', 'bloomerang', 'kindful',
                       'raisersedge', "raiser's edge", 'etapestry', 'classy']
    for a in soup.find_all('a', href=True):
        if any(k in a.get_text().lower() or k in a['href'].lower() for k in keywords):
            try:
                res = requests.get(urljoin(base_url, a['href']), timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                if res.status_code == 200:
                    if any(p in res.text.lower() for p in known_platforms):
                        return f"Donation platform detected: {p}"
            except:
                continue
    return "No known donation platform detected."

def crawl_site_for_contacts(start_url, max_pages=50):
    visited, to_visit = set(), [start_url]
    all_contacts, all_emails, seen, linkedin_profiles = [], set(), set(), set()
    mission, address, recent_events, upcoming_events = '', '', [], []
    donation_platform = 'Not checked'

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')

            if not mission or not address:
                m, a = extract_mission_and_address(soup)
                mission, address = m or mission, a or address

            if not recent_events and not upcoming_events:
                recent_events, upcoming_events = extract_event_summaries(soup)

            if donation_platform == 'Not checked':
                donation_platform = detect_donation_platform(start_url, soup)

            linkedin_profiles.update(extract_linkedin_profiles(soup))
            contacts = extract_contacts_from_html(soup)

            for contact in contacts:
                contact['source_url'] = url
                if contact['email']:
                    all_emails.add(contact['email'].lower())

                uid = contact['name'].lower() if contact['name'] else contact['email'].lower()
                if uid not in seen:
                    name_parts = contact['name'].lower().split() if contact['name'] else []
                    for profile in linkedin_profiles:
                        if all(part in profile.lower() for part in name_parts):
                            contact['linkedin'] = profile
                            break
                    all_contacts.append(contact)
                    seen.add(uid)

            to_visit.extend(link for link in get_internal_links(start_url, soup)
                            if link not in visited and len(to_visit) + len(visited) < max_pages)

        except Exception:
            continue

    return all_contacts, mission, address, recent_events, upcoming_events, donation_platform, list(all_emails)

# --- Streamlit UI ---
st.title("🕸️ Web Contact & Info Crawler")
url_input = st.text_input("Enter a nonprofit website URL (e.g. https://example.org)")

if st.button("Start Crawling") and url_input:
    with st.spinner("Crawling site..."):
        contacts, mission, address, recent_events, upcoming_events, donation_platform, all_emails = crawl_site_for_contacts(url_input.strip(), max_pages=5)

    st.subheader("📌 Organization Overview")
    st.write(f"**Mission:** {mission if mission else 'Not Found'}")
    st.write(f"**Address:** {address if address else 'Not Found'}")
    st.write(f"**Donation Platform:** {donation_platform}")

    st.subheader("📅 Recent Events")
    for event in recent_events or ["No recent events found."]:
        st.write(f"- {event}")

    st.subheader("📅 Upcoming Events")
    for event in upcoming_events or ["No upcoming events found."]:
        st.write(f"- {event}")

    if contacts:
        st.subheader(f"👥 {len(contacts)} Contact(s) Found")
        for c in contacts:
            st.markdown(f"""
**Name:** [{c['name']}]({c['source_url']})  
**Title:** {c['title']}  
**Email:** {c['email']}  
**Phone:** {c['phone']}  
**LinkedIn:** [{c['linkedin']}]({c['linkedin']})""" if c['linkedin'] else f"""
**Name:** [{c['name']}]({c['source_url']})  
**Title:** {c['title']}  
**Email:** {c['email']}  
**Phone:** {c['phone']}  
**LinkedIn:** Not Found""")
            st.markdown("---")

        df = pd.DataFrame(contacts)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download Contacts as CSV", csv, "contacts.csv", "text/csv")

    # Show unused emails at the bottom
    used_emails = {c['email'].lower() for c in contacts if c['email']}
    orphaned_emails = sorted(set(all_emails) - used_emails)
    if orphaned_emails:
        st.subheader("📬 Additional Emails Found (Not Part of Contact Cards)")
        for email in orphaned_emails:
            st.write(email)
