import time
import tkinter as tk
from tkinter import messagebox
import asyncio
from playwright.async_api import async_playwright
import json
import csv
import random
import datetime
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime as dt

# Output directories
SAVE_DIR = r"FULL SCAPES\saved_data\Flipkart Data"
PDP_ERROR_LOG = os.path.join(SAVE_DIR, "flipkart_pdp_errors.log")
PDP_OUTPUT_JSON = os.path.join(SAVE_DIR, "flipkart_full_Data.json")
PDP_OUTPUT_CSV = os.path.join(SAVE_DIR, "flipkart_full_Data.csv")

os.makedirs(SAVE_DIR, exist_ok=True)

flipkart_links = []

# ----------------------------- GUI Section -----------------------------
def submit_link():
    link = entry.get().strip()
    if link:
        if len(flipkart_links) < 3:
            flipkart_links.append(link)
            listbox.insert(tk.END, link)
            entry.delete(0, tk.END)
            if len(flipkart_links) == 3:
                messagebox.showinfo("Done", "Collected 3 links!")
                entry.config(state='disabled')
                submit_button.config(state='disabled')
        else:
            messagebox.showwarning("Limit reached", "Already collected 3 links.")

def run_gui():
    global root, entry, submit_button, listbox

    root = tk.Tk()
    root.title("Flipkart Link Collector")
    root.geometry("720x720")

    label = tk.Label(root, text="Enter Flipkart Link:", font=("Arial", 12))
    label.pack(pady=10)

    entry = tk.Entry(root, width=60)
    entry.pack(pady=5)

    submit_button = tk.Button(root, text="Submit", command=submit_link)
    submit_button.pack(pady=5)

    listbox_label = tk.Label(root, text="Collected Links:", font=("Arial", 10, "bold"))
    listbox_label.pack(pady=10)

    listbox = tk.Listbox(root, width=60, height=10)
    listbox.pack(pady=5)

    root.mainloop()

# ----------------------------- Step 1: Listing Scraper -----------------------------
PAGES_PER_LINK = 1  # You can increase this if needed

async def scrape_flipkart_link(page, base_url, max_pages=PAGES_PER_LINK):
    data = []
    for page_num in range(1, max_pages + 1):
        url = f"{base_url}&page={page_num}"
        try:
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_selector("[data-id]", timeout=20000)
            await asyncio.sleep(random.uniform(2.5, 4.5))
        except Exception as e:
            print(f"⚠️ Failed to load page {url}: {e}")
            continue

        products = await page.locator("[data-id]").all()
        for product in products:
            try:
                data_id = await product.get_attribute("data-id") or "N/A"
                container = product.locator('div._1sdMkc.LFEi7Z')
                await container.wait_for(timeout=10000)
                if not await container.is_visible():
                    continue

                brand_name = await container.locator('div.hCKiGj div.syl9yP').text_content() or "N/A"
                name_element = container.locator('div.hCKiGj a.WKTcLC')
                product_name = await name_element.text_content() if await name_element.is_visible() else "N/A"
                product_url = "https://www.flipkart.com" + (await name_element.get_attribute("href") or "#") if product_name != "N/A" else "N/A"

                item = {
                    "Data ID": data_id,
                    "Brand Name": brand_name.strip(),
                    "Product Name": product_name.strip(),
                    "Product URL": product_url,
                }
                data.append(item)

            except Exception as e:
                # silently skip problematic products
                continue
    return data

async def run_listing_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        all_data = []
        for link in flipkart_links:
            print(f"🔍 Scraping listings from: {link}")
            data = await scrape_flipkart_link(page, link, max_pages=PAGES_PER_LINK)
            all_data.extend(data)
            print(f"➡️ Found {len(data)} products on this link.")

        await browser.close()

        if all_data:
            json_path = os.path.join(SAVE_DIR, "flipkart_listing_data.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(all_data, f, indent=4)

            csv_path = os.path.join(SAVE_DIR, "flipkart_listing_data.csv")
            with open(csv_path, "w", newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=all_data[0].keys())
                writer.writeheader()
                writer.writerows(all_data)

        return all_data

# ----------------------------- Step 2: PDP Scraper -----------------------------
HEADERS_LIST = [
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0"},
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15"},
    {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"},
]

def extract_pdp_data(soup, url):
    try:
        brand = soup.select_one("span.mEh187")
        name = soup.select_one("span.VU-ZEz")
        price = soup.select_one("div.Nx9bqj")
        original_price = soup.select_one("div.yRaY8j")
        discount = soup.select_one("div.UkUFwK span")
        rating_div = soup.select_one("span.Y1HWO0 div.XQDdHH")
        rating_text = rating_div.text.strip() if rating_div else None
        rating_count = soup.select_one("span.Wphh3N span")

        sizes = []
        size_blocks = soup.select("ul.hSEbzK li")
        for li in size_blocks:
            size_text = li.select_one("a")
            detail = li.select_one("div.V3Zflw")
            if size_text and detail:
                sizes.append(f"{size_text.text.strip()}: {detail.text.strip()}")

        seller = soup.select_one("div#sellerName span span")
        seller_rating = soup.select_one("div.XQDdHH.uuhqql")
        seller_name = seller.text.strip() if seller else None
        seller_rating_text = seller_rating.text.strip() if seller_rating else None

        specs = {}
        spec_rows = soup.select("div.Cnl9Jt div._5Pmv5S div.row")
        for row in spec_rows:
            key_div = row.select_one("div.col.col-3-12")
            val_div = row.select_one("div.col.col-9-12")
            if key_div and val_div:
                specs[key_div.text.strip()] = val_div.text.strip()

        descriptions = []
        desc_blocks = soup.select("div.pqHCzB > div")
        for block in desc_blocks:
            img_div = block.select_one("div._0B07y7 img")
            img_url = img_div["src"].strip() if img_div and "src" in img_div.attrs else None
            title_div = block.select_one("div._9GQWrZ")
            para = block.select_one("div.AoD2-N p")
            descriptions.append({
                "Image URL": img_url,
                "Title": title_div.text.strip() if title_div else None,
                "Text": para.text.strip() if para else None
            })

        flat_blocks = soup.select("div._9GQWrZ")
        for title_div in flat_blocks:
            parent = title_div.find_parent()
            para = parent.select_one("div.AoD2-N p") if parent else None
            if title_div and para:
                descriptions.append({
                    "Image URL": None,
                    "Title": title_div.text.strip(),
                    "Text": para.text.strip()
                })

        reviews_section = soup.select_one("a[href*='/product-reviews/'] div._23J90q.iIbIvC span._6n9Uuq")
        review_summary = reviews_section.text.strip() if reviews_section else None
        review_link_tag = soup.select_one("a[href*='/product-reviews/']:has(div._23J90q.iIbIvC)")
        review_link = f"https://www.flipkart.com{review_link_tag['href'].strip()}" if review_link_tag and 'href' in review_link_tag.attrs else None

        return {
            "Product URL": url,
            "Brand Name": brand.text.strip() if brand else None,
            "Product Name": name.text.strip() if name else None,
            "Price (INR)": price.text.strip() if price else None,
            "Original Price (INR)": original_price.text.strip() if original_price else None,
            "Discount": discount.text.strip() if discount else None,
            "Rating": rating_text,
            "Rating Count": rating_count.text.strip() if rating_count else None,
            "Sizes": sizes,
            "Seller Name": seller_name,
            "Seller Rating": seller_rating_text,
            "Specifications": specs,
            "Description Cards": descriptions,
            "All Reviews Summary": review_summary,
            "All Reviews Link": review_link,
            "Date of Extraction": dt.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    except Exception as e:
        log_pdp_error(url, f"Parsing error: {e}")
        return None

def log_pdp_error(url, error):
    with open(PDP_ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"{dt.now()} - {url} - {error}\n")

def scrape_pdp(urls):
    scraped_data = []
    for idx, url in enumerate(urls):
        headers = random.choice(HEADERS_LIST)
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code != 200:
                log_pdp_error(url, f"Status code: {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            data = extract_pdp_data(soup, url)
            if data:
                scraped_data.append(data)

            if (idx + 1) % 10 == 0:
                print(f"✅ Scraped {idx+1}/{len(urls)} PDPs")

            time.sleep(random.uniform(1.5, 3.0))

        except Exception as e:
            log_pdp_error(url, str(e))
            continue

    return scraped_data

def save_json(data, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def save_csv(data, filepath):
    if not data:
        print("No data to save to CSV.")
        return
    keys = sorted(data[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

# ----------------------------- Main Program -----------------------------
def main():
    # Run GUI first to collect links
    run_gui()

    if not flipkart_links:
        print("No Flipkart links provided. Exiting.")
        return

    # Run Playwright listing scraper
    print(f"Starting Playwright listing scraping for {len(flipkart_links)} links...")
    listing_data = asyncio.run(run_listing_scraper())

    if not listing_data:
        print("No listing data scraped. Exiting.")
        return

    print(f"Total listing products scraped: {len(listing_data)}")

    # Extract all product URLs for PDP scraping
    product_urls = [item["Product URL"] for item in listing_data if item.get("Product URL") and item["Product URL"] != "N/A"]
    product_urls = list(set(product_urls))  # Unique URLs

    print(f"Starting PDP scraping for {len(product_urls)} unique product URLs...")

    pdp_results = scrape_pdp(product_urls)

    print(f"PDP scraping done. Total products scraped: {len(pdp_results)}")

    # Save PDP results
    save_json(pdp_results, PDP_OUTPUT_JSON)
    save_csv(pdp_results, PDP_OUTPUT_CSV)

    print(f"Data saved to:\n  JSON: {PDP_OUTPUT_JSON}\n  CSV: {PDP_OUTPUT_CSV}")

if __name__ == "__main__":
    main()
