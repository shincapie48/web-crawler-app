import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import streamlit as st
import pandas as pd

# Page Setup
st.set_page_config(page_title="Web Contact & Info Crawler", layout="wide")
st.title("🕸️ Web Contact & Info Crawler")

# User Inputs
url_input = st.text_input("Enter a nonprofit website URL (e.g. https://example.org)")
max_pages = st.slider("Max pages to crawl", 1, 100, 50)

# Helper Functions
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
    phone_re = re.compile(r"\+?\d{1,4}?[\s\.-]?\(?\d{1,3}\)?[\s\.-]?\d{1,4}[\s\.-]?\d{1,4}[\s\.-]\d{1,9}")
    name_re = re.compile(r"\b((?:Dr\.|Rev\.|Mr\.|Ms\.|Mrs\.)?\s?[A-Z][a-z]+(?:\s[A-Z]\.)?(?:\s[A-Z][a-z]+)+)\b")
    title_keywords = ['Director','Manager','Coordinator','Officer','President','CEO','Founder','Chair','Professor','Dr.','Mr.','Ms.','Mrs.']

    contacts = []
    for i, line in enumerate(lines):
        emails = email_re.findall(line)
        phones = phone_re.findall(line)
        if not emails and not phones:
            continue

        ctx_lines = lines[max(0, i-2): i+3]
        ctx = " ".join(ctx_lines)
        name_m = name_re.search(ctx)
        name = name_m.group(1).strip() if name_m else ""
        title = ""
        for ctx_line in ctx_lines:
            if any(k in ctx_line for k in title_keywords):
                title = ctx_line.strip()
                break

        email = emails[0] if emails else ""
        phone = normalize_and_validate_phone(phones[0]) if phones else ""
        name = remove_duplicate_words(name)
        title = remove_duplicate_words(title)

        if sum(bool(v) for v in [name, title, email, phone]) < 2:
            continue

        contacts.append({"name": name, "title": title, "email": email, "phone": phone, "linkedin": ""})

    return contacts

def extract_mission_and_address(soup):
    lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]
    mission = next((l for l in lines if any(k in l.lower() for k in ["our mission", "we exist to", "mission is to"])), "")
    addr = ""
    addr_re = re.compile(r"\d{1,6} .+?, [A-Za-z\s]+, [A-Z]{2} \d{5}")
    for l in lines:
        m = addr_re.search(l)
        if m:
            addr = m.group()
            break
    return mission, addr

def extract_event_summaries(soup):
    lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]
    recent, upcoming = [], []
    for i, l in enumerate(lines):
        lo = l.lower()
        if any(k in lo for k in ["recent events", "past events", "highlights", "recap"]):
            recent.extend(lines[i+1:i+6])
        elif any(k in lo for k in ["upcoming events", "calendar", "save the date", "future events"]):
            upcoming.extend(lines[i+1:i+6])
    return list(dict.fromkeys([e for e in recent if len(e) < 200]))[:5], list(dict.fromkeys([e for e in upcoming if len(e) < 200]))[:5]

def extract_linkedin_profiles(soup):
    return [a['href'] for a in soup.find_all("a", href=True) if "linkedin.com/in/" in a['href'] or "linkedin.com/company/" in a['href']]

def get_internal_links(start_url, soup):
    base = urlparse(start_url).netloc
    return set(urljoin(start_url, a['href'].split("#")[0]) for a in soup.find_all("a", href=True) if urlparse(urljoin(start_url, a['href'])).netloc == base)

def detect_donation_platform(base_url, soup):
    platforms = ['givecloud','givemsmart','bloomerang','kindful','raisersedge',"etapestry","classy"]
    for a in soup.find_all("a", href=True):
        if any(k in (a.get_text().lower() + a['href'].lower()) for k in ["donate","support","give"]):
            try:
                r = requests.get(urljoin(base_url, a['href']), timeout=5)
                txt = r.text.lower()
                for p in platforms:
                    if p in txt:
                        return f"Donate via {p}"
            except: pass
    return "Not detected"

# Crawl Function
def crawl_site_for_contacts(url, max_pages):
    visited, to_visit = set(), [url]
    contacts, emails = [], set()
    mission = address = donation = ""
    recent_events = upcoming_events = []
    progress = st.progress(0)

    for step in range(min(max_pages, len(to_visit))):
        if not to_visit: break
        page = to_visit.pop(0)
        visited.add(page)

        try:
            r = requests.get(page, timeout=5, headers={"User-Agent":"Mozilla/5.0"})
            soup = BeautifulSoup(r.text, "html.parser")

            if not mission or not address:
                m, addr = extract_mission_and_address(soup)
                mission, address = m or mission, addr or address

            if not recent_events and not upcoming_events:
                recent_events, upcoming_events = extract_event_summaries(soup)

            if not donation:
                donation = detect_donation_platform(page, soup)

            for link in extract_linkedin_profiles(soup):
                pass

            cs = extract_contacts_from_html(soup)
            for c in cs:
                c["source_url"] = page
                if c["email"]:
                    emails.add(c["email"].lower())
                if not any(d["email"] == c["email"] for d in contacts):
                    contacts.append(c)

            for link in get_internal_links(url, soup):
                if link not in visited:
                    to_visit.append(link)

        except Exception:
            pass

        progress.progress((step + 1) / max_pages)

    return contacts, emails, mission, address, recent_events, upcoming_events, donation

# Run & Display
if st.button("Start Crawling") and url_input:
    contacts, all_emails, mission, address, recents, upcoming, donation = crawl_site_for_contacts(url_input.strip(), max_pages)
    st.success(f"Crawling complete — {len(contacts)} contacts found")

    st.subheader("📌 Overview")
    st.write(f"**Mission:** {mission or 'Not found'}")
    st.write(f"**Address:** {address or 'Not found'}")
    st.write(f"**Donation Platform:** {donation or 'Not detected'}")

    st.subheader("📅 Recent Events")
    for e in recents or ["No recent events found"]: st.write(f"- {e}")

    st.subheader("📅 Upcoming Events")
    for e in upcoming or ["No upcoming events found"]: st.write(f"- {e}")

    if contacts:
        st.subheader(f"👥 {len(contacts)} Contacts")
        for c in contacts:
            linkedin = f"[LinkedIn]({c['linkedin']})" if c.get("linkedin") else "Not found"
            st.markdown(f"""
**Name:** [{c['name']}]({c['source_url']})  
**Title:** {c['title']}  
**Email:** {c['email']}  
**Phone:** {c['phone']}  
**LinkedIn:** {linkedin}
""")
            st.markdown("---")
        df = pd.DataFrame(contacts)
        st.download_button("⬇️ Download CSV", df.to_csv(index=False), "contacts.csv", "text/csv")
    else:
        st.info("No contacts found.")

    used_emails = {c["email"].lower() for c in contacts if c["email"]}
    orphaned = sorted(all_emails - used_emails)
    if orphaned:
        st.subheader("📬 Orphaned Emails")
        for e in orphaned: st.write(e)
