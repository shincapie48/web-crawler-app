import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import streamlit as st
import pandas as pd

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
    title_keywords = ['Director', 'Manager', 'Coordinator', 'Officer', 'President',
                      'CEO', 'Founder', 'Chair', 'Professor', 'Dr.', 'Mr.', 'Ms.', 'Mrs.']

    contacts = []

    for i, line in enumerate(lines):
        emails = email_regex.findall(line)
        phones = phone_regex.findall(line)
        if not (emails or phones):
            continue

        context_lines = lines[max(0, i - 2):min(len(lines), i + 3)]
        context = ' '.join(context_lines)

        name = ''
        name_match = name_regex.search(context)
        if name_match:
            name = name_match.group(1).strip()

        title = ''
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

    mission = ''
    for line in lines:
        if any(keyword in line.lower() for keyword in ['our mission', 'we exist to', 'mission is to']):
            mission = line
            break

    address_regex = re.compile(r'\d{1,6} .+?, [A-Za-z\s]+, [A-Z]{2} \d{5}')
    address = ''
    for line in lines:
        match = address_regex.search(line)
        if match:
            address = match.group()
            break

    return mission, address

def extract_event_summaries(soup):
    text = soup.get_text(separator='\n')
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    recent_keywords = ['recent events', 'past events', 'highlights', 'recap']
    upcoming_keywords = ['upcoming events', 'calendar', 'save the date', 'future events']

    recent_events = []
    upcoming_events = []

    for i, line in enumerate(lines):
        lower = line.lower()
        if any(kw in lower for kw in recent_keywords):
            recent_events.extend(lines[i+1:i+6])
        elif any(kw in lower for kw in upcoming_keywords):
            upcoming_events.extend(lines[i+1:i+6])

    recent_events = list(dict.fromkeys([e for e in recent_events if len(e) < 200]))
    upcoming_events = list(dict.fromkeys([e for e in upcoming_events if len(e) < 200]))

    return recent_events[:5], upcoming_events[:5]

def extract_linkedin_profiles(soup):
    links = []
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if 'linkedin.com/in/' in href or 'linkedin.com/company/' in href:
            links.append(href.strip())
    return links

def get_internal_links(base_url, soup):
    base_domain = urlparse(base_url).netloc
    links = set()
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.netloc == base_domain and parsed.scheme in ['http', 'https']:
            links.add(full_url.split('#')[0])
    return links

def detect_donation_platform(base_url, soup):
    donation_keywords = ['donate', 'give', 'support']
    donation_links = []

    for a_tag in soup.find_all('a', href=True):
        text = a_tag.get_text().lower()
        href = a_tag['href'].lower()
        if any(word in text or word in href for word in donation_keywords):
            full_url = urljoin(base_url, a_tag['href'])
            donation_links.append(full_url)

    known_platforms = ['givecloud', 'givemsmart', 'bloomerang', 'kindful',
                       'raisersedge', "raiser's edge", 'etapestry', 'classy']

    for link in donation_links:
        try:
            res = requests.get(link, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            res.raise_for_status()
            page_text = res.text.lower()
            for platform in known_platforms:
                if platform in page_text:
                    return f"Donation platform detected: {platform}"
        except requests.RequestException:
            continue

    return "No known donation platform detected."

def crawl_site_for_contacts(start_url, max_pages=50):
    visited = set()
    to_visit = [start_url]
    all_contacts = []
    seen = set()
    mission = ''
    address = ''
    linkedin_profiles = set()
    recent_events = []
    upcoming_events = []
    donation_platform = 'Not checked'
    all_emails = set()

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            if not mission or not address:
                m, a = extract_mission_and_address(soup)
                if m:
                    mission = m
                if a:
                    address = a

            if not recent_events and not upcoming_events:
                recents, upcomings = extract_event_summaries(soup)
                if recents:
                    recent_events = recents
                if upcomings:
                    upcoming_events = upcomings

            if donation_platform == 'Not checked':
                donation_platform = detect_donation_platform(start_url, soup)

            linkedin_profiles.update(extract_linkedin_profiles(soup))

            contacts = extract_contacts_from_html(soup)
            for contact in contacts:
                contact['source_url'] = url  # Add source page URL

                # Collect emails separately
                if contact['email']:
                    all_emails.add(contact['email'].lower())

                unique_id = contact['name'].lower() if contact['name'] else contact['email'].lower()
                if unique_id not in seen:
                    name_parts = contact['name'].lower().split() if contact['name'] else []
                    for profile_url in linkedin_profiles:
                        if all(part in profile_url.lower() for part in name_parts):
                            contact['linkedin'] = profile_url
                            break

                    all_contacts.append(contact)
                    seen.add(unique_id)

            internal_links = get_internal_links(start_url, soup)
            for link in internal_links:
                if link not in visited and len(visited) + len(to_visit) < max_pages:
                    to_visit.append(link)

        except requests.RequestException:
            continue

    return all_contacts, mission, address, recent_events, upcoming_events, donation_platform, list(all_emails)

# --- Streamlit Front End ---
st.title("🕸️ Web Contact & Info Crawler")

url_input = st.text_input("Enter the base website URL (e.g. https://example.org)")

if st.button("Start Crawling") and url_input:
    with st.spinner("Crawling website... (this may take some time)"):
        contacts, mission, address, recent_events, upcoming_events, donation_platform, all_emails = crawl_site_for_contacts(url_input.strip(), max_pages=50)

    st.subheader("📌 Organization Overview")
    st.write(f"**Mission:** {mission if mission else 'Not Found'}")
    st.write(f"**Address:** {address if address else 'Not Found'}")
    st.write(f"**Donation Platform:** {donation_platform}")

    st.subheader("📅 Recent Events")
    if recent_events:
        for event in recent_events:
            st.write(f"- {event}")
    else:
        st.write("No recent events found.")

    st.subheader("📅 Upcoming Events")
    if upcoming_events:
        for event in upcoming_events:
            st.write(f"- {event}")
    else:
        st.write("No upcoming events found.")

    if all_emails:
        st.subheader("📬 All Emails Found")
        for email in all_emails:
            st.write(email)

    if contacts:
        st.subheader(f"👥 Extracted {len(contacts)} Contact(s)")
        for c in contacts:
            if c['linkedin']:
                linkedin_md = f"[LinkedIn]({c['linkedin']})"
            else:
                linkedin_md = "Not Found"

            source_md = f"[Source page]({c['source_url']})" if c.get('source_url') else "Unknown"

            st.markdown(f"""
            **Name:** [{c['name']}]({c['source_url']})  
            **Title:** {c['title']}  
            **Email:** {c['email']}  
            **Phone:** {c['phone']}  
            **LinkedIn:** {linkedin_md}  
            **Found on:** {source_md}
            """)
            st.markdown("---")

        # Export contacts CSV
        df = pd.DataFrame(contacts)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Download Contacts as CSV",
            data=csv,
            file_name='contacts.csv',
            mime='text/csv'
        )
