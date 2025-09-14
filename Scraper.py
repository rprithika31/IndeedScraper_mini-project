import argparse, json, os, random, re, time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import pandas as pd
except:
    pd = None

try:
    import requests
    from bs4 import BeautifulSoup
except:
    requests = None; BeautifulSoup = None

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service as ChromeService
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_OK = True
except:
    SELENIUM_OK = False

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/123 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15",
]

def clean_text(s): 
    return re.sub(r"\s+", " ", str(s or "")).strip()

def parse_date_posted(text):
    today = datetime.today().date()
    t = text.lower()
    if "today" in t or "just posted" in t: 
        return str(today)
    m = re.search(r"(\d+)\s*day", t)
    if m: 
        return str(today - timedelta(days=int(m.group(1))))
    return str(today)

def build_search_url(query, location, start=0):
    from urllib.parse import urlencode, quote_plus
    return "https://www.indeed.com/jobs?" + urlencode(
        {"q": query, "l": location, "start": start}, 
        quote_via=quote_plus
    )

def make_driver(headless=True):
    opts = webdriver.ChromeOptions()
    if headless: 
        opts.add_argument("--headless=new")
    opts.add_argument(f"--user-agent={random.choice(UA_POOL)}")
    return webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()), 
        options=opts
    )

def scrape_list_page(driver, url):
    driver.get(url)
    WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.job_seen_beacon"))
    )
    out = []
    for c in driver.find_elements(By.CSS_SELECTOR, "div.job_seen_beacon"):
        def safe(css, attr=None):
            try:
                el = c.find_element(By.CSS_SELECTOR, css)
                return el.get_attribute(attr) if attr else el.text
            except:
                return ""
        link = safe("a", "href")
        if link.startswith("/"): 
            link = "https://www.indeed.com" + link
        out.append({
            "job_title": clean_text(safe("h2.jobTitle")),
            "company": clean_text(safe("span.companyName")),
            "location": clean_text(safe("div.companyLocation")),
            "salary": clean_text(safe("div.metadata.salary-snippet-container")),
            "rating": clean_text(safe("span.ratingsDisplay")),
            "job_description": "",
            "date_posted": parse_date_posted(clean_text(safe("span.date"))),
            "job_url": link
        })
    return out

def fetch_description(url):
    if not (requests and BeautifulSoup): 
        return ""
    try:
        r = requests.get(url, headers={"User-Agent": random.choice(UA_POOL)}, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        node = soup.select_one("#jobDescriptionText")
        return clean_text(node.get_text("\n")) if node else ""
    except:
        return ""

def save_outputs(rows, base):
    if pd:
        pd.DataFrame(rows).to_csv(base + ".csv", index=False, encoding="utf-8")

def run(query, location, pages=1, fetch_desc=False):
    driver = make_driver()
    try:
        rows = []
        for p in range(pages):
            rows.extend(scrape_list_page(driver, build_search_url(query, location, p*10)))
            time.sleep(1)
        if fetch_desc:
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = {ex.submit(fetch_description, r["job_url"]): i for i, r in enumerate(rows)}
                for fut in as_completed(futs):
                    rows[futs[fut]]["job_description"] = fut.result()
        save_outputs(rows, f"indeed_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    finally:
        driver.quit()

if __name__== "__main__":
    run("Python Developer", "Chennai", pages=1, fetch_desc=True)
