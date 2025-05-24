import asyncio
import os
import re
import csv
import json
import random
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import html

# ==== GUI ====
category_links = []
PRODUCTS_PER_LINK = 5
output_dir = ""

def start_gui():
    def add_link():
        link = link_entry.get().strip()
        if link:
            links_listbox.insert(tk.END, link)
            link_entry.delete(0, tk.END)

    def browse_dir():
        global output_dir
        output_dir = filedialog.askdirectory()
        if output_dir:
            dir_label.config(text=output_dir)

    def start_scraping():
        global category_links, PRODUCTS_PER_LINK
        category_links = list(links_listbox.get(0, tk.END))
        try:
            PRODUCTS_PER_LINK = int(limit_entry.get())
        except ValueError:
            PRODUCTS_PER_LINK = 100
        if not category_links or not output_dir:
            messagebox.showerror("Error", "Please add category links and select an output directory.")
            return
        root.destroy()

    root = tk.Tk()
    root.title("🧬 Myntra Scraper Configuration")
    root.geometry("620x420")

    tk.Label(root, text="🔗 Enter Category Links:").pack(pady=(10, 2))
    link_entry = tk.Entry(root, width=65)
    link_entry.pack()
    tk.Button(root, text="➕ Add Link", command=add_link).pack(pady=4)
    links_listbox = tk.Listbox(root, width=80, height=6)
    links_listbox.pack()

    tk.Label(root, text="🔢 Products per link:").pack(pady=(10, 2))
    limit_entry = tk.Entry(root)
    limit_entry.insert(0, "100")
    limit_entry.pack()

    tk.Button(root, text="📁 Choose Output Directory", command=browse_dir).pack(pady=8)
    dir_label = tk.Label(root, text="")
    dir_label.pack()

    tk.Button(root, text="🚀 Start Scraping", command=start_scraping).pack(pady=15)

    root.mainloop()

# ==== LISTING SCRAPER ====
async def extract_product_data(product):
    try:
        import datetime, re

        data_id = await product.get_attribute("id")
        a_tag = product.locator('a[data-refreshpage="true"]')
        product_url = "N/A"
        if await a_tag.count() > 0:
            href = await a_tag.get_attribute("href")
            if href:
                product_url = f"https://www.myntra.com/{href}"
                if not data_id:
                    match = re.search(r'/(\d+)/buy$', href)
                    if match:
                        data_id = match.group(1)

        if not data_id:
            print(f"⚠️ Skipping product, missing ID and URL: {product_url}")
            return None

        async def get_text(selector):
            try:
                element = product.locator(selector)
                return await element.inner_text() if await element.count() > 0 else "N/A"
            except:
                return "N/A"

        brand_name = await get_text("h3")
        product_name = await get_text("h4.product-product")

        try:
            rating_element = product.locator(".product-ratingsContainer span").first
            rating = await rating_element.inner_text() if await rating_element.count() > 0 else "N/A"
        except:
            rating = "N/A"

        try:
            rating_count_element = product.locator(".product-ratingsContainer .product-ratingsCount")
            if await rating_count_element.count() > 0:
                raw_text = await rating_count_element.inner_text()
                rating_count = re.sub(r"[^\d]", "", raw_text)
            else:
                rating_count = "N/A"
        except:
            rating_count = "N/A"

        return {
            "Data ID": data_id,
            "Brand Name": brand_name,
            "Product Name": product_name,
            "Product URL": product_url,
            "Rating": rating,
            "Rating Count": rating_count,
            "Date of Extraction": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    except Exception as e:
        print(f"❌ Error extracting product: {e}")
        return None

async def scrape_myntra_link(page, base_url, product_limit):
    all_data, seen_ids = [], set()
    page_num, extracted = 1, 0
    prev_ids = set()

    while extracted < product_limit:
        url = f"{base_url}{'&' if '?' in base_url else '?'}p={page_num}"
        print(f"\n📄 Scraping: {url} (Page {page_num})")

        try:
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_selector("#desktopSearchResults .results-base li", timeout=15000)
            await asyncio.sleep(random.uniform(2.5, 4))
        except Exception as e:
            print(f"❌ Page load failed: {e}")
            break

        products = await page.locator("#desktopSearchResults .results-base li").all()
        if not products:
            print("⚠️ No more products.")
            break

        results = await asyncio.gather(*(extract_product_data(p) for p in products))
        current_ids = set()

        for item in results:
            if item and item["Data ID"] not in seen_ids and extracted < product_limit:
                seen_ids.add(item["Data ID"])
                current_ids.add(item["Data ID"])
                all_data.append(item)
                extracted += 1

        if not current_ids or current_ids == prev_ids:
            print("⛔ Duplicate or no new products. Stopping.")
            break

        prev_ids = current_ids
        page_num += 1

    return all_data


# ==== PDP SCRAPER ====
async def extract_pdp_data(page, url):
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_selector("#mountRoot", timeout=20000)
        await asyncio.sleep(2)

        async def safe_html(selector):
            try:
                el = page.locator(selector)
                return await el.first.inner_html() if await el.count() > 0 else ""
            except Exception:
                return ""

        async def safe_text(selector):
            try:
                el = page.locator(selector)
                return await el.first.inner_text() if await el.count() > 0 else ""
            except Exception:
                return ""

        # Product Name from PDP
        product_name = await safe_text("h1.pdp-name")

        # ✅ Extract plain text description as a list with one item
        raw_details_text = await safe_text("p.pdp-product-description-content")
        parsed_details = [raw_details_text] if raw_details_text else []

        # Material & Care / Size & Fit
        material_care = size_fit = ""
        desc_blocks = await page.locator("div.pdp-sizeFitDesc").all()
        for block in desc_blocks:
            try:
                title = await block.locator("h4.pdp-sizeFitDescTitle").text_content()
                content = await block.locator("p.pdp-sizeFitDescContent").text_content()
                if "Material & Care" in title:
                    material_care = content
                elif "Size & Fit" in title:
                    size_fit = content
            except:
                continue

        # 🔓 Click "See More" if available in Specifications
        try:
            see_more_button = page.locator("div.index-showMoreText")
            if await see_more_button.count() > 0:
                await see_more_button.click()
                await asyncio.sleep(1)
        except Exception as e:
            print(f"⚠️ Could not click See More: {e}")

        # 📋 Extract key-value pairs from specifications table
        specs = {}
        spec_rows = await page.locator("div.index-tableContainer > div.index-row").all()
        for row in spec_rows:
            try:
                key = await row.locator("div.index-rowKey").text_content()
                value = await row.locator("div.index-rowValue").text_content()
                if key and value:
                    specs[key.strip()] = value.strip()
            except Exception:
                continue

        # 💰 Extract offer details if available
        best_price = ""
        try:
            offer_container = page.locator("div.pdp-offers-offer")
            if await offer_container.count() > 0:
                best_price = await offer_container.inner_text()
        except Exception as e:
            print(f"⚠️ Offer extraction failed: {e}")

        # 💸 Extract Price, Original Price, Discount
        try:
            price = await safe_text("span.pdp-price strong")
            original_price = await safe_text("span.pdp-mrp s")
            discount = await safe_text("span.pdp-discount")

            price = price.replace("Rs.", "₹").replace("₹", "").strip()
            price = f"₹{price}" if price else "N/A"

            original_price = original_price.replace("Rs.", "₹").replace("₹", "").strip()
            original_price = f"₹{original_price}" if original_price else "N/A"

            discount = discount.strip() if discount else "N/A"
        except Exception:
            price = original_price = discount = "N/A"

        return {
            "Product URL": url,
            "Product Name (PDP)": product_name,
            "Product Details": parsed_details,
            "Size & Fit": size_fit,
            "Material & Care": material_care,
            "Offer Details": best_price,
            "Price (INR)": price,
            "Original Price (INR)": original_price,
            "Discount": discount,
            **specs  # Flatten the specifications into the top-level dictionary
        }

    except Exception as e:
        print(f"❌ PDP error for {url}: {e}")
        return {}



# ==== RUNNER ====
async def run_all():
    start_gui()
        
    os.makedirs(output_dir, exist_ok=True)
    total_listing_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        for link in category_links:
            print(f"🔗 Scraping: {link}")
            data = await scrape_myntra_link(page, link, PRODUCTS_PER_LINK)
            total_listing_data.extend(data)

        if not total_listing_data:
            print("❌ No listing data found.")
            return

        # Save listing
# Save listing as JSON
        listing_path = os.path.join(output_dir, "myntra_listing.json")
        with open(listing_path, "w", encoding="utf-8") as f:
            json.dump(total_listing_data, f, indent=4, ensure_ascii=False)
            print(f"💾 Saved listing data: {listing_path}")

        # PDP enrichment
        enriched_data = []
        for i, item in enumerate(total_listing_data):
            pdp = await extract_pdp_data(page, item["Product URL"])
            item.update(pdp)
            enriched_data.append(item)
            if i % 10 == 0 or i == len(total_listing_data) - 1:
                print(f"🔄 PDP processed: {i + 1}/{len(total_listing_data)}")
            await asyncio.sleep(1)  # prevent overloading

        # Dynamic fieldnames
        all_fieldnames = set()
        for row in enriched_data:
            all_fieldnames.update(row.keys())
        all_fieldnames = list(all_fieldnames)

        for row in enriched_data:
            for key in all_fieldnames:
                row.setdefault(key, "")

        # Final save
        # Final save as JSON
    final_path = os.path.join(output_dir, "myntra_enriched.json")
    with open(final_path, "w", encoding="utf-8") as f:
        json.dump(enriched_data, f, indent=4, ensure_ascii=False)
        print(f"✅ Final enriched data saved: {final_path}")


# ==== ENTRY POINT ====
if __name__ == "__main__":
    asyncio.run(run_all())
