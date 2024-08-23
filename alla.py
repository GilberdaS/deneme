from playwright.sync_api import sync_playwright
from dataclasses import dataclass, asdict, field
import pandas as pd
import os
import logging
import re
import tkinter as tk
from tkinter import simpledialog, messagebox

# Logger yapılandırması
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Business:
    """Holds business data"""
    name: str = None
    address: str = None
    website: str = None
    phone_number: str = None
    reviews_average: float = None
    total_reviews: int = None  # Toplam değerlendirme sayısı için eklenen alan
    url: str = None  # Google Maps URL'si için eklenen alan

@dataclass
class BusinessList:
    """Holds list of Business objects and saves to both excel and csv"""
    business_list: list[Business] = field(default_factory=list)
    save_at = 'output'

    def dataframe(self):
        """Transform business_list to pandas dataframe

        Returns: pandas dataframe
        """
        return pd.json_normalize(
            (asdict(business) for business in self.business_list), sep="_"
        )

    def save_to_excel(self, filename):
        """Saves pandas dataframe to excel (xlsx) file

        Args:
            filename (str): filename
        """
        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_excel(f"{self.save_at}/{filename}.xlsx", index=False)

    def save_to_csv(self, filename):
        """Saves pandas dataframe to csv file

        Args:
            filename (str): filename
        """
        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_csv(f"{self.save_at}/{filename}.csv", index=False)

def filter_business(name: str, address: str, unwanted_keywords: list) -> bool:
    """Filters out unwanted businesses based on name or address.

    Args:
        name (str): Name of the business.
        address (str): Address of the business.
        unwanted_keywords (list): List of unwanted keywords.

    Returns:
        bool: True if the business should be included, False otherwise.
    """
    return not any(keyword in name.lower() or keyword in address.lower() for keyword in unwanted_keywords)

def clean_total_reviews_text(text: str) -> int:
    """Cleans and converts the total reviews text to an integer.

    Args:
        text (str): The text containing the total reviews count.

    Returns:
        int: The cleaned total reviews count.
    """
    text = text.strip()
    text = re.sub(r'[^\d]', '', text)  # Sadece rakamları al, diğer karakterleri temizle
    return int(text) if text else None

def show_completion_message():
    """Shows a completion message after scraping is done"""
    messagebox.showinfo("Tamamlandı", "Veri çekme işlemi tamamlandı!")

def start_scraping(search_query, unwanted_keywords, excel_filename):
    ###########
    # Veri Çekme
    ###########
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        page.goto("https://www.google.com/maps", timeout=60000)
        page.wait_for_timeout(1000)

        logger.info(f"Arama yapılıyor: {search_query}")

        page.locator('//input[@id="searchboxinput"]').fill(search_query)
        page.wait_for_timeout(1000)

        page.keyboard.press("Enter")
        page.wait_for_timeout(5000)

        page.hover('//a[contains(@href, "https://www.google.com/maps/place")]')

        previously_counted = 0
        total = 100  # Sabit total değeri, isterseniz Tkinter arayüzüne ekleyebilirsiniz

        while True:
            page.mouse.wheel(0, 10000)
            page.wait_for_timeout(1000)

            current_count = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').count()

            if current_count >= total:
                listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()[:total]
                listings = [listing.locator("xpath=..") for listing in listings]
                logger.info(f"Toplam Verilen Sayısı: {len(listings)}")
                break
            else:
                if current_count == previously_counted:
                    listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()
                    logger.info(f"Tüm listelere ulaşıldı\nToplam Verilen Sayısı: {len(listings)}")
                    break
                else:
                    previously_counted = current_count
                    logger.info(f"Şu anki Sayılar: {current_count}")

        business_list = BusinessList()

        for listing in listings:
            try:
                listing.click()
                page.wait_for_timeout(5000)

                business = Business()

                name_attribute = 'aria-label'
                address_css = 'button[data-item-id="address"] .fontBodyMedium'
                website_css = 'a[data-item-id="authority"] .fontBodyMedium'
                phone_number_css = 'button[data-item-id*="phone:tel:"] .fontBodyMedium'
                reviews_average_css = 'div[jsaction="pane.reviewChart.moreReviews"] div[role="img"]'
                total_reviews_xpath = '//*[@id="QA0Szd"]/div/div/div[1]/div[3]/div/div[1]/div/div/div[2]/div[2]/div/div[1]/div[2]/div/div[1]/div[2]/span[2]/span/span'

                # Verileri almak ve boşlukları kontrol etmek
                try:
                    name_attribute_value = listing.get_attribute(name_attribute)
                    business.name = name_attribute_value.strip() if name_attribute_value else ""
                    if not business.name:
                        logger.warning("İşletme ismi alınamadı.")
                except Exception as e:
                    logger.error(f'İşletme ismi alınamadı: {e}')

                address_element = page.locator(address_css)
                business.address = address_element.inner_text().strip() if address_element.count() > 0 else ""
                
                website_element = page.locator(website_css)
                business.website = website_element.inner_text().strip() if website_element.count() > 0 else ""
                
                phone_number_element = page.locator(phone_number_css)
                business.phone_number = phone_number_element.inner_text().strip() if phone_number_element.count() > 0 else ""
                
                # Telefon numarası yoksa işleme almayın
                if not business.phone_number:
                    continue
                
                reviews_average_elements = page.locator(reviews_average_css)
                reviews_average_value = reviews_average_elements.get_attribute('aria-label')
                if reviews_average_value:
                    business.reviews_average = float(reviews_average_value.split()[0].replace(',', '.').strip())

                # Toplam değerlendirme sayısını al
                try:
                    total_reviews_element = page.locator(total_reviews_xpath)
                    total_reviews_text = total_reviews_element.inner_text().strip()
                    if total_reviews_text:
                        business.total_reviews = clean_total_reviews_text(total_reviews_text)
                except Exception as e:
                    logger.error(f'Toplam değerlendirme sayısı alınamadı: {e}')
                    business.total_reviews = None

                # Adres ve reviews_average yoksa işleme almayın
                if not business.address or not business.reviews_average:
                    continue

                # Google Maps URL'sini ekle
                business.url = page.url

                # Filtreleme işlemi
                if filter_business(business.name, business.address, unwanted_keywords):
                    business_list.business_list.append(business)

            except Exception as e:
                logger.error(f'Hata oluştu: {e}', exc_info=True)

        business_list.save_to_excel(excel_filename)
        business_list.save_to_csv(excel_filename)

        browser.close()
        show_completion_message()  # İşlem tamamlandığında bilgilendirme mesajı göster
def main():
    # Tkinter arayüzü
    root = tk.Tk()
    root.title("Emir Günay Maps Scrapper")

    tk.Label(root, text="Arama Sorgusu:").grid(row=0, column=0)
    tk.Label(root, text="İstenmeyen Anahtar Kelimeler (virgülle ayırın):").grid(row=1, column=0)
    tk.Label(root, text="Excel Dosya Adı:").grid(row=2, column=0)

    search_query_entry = tk.Entry(root, width=50)
    search_query_entry.grid(row=0, column=1)

    unwanted_keywords_entry = tk.Entry(root, width=50)
    unwanted_keywords_entry.grid(row=1, column=1)

    excel_filename_entry = tk.Entry(root, width=50)
    excel_filename_entry.grid(row=2, column=1)

    def on_submit():
        search_query = search_query_entry.get()
        unwanted_keywords = unwanted_keywords_entry.get().split(',')
        excel_filename = excel_filename_entry.get()

        if not search_query or not excel_filename:
            messagebox.showerror("Hata", "Tüm alanları Doldurunuz ! ")
        else:
            root.destroy()
            start_scraping(search_query, unwanted_keywords, excel_filename)

    submit_button = tk.Button(root, text="Başlat", command=on_submit)
    submit_button.grid(row=3, columnspan=2)

    root.mainloop()

if __name__ == "__main__":
    main()




