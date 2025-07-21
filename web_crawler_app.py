import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import streamlit as st
import pandas as pd

# Streamlit config
st.set_page_config(page_title="Web Contact & Info Crawler", layout="wide")
st.title("🕸️ Web Contact & Info Crawler")

# Input
url_input = st.text_input("Enter a nonprofit website URL (e.g. https://example.org)")
max_pages = st.slider("Max pages to crawl", 1, 100, 50)

def normalize_phone(p): ...
def remove_dupes(t): ...
# (Insert your full existing helper functions here: mission, events, linkedin, etc.)

# Compact crawler without visible logs
def crawl_site_for_contacts(url, max_pages):
    visited, to_visit = set(), [url]
    contacts, emails = [], set()
    mission = address = donation = ""
    recent_events = upcoming_events = []
    
    pbar = st.progress(0)
    steps = 0
    while to_visit and steps < max_pages:
        page = to_visit.pop(0)
        visited.add(page)
        try:
            r = requests.get(page, timeout=10, headers={"User-Agent":"Mozilla"})
            soup = BeautifulSoup(r.text, "html.parser")
            
            m, a = extract_mission_and_address(soup)
            if m: mission = m
            if a: address = a
            
            rec, up = extract_event_summaries(soup)
            if rec: recent_events = rec
            if up: upcoming_events = up
            
            if donation == "":
                donation = detect_donation_platform(page, soup)
            
            for link in extract_linkedin_profiles(soup):
                pass  # (use as needed)
            
            cs = extract_contacts_from_html(soup)
            for c in cs:
                c["source_url"] = page
                if c["email"]:
                    emails.add(c["email"].lower())
                if not any(d["email"] == c["email"] for d in contacts):
                    contacts.append(c)

            base = urlparse(url).netloc
            for a in soup.select("a[href]"):
                full = urljoin(page, a["href"].split("#")[0])
                if urlparse(full).netloc == base and full not in visited and len(to_visit) + steps < max_pages:
                    to_visit.append(full)
        except:
            pass
        
        steps += 1
        pbar.progress(min(steps / max_pages, 1.0))
    return contacts, emails, mission, address, recent_events, upcoming_events, donation

if st.button("Start Crawling") and url_input:
    contacts, all_emails, mission, address, recents, upcoming, donation = crawl_site_for_contacts(url_input, max_pages)
    st.success("✅ Crawling complete")

    st.subheader("📌 Organization Overview")
    st.write(f"**Mission:** {mission or 'Not Found'}")
    st.write(f"**Address:** {address or 'Not Found'}")
    st.write(f"**Donation Platform:** {donation or 'None detected'}")

    st.subheader("📅 Recent Events")
    if recents:
        for e in recents: st.write(f"- {e}")
    else: st.write("- No recent events found")

    st.subheader("📅 Upcoming Events")
    if upcoming:
        for e in upcoming: st.write(f"- {e}")
    else: st.write("- No upcoming events found")

    if contacts:
        st.subheader(f"👥 {len(contacts)} Contact(s) Found")
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
        st.download_button("⬇️ Download Contacts as CSV", df.to_csv(index=False), "contacts.csv")
    else:
        st.info("No contacts found.")

    used = {c["email"].lower() for c in contacts}
    orphaned = sorted(all_emails - used)
    if orphaned:
        st.subheader("📬 Additional Emails Found (Not in Contact Cards)")
        for e in orphaned: st.write(e)
