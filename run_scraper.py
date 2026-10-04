import sys
from scraper.scraper import WebScraper

if __name__ == "__main__":
    print("=" * 60)
    print("🕷️ STARTING STANDALONE WEB SCRAPER JOB")
    print("Target Portals:")
    print(" 1. https://sevasindhugs1.karnataka.gov.in/gl-sp/")
    print(" 2. https://ssp.karnataka.gov.in/")
    print(" 3. https://www.karnataka.gov.in/")
    print("=" * 60)

    scraper = WebScraper()
    results = scraper.run()
    
    print("\n" + "=" * 60)
    print("✅ SCRAPER RUN COMPLETED")
    print(f"📄 Total Pages Scraped & Saved to SQL: {results['pages_scraped']}")
    print(f"📥 Total PDFs Saved to 'scraper/SCRAPED PDF': {results['pdfs_downloaded']}")
    print("=" * 60)
