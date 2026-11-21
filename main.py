import scraper
import parser
import docs_writer

def main():
    try:
        print("========================================")
        print("   GOOGLE CLASSROOM AUTOMATION AGENT    ")
        print("========================================\n")
        
        # Step 1: Scrape
        scraped_data = scraper.scrape_classroom()
        
        # Step 2: Parse with Gemini
        parsed_data = parser.parse_class_data(scraped_data)
        
        # Step 3: Write to Google Docs
        docs_success = docs_writer.write_to_doc(parsed_data)
        
        # Step 4: Summary output
        docs_writer.generate_summary(parsed_data, docs_success)
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR IN EXE: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "-"*40)
    input("Press ENTER to close this window...")

if __name__ == "__main__":
    main()
