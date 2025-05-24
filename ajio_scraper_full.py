import asyncio
import random
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import datetime
import json
import csv
import os
import tkinter as tk
from tkinter import filedialog, messagebox



# ----------------------------------------
# HEADERS / USER AGENTS
# ----------------------------------------
HEADERS_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
]



# ----------------------------------------
# GUI SECTION
# ----------------------------------------
def launch_gui():
    ajio_links = []
    output_dir = ""
    max_products = 5

    def browse_dir():
        path = filedialog.askdirectory()
        if path:
            output_entry.delete(0, tk.END)
            output_entry.insert(0, path)

    def submit():
        nonlocal ajio_links, output_dir, max_products
        links_raw = links_text.get("1.0", tk.END).strip()
        ajio_links = [link.strip() for link in links_raw.splitlines() if link.strip()]
        output_dir = output_entry.get().strip()
        try:
            max_products = int(max_products_entry.get().strip())
            if max_products <= 0:
                raise ValueError()
        except:
            messagebox.showerror("Invalid Input", "Please enter a valid positive integer for max products.")
            return

        if not ajio_links or not output_dir:
            messagebox.showerror("Missing Input", "Please provide both links and output directory.")
            return
        root.destroy()

    root = tk.Tk()
    root.title("Ajio Scraper Input")

    tk.Label(root, text="Enter Ajio Category URLs (one per line):").pack(anchor="w", padx=10, pady=(10, 0))
    links_text = tk.Text(root, height=8, width=80)
    links_text.pack(padx=10)

    tk.Label(root, text="Select Output Directory:").pack(anchor="w", padx=10, pady=(10, 0))
    frame_dir = tk.Frame(root)
    frame_dir.pack(padx=10, fill='x')
    output_entry = tk.Entry(frame_dir, width=60)
    output_entry.pack(side=tk.LEFT, fill='x', expand=True)
    tk.Button(frame_dir, text="Browse", command=browse_dir).pack(side=tk.LEFT, padx=5)

    tk.Label(root, text="Max Products per Link:").pack(anchor="w", padx=10, pady=(10, 0))
    max_products_entry = tk.Entry(root, width=10)
    max_products_entry.insert(0, "5")
    max_products_entry.pack(anchor="w", padx=10)

    tk.Button(root, text="Start Scraping", command=submit).pack(pady=15)

    root.mainloop()

    return ajio_links, output_dir, max_products

# ----------------------------------------
# HELPER FUNCTION: Safe text extraction
# ----------------------------------------
async def safe_text(locator, timeout=1500):
    try:
        text = await locator.text_content(timeout=timeout)
        if text:
            return text.strip()
        return "N/A"
    except PlaywrightTimeoutError:
        return "N/A"
    except Exception:
        return "N/A"


# ----------------------------------------
# LISTING SCRAPER
# ----------------------------------------
async def extract_product_details(product, index):
    try:
        data_id = await product.get_attribute("data-id") or f"AJIO_{index + 1}"

        brand_name = await safe_text(product.locator('.brand'))
        product_name = await safe_text(product.locator('.nameCls'))
        rating = await safe_text(product.locator('._1gIWf ._3I65V'))
        rating_count = await safe_text(product.locator('p[aria-label*="|"]'))
        price = await safe_text(product.locator('.price strong'))
        original_price = await safe_text(product.locator('.orginal-price'))
        discount = await safe_text(product.locator('.discount'))

        try:
            visible = await product.locator('.exclusive-new').is_visible(timeout=1000)
        except Exception:
            visible = False

        bestseller = "Yes" if visible else "No"

        product_url_raw = await product.locator("a").get_attribute("href")
        if product_url_raw and product_url_raw.startswith("/"):
            product_url = f"https://www.ajio.com{product_url_raw}"
        else:
            product_url = product_url_raw or "N/A"

        return {
            "Data ID": data_id,
            "Brand Name": brand_name,
            "Product Name": product_name,
            "Product URL": product_url,
            "Rating": rating,
            "Rating Count": rating_count,
            "Price": price,
            "Original Price": original_price,
            "Discount": discount,
            "Bestseller": bestseller,
            "Date of Extraction": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        }
    except Exception as e:
        print(f"⚠️ Error extracting product #{index + 1} - {e}")
        return None


async def scrape_ajio_from_link(page, url, product_limit):
    print(f"\n🌐 Starting scrape from: {url}")
    all_data = []
    scroll_y = 0
    last_product_count = 0
    max_scroll_attempts = 2  # Max scrolls without new products before stopping
    scroll_attempts = 0

    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_selector("#products", timeout=20000)
    except Exception as e:
        print(f"❌ Failed to load {url} - {e}")
        return []

    while len(all_data) < product_limit and scroll_attempts < max_scroll_attempts:
        await asyncio.sleep(1)  # Let page settle

        products = await page.locator('#products .item').all()
        current_count = len(products)
        if current_count == last_product_count:
            scroll_attempts += 1
            print(f"🔄 No new products detected after scroll #{scroll_attempts}, stopping scrolling...")
            break  # No new products loaded
        scroll_attempts = 0  # Reset if new products found

        new_products = products[last_product_count:]

        product_tasks = [
            extract_product_details(product, i + last_product_count)
            for i, product in enumerate(new_products)
        ]
        batch_data = await asyncio.gather(*product_tasks)
        batch_data = [item for item in batch_data if item]

        all_data.extend(batch_data)
        if len(all_data) >= product_limit:
            print(f"✅ Reached product limit ({product_limit})")
            break

        last_product_count = current_count

        scroll_y += 800
        await page.evaluate(f"window.scrollTo(0, {scroll_y})")
        print(f"⬇️ Scrolled to {scroll_y}px, collected {len(all_data)} products so far...")

        await asyncio.sleep(1)

    return all_data[:product_limit]

# ----------------------------------------
# PDP SCRAPER
# ----------------------------------------
async def extract_pdp_details(page, product_url, index):
    try:
        await page.goto(product_url, timeout=60000)
        await page.wait_for_selector(".prod-container", timeout=10000)

        sizes = []
        size_items = await page.locator(".size-variant-item.size-instock").all()
        for item in size_items:
            size = await item.locator("span").text_content()
            if size:
                sizes.append(size.strip())

        details = []
        detail_items = await page.locator("section.prod-desc ul.prod-list li.detail-list").all()
        for item in detail_items:
            text = await item.text_content()
            if text:
                details.append(text.strip())

        return {
            "Product URL": product_url,
            "Sizes Available": ", ".join(sizes) if sizes else "N/A",
            "Product Details": " | ".join(details) if details else "N/A",
            "Date of Extraction": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        print(f"⚠️ Error scraping PDP #{index + 1} ({product_url}): {e}")
        return {
            "Product URL": product_url,
            "Sizes Available": "Error",
            "Product Details": "Error",
            "Date of Extraction": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }


# ----------------------------------------
# MAIN ORCHESTRATOR
# ----------------------------------------
async def main():
    ajio_links, output_dir, max_products = launch_gui()
    os.makedirs(output_dir, exist_ok=True)

    async with async_playwright() as p:
        user_agent = random.choice(HEADERS_LIST)
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="Asia/Kolkata",
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=True
        )


        final_listing_data = []
        for link in ajio_links:
            page = await context.new_page()
            try:
                products = await scrape_ajio_from_link(page, link, max_products)
                final_listing_data.extend(products)
            except Exception as e:
                print(f"❌ Error scraping listing from {link}: {e}")
            await page.close()

        # Save listing JSON
        listing_path = os.path.join(output_dir, "ajio_data.json")
        with open(listing_path, "w", encoding="utf-8") as jf:
            json.dump(final_listing_data, jf, indent=4, ensure_ascii=False)
        print(f"\n✅ Total listing products scraped: {len(final_listing_data)}")

        # PDP Scraping with limited concurrency to avoid overload
        pdp_tasks = [
            extract_pdp_details(await context.new_page(), product["Product URL"], idx)
            for idx, product in enumerate(final_listing_data)
            ]
        pdp_data = await asyncio.gather(*pdp_tasks)
        # Save PDP JSON
        pdp_path = os.path.join(output_dir, "ajio_pdp_data.json")
        with open(pdp_path, "w", encoding="utf-8") as jf:
            json.dump(pdp_data, jf, indent=4, ensure_ascii=False)

        await browser.close()

    # Merge listing and PDP data on Product URL
    pdp_map = {item["Product URL"]: item for item in pdp_data if item}
    merged_data = []
    seen_urls = set()

    for item in final_listing_data:
        url = item["Product URL"]
        if url in seen_urls:
            continue
        merged = item.copy()
        if url in pdp_map:
            merged.update(pdp_map[url])
        merged_data.append(merged)
        seen_urls.add(url)

    duplicates_removed = len(final_listing_data) - len(merged_data)
    print(f"\n🧹 Removed {duplicates_removed} duplicate products.")
    
    # Save final merged JSON and CSV
    final_json_path = os.path.join(output_dir, "ajio_final_data.json")
    with open(final_json_path, "w", encoding="utf-8") as jf:
        json.dump(merged_data, jf, indent=4, ensure_ascii=False)

    final_csv_path = os.path.join(output_dir, "ajio_final_data.csv")
    if merged_data:
        with open(final_csv_path, "w", newline="", encoding="utf-8") as cf:
            # Ensure consistent CSV columns by collecting all keys from merged_data dicts
            fieldnames = sorted({key for d in merged_data for key in d.keys()})
            writer = csv.DictWriter(cf, fieldnames=fieldnames)
            writer.writeheader()
            for row in merged_data:
                # Write with default empty string if key missing
                writer.writerow({k: row.get(k, "") for k in fieldnames})

    print(f"\n📂 Final JSON saved to: {final_json_path}")
    print(f"📂 Final CSV saved to: {final_csv_path}")

# ----------------------------------------
# Run Everything
# ----------------------------------------
if __name__ == "__main__":
    asyncio.run(main())
