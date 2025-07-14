# 🕸️ Web Contact & Info Crawler

This Streamlit app crawls a nonprofit website (up to 50 pages) to extract:

- Contact cards (with name, title, email, phone, LinkedIn, and source URL)
- Organization mission and address
- Recent and upcoming events
- Donation platform detection
- List of all emails found

## How to run locally

```bash
pip install -r requirements.txt
streamlit run web_crawler_app.py
