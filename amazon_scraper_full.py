import asyncio
import os
import re
import json
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
from playwright.sync_api import sync_playwright

# Global variables set by GUI
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
    root.title("🧬 Amazon Scraper Configuration")
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

def extract_listing_data(page):
    products = []
    items = page.query_selector_all('div[data-asin]')
    for item in items:
        try:
            data_id = item.get_attribute("data-asin").strip()
            if not data_id:
                continue

            product_url = item.query_selector("a.a-link-normal.s-line-clamp-2.s-link-style.a-text-normal")
            product_href = product_url.get_attribute("href") if product_url else ""
            full_url = f"https://www.amazon.in{product_href}" if product_href else ""

            brand_elem = item.query_selector("span.a-size-base-plus.a-color-base")
            brand_name = brand_elem.inner_text().strip() if brand_elem else ""

            product_name_elem = item.query_selector("a.a-link-normal.s-line-clamp-2.s-link-style.a-text-normal h2 span")
            product_name = product_name_elem.inner_text().strip() if product_name_elem else ""

            rating_elem = item.query_selector("span.a-icon-alt")
            rating = rating_elem.inner_text().strip() if rating_elem else ""

            rating_count_elem = item.query_selector("span.a-size-base.s-underline-text")
            rating_count = rating_count_elem.inner_text().strip() if rating_count_elem else ""

            price_elems = item.query_selector_all("span.a-price span.a-offscreen")
            prices = [p.inner_text().strip().replace("₹", "").replace(",", "") for p in price_elems]
            price = float(prices[0]) if prices else None

            original_price_elems = item.query_selector_all("span.a-text-price span.a-offscreen")
            original_prices = [p.inner_text().strip().replace("₹", "").replace(",", "") for p in original_price_elems]
            original_price = float(original_prices[0]) if original_prices else None

            discount_elem = item.query_selector("span.savingsPercentage")
            if not discount_elem:
                discount_elem = item.query_selector("span.s-price-instructions-style span.a-color-price")

            if discount_elem:
                discount = discount_elem.inner_text().strip()
            elif original_price and price:
                percent = int(round(((original_price - price) / original_price) * 100))
                discount = f"{percent}% off"
            else:
                discount = ""

            badge_text = ""
            badge_container = item.query_selector("div.puis-status-badge-container")
            if badge_container:
                badge_label_span = badge_container.query_selector("span.a-badge-text")
                if badge_label_span:
                    badge_text = badge_label_span.inner_text().strip()

            if not badge_text:
                amazons_choice_span = item.query_selector("span.a-badge[aria-labelledby$='-amazons-choice-label']")
                if amazons_choice_span:
                    label_elem = amazons_choice_span.query_selector("span.a-badge-label")
                    supplementary_elem = amazons_choice_span.query_selector("span.a-badge-supplementary-text")
                    label_text = label_elem.inner_text().strip() if label_elem else ""
                    supplementary_text = supplementary_elem.inner_text().strip() if supplementary_elem else ""
                    badge_text = f"{label_text} {supplementary_text}".strip()

            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            product = {
                "Data ID": data_id,
                "Product URL": full_url,
                "Brand Name": brand_name,
                "Product Name": product_name,
                "Rating": rating,
                "Rating Count": rating_count,
                "Price (INR)": f"₹{price}" if price else "",
                "Original Price (INR)": f"₹{original_price}" if original_price else "",
                "Discount": discount,
                "Badge": badge_text,
                "Date of Extraction": timestamp
            }

            products.append(product)
        except Exception as e:
            print(f"Error extracting product: {e}")
    return products
def extract_pdp_data(page):
    def get_all_facts():
        facts = {}
        try:
            fact_containers = page.query_selector_all("div.a-fixed-left-grid.product-facts-detail")
            for container in fact_containers:
                left = container.query_selector("div.a-col-left")
                right = container.query_selector("div.a-col-right")
                if left and right:
                    left_text = left.inner_text().strip().rstrip(":")
                    right_text = right.inner_text().strip()
                    if left_text and right_text:
                        facts[left_text] = right_text
        except:
            pass
        return facts

    def get_bullet_points():
        bullets = page.query_selector_all("div.a-expander-content ul.a-unordered-list li")
        return [li.inner_text().strip() for li in bullets if li.inner_text().strip()]

    def find_bullet_by_keywords(keywords):
        bullets = get_bullet_points()
        for text in bullets:
            lower_text = text.lower()
            for kw in keywords:
                if kw.lower().rstrip(":") in lower_text:
                    return text
        return ""

    # Keyword mappings for bullet-based extraction
    keyword_map = {
        "Fabric Info": ["fabric", "kurta and bottom fabric"],
        "Color Info": ["color :-", "color"],
        "Style Info": ["style"],
        "Length Info": ["length"],
        "Sleeve Info": ["sleeves"],
        "Size Chart": ["size chart"],
        "Includes Info": ["this set includes"],
        "Work/Design Info": ["work :-", "work"],
        "Neck Style": ["neck style:-", "neck style"],
        "Color Disclaimer": ["colour declaration"],
        "Occasion / Usage": ["occasion", "ocassion"],
        "Brand Mention / CTA": ["click on brand name"]
    }

    # Extract About This Item section (structured)
    about_this_item_dict = {}
    for label, keywords in keyword_map.items():
        val = find_bullet_by_keywords(keywords)
        if val:
            about_this_item_dict[label] = val

    full_bullets = get_bullet_points()

    # Dynamic Product Details extraction
    product_details = get_all_facts()

    # 🔹 New: Extract Additional Details (already present in your code)
    def get_additional_details():
        additional_keys = [
            "Manufacturer", "Item Weight", "Product Dimensions", "Country of Origin",
            "Packer", "Importer", "Net Quantity", "Included Components"
        ]
        details = {}
        try:
            containers = page.query_selector_all("div.a-fixed-left-grid")
            for container in containers:
                left = container.query_selector("div.a-fixed-left-grid-col.a-col-left span")
                right = container.query_selector("div.a-fixed-left-grid-col.a-col-right span")
                if left and right:
                    key = left.inner_text().strip().rstrip(":")
                    value = right.inner_text().strip()
                    if key in additional_keys and value:
                        details[key] = value
        except:
            pass
        return details

    # 🔹 New: Extract Brand Snapshot details (already present in your code)
    def get_brand_snapshot():
        brand_snapshot = {}
        try:
            brand_container = page.query_selector("div.a-cardui-body.brand-snapshot-card-content")
            if brand_container:
                brand_name_span = brand_container.query_selector("p > span.a-size-medium.a-text-bold")
                if brand_name_span:
                    brand_snapshot["Brand Name"] = brand_name_span.inner_text().strip()

            title_container = page.query_selector("div.a-section.a-text-center.brand-snapshot-title-container > p")
            if title_container:
                brand_snapshot["Top Brand Heading"] = title_container.inner_text().strip()

            list_items = page.query_selector_all("div.a-section.a-spacing-base.brand-snapshot-flex-row[role='listitem']")
            if list_items and len(list_items) >= 3:
                pos_rating = list_items[0].query_selector("p")
                if pos_rating:
                    brand_snapshot["Positive Ratings"] = pos_rating.inner_text().strip()

                recent_orders = list_items[1].query_selector("p")
                if recent_orders:
                    brand_snapshot["Recent Orders"] = recent_orders.inner_text().strip()

                years_amazon = list_items[2].query_selector("p")
                if years_amazon:
                    brand_snapshot["Years on Amazon"] = years_amazon.inner_text().strip()

                badge_images = []
                for item in list_items:
                    img = item.query_selector("img.brand-snapshot-item-image")
                    if img:
                        src = img.get_attribute("src")
                        if src:
                            badge_images.append(src)
                if badge_images:
                    brand_snapshot["Brand Badge Image URLs"] = badge_images

        except:
            pass
        return brand_snapshot

    # 🔹 New: Extract Product Description
    def get_product_description():
        try:
            desc_div = page.query_selector("#productDescription_feature_div #productDescription.a-section.a-spacing-small p span")
            if desc_div:
                return desc_div.inner_text().strip()
        except:
            pass
        return ""

    # 🔹 New: Extract Product and Seller Details (Product Facts list items with <li><span class="a-text-bold">Key</span></li>)
    def get_product_and_seller_details():
        details = {}
        try:
            # Select all <li> where span.a-text-bold contains the keys
            li_elements = page.query_selector_all("li")
            for li in li_elements:
                key_span = li.query_selector("span.a-text-bold")
                if key_span:
                    key = key_span.inner_text().strip().rstrip(":")
                    # Only add if key is in our required fields
                    required_keys = [
                        "Product Dimensions", "Date First Available", "Manufacturer", "ASIN",
                        "Item model number", "Country of Origin", "Department", "Packer",
                        "Importer", "Item Weight", "Item Dimensions LxWxH", "Net Quantity",
                        "Included Components", "Generic Name"
                    ]
                    if key in required_keys:
                        # The sibling span (or text node) with the value may be next sibling or inside li
                        # We'll try to get text excluding the key span text itself
                        # One approach: get full li text and remove the key span text
                        full_text = li.inner_text().strip()
                        value = full_text.replace(key_span.inner_text().strip(), "").strip(" :\n")
                        details[key] = value
        except:
            pass
        return details

    # Compose final data dictionary
    pdp_data = {
        "Product Details": product_details,
        "About This Item": about_this_item_dict,
        "All Bullet Points": full_bullets,
        "Additional Details": get_additional_details(),
        "Brand Snapshot": get_brand_snapshot(),
        "Product and Seller Details": get_product_and_seller_details(),   # NEW field added
        "Product Description": get_product_description()                 # NEW field added
    }

    return pdp_data


def scrape_amazon():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        all_products = []
        for base_link in category_links:
            print(f"\nScraping: {base_link}")

            current_link_products = []
            current_count = 0
            page_num = 1

            # We assume the base_link is like: https://www.amazon.in/s?k=women+ethnic+wear
            # Append &page=2, &page=3 etc. for pagination
            while current_count < PRODUCTS_PER_LINK:
                # Construct paginated URL
                if "page=" in base_link:
                    # Replace existing page number if present
                    url = re.sub(r"page=\d+", f"page={page_num}", base_link)
                else:
                    # Add page param, if URL already has ? then use &, else use ?
                    url = base_link + ("&" if "?" in base_link else "?") + f"page={page_num}"

                print(f"Visiting page {page_num}: {url}")
                page = context.new_page()
                try:
                    page.goto(url, timeout=60000)
                    page.wait_for_timeout(3000)

                    products = extract_listing_data(page)
                    new_products = [p for p in products if p["Data ID"] not in {x["Data ID"] for x in current_link_products}]
                    if not new_products:
                        print("No new products found, stopping pagination.")
                        page.close()
                        break

                    current_link_products.extend(new_products)
                    current_count = len(current_link_products)
                    print(f"Page {page_num}: Collected {current_count} products from current link")

                    page.close()
                    if current_count >= PRODUCTS_PER_LINK:
                        break

                    page_num += 1
                except Exception as e:
                    print(f"Error loading page {page_num}: {e}")
                    page.close()
                    break

            all_products.extend(current_link_products[:PRODUCTS_PER_LINK])

        listing_path = os.path.join(output_dir, "Amazon_All_Listings.json")
        with open(listing_path, "w", encoding="utf-8") as f:
            json.dump(all_products, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Listings saved to: {listing_path}")

        # === PDP SCRAPER SECTION ===
        final_products = []
        for product in all_products:
            url = product.get("Product URL")
            try:
                pdp_page = context.new_page()
                pdp_page.goto(url, timeout=60000)
                pdp_page.wait_for_timeout(3000)
                pdp_info = extract_pdp_data(pdp_page)
                pdp_page.close()
                product.update(pdp_info)
                final_products.append(product)
                print(f"✅ PDP scraped for: {product['Product Name'][:40]}")
            except Exception as e:
                print(f"❌ Error loading PDP for {url}: {e}")

        full_path = os.path.join(output_dir, "Amazon_full_data.json")
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(final_products, f, ensure_ascii=False, indent=2)
        print(f"\n🧾 Final full product data saved to: {full_path}")
        browser.close()

if __name__ == "__main__":
    start_gui()
    scrape_amazon()
