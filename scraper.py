import os
import time
from playwright.sync_api import sync_playwright
import config

# Dedicated directory for Playwright's own browser profile
# Login cookies will persist here between runs
PLAYWRIGHT_PROFILE_DIR = os.path.join(config.BASE_DIR, "playwright_profile")


import datetime

def _get_current_date_formats():
    """Returns a list of potential date strings for the current day."""
    now = datetime.datetime.now()
    # Windows uses '#' instead of '-' for unpadded numbers
    return [
        now.strftime("%B %d"),    # March 16
        now.strftime("%b %d"),    # Mar 16
        now.strftime("%m/%d"),     # 03/16
        now.strftime("%#m/%#d"),   # 3/16
        now.strftime("%A")         # Monday
    ]

def _scrape_google_slides_text(context, slides_url, target_area_title):
    """
    Helper to open a Google Slides link and try to extract text from a specific area
    on the slide corresponding to the current date.
    """
    print(f"     Opening Google Slides: {slides_url}")
    new_page = context.new_page()
    try:
        new_page.goto(slides_url, timeout=60000)
        new_page.wait_for_load_state("load")
        time.sleep(5)  # Let slides load

        # Try to find the slide with the current date.
        # The current date is usually located on slide 1–3, but we scan up to 15 slides as a fallback.
        date_formats = _get_current_date_formats()
        slide_found = False
        
        # We'll try to navigate through slides using Right Arrow if we can't find it immediately
        for slider_idx in range(15): # Check first 15 slides
            page_text = new_page.locator("body").inner_text()
            if any(fmt.lower() in page_text.lower() for fmt in date_formats):
                print(f"     ✅ Found slide matching current date/day (Slide {slider_idx + 1}).")
                slide_found = True
                break
            new_page.keyboard.press("ArrowRight")
            time.sleep(1.5)

        if not slide_found:
            print("     ⚠️ Could not find a slide matching the current date. Scraping current slide anyway.")

        # Extract all text and let Gemini find the target area
        full_text = new_page.locator("body").inner_text()
        return f"GOOGLE SLIDES CONTENT (Look for '{target_area_title}'):\n{full_text}"
    except Exception as e:
        print(f"     ❌ Error reading slides: {e}")
        return f"Error reading slides: {e}"
    finally:
        new_page.close()

def scrape_classroom() -> dict:
    """
    Scrapes Google Classroom for the configured classes with specific logic for each.
    """
    print("\n--- Starting Google Classroom Scraper ---")
    results = {}

    with sync_playwright() as p:
        # (Login logic remains the same...)
        try:
            # Use channel="chrome" to use the system-installed Chrome 
            # instead of requiring bundled Playwright browsers (which fail in EXE)
            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=PLAYWRIGHT_PROFILE_DIR,
                headless=False,
                channel="chrome",
                args=["--start-maximized"],
                ignore_default_args=["--enable-automation"],
                no_viewport=True,
            )
        except Exception as e:
            print(f"❌ Error launching browser: {e}")
            print("💡 Tip: Make sure Google Chrome is installed on this machine.")
            return {}
        
        if browser_context.pages:
            page = browser_context.pages[0]
        else:
            page = browser_context.new_page()
        
        try:
            page.goto("https://classroom.google.com", timeout=60000)
            page.wait_for_load_state("load")
            time.sleep(3)

            current_url = page.url
            if not current_url.startswith("https://classroom.google.com"):
                # (Existing login wait logic...)
                print("\n⚠️  LOGIN REQUIRED - Please sign in manually.")
                for _ in range(36):
                    time.sleep(5)
                    if page.url.startswith("https://classroom.google.com"):
                        print("✅ Login successful!")
                        time.sleep(3)
                        break
                else:
                    return {}
            
            for class_name in config.CLASS_NAMES:
                print(f"\nEvaluating Class: {class_name}")
                class_texts = []
                
                # Check for direct agenda link first
                if class_name in config.AGENDA_LINKS:
                    print(f"  -> Found direct agenda link. Skipping Classroom navigation.")
                    url = config.AGENDA_LINKS[class_name]
                    target = "To-Do/Reminders"
                    if "SS" in class_name: target = "don't forget"
                    if "Geometry" in class_name: target = "homework"
                    
                    class_texts.append(_scrape_google_slides_text(browser_context, url, target))
                    results[class_name] = class_texts
                    continue

                try:
                    # Navigate to the class (only for Spanish and Science since they don't have direct links)
                    class_link = page.locator(f"a:has-text('{class_name}')").first
                    if class_link.count() == 0:
                        class_link = page.get_by_text(class_name, exact=False).first
                    
                    if class_link.count() == 0:
                        print(f"❌ Could not find class '{class_name}'. Skipping.")
                        continue

                    class_link.click()
                    page.wait_for_load_state("load")
                    time.sleep(2)

                    # --- CLASS SPECIFIC LOGIC ---

                    if "Spanish" in class_name:
                        print("  -> Logic: Check Upcoming box + Stream")
                        try:
                            # Use a shorter timeout for the Upcoming box to avoid 30s hangs
                            upcoming_locator = page.locator("section:has-text('Upcoming')")
                            upcoming_text = upcoming_locator.inner_text(timeout=7000)
                            
                            if "Woohoo, no work due soon!" in upcoming_text:
                                class_texts.append("Spanish Upcoming Box: No work due soon.")
                            else:
                                class_texts.append(f"Spanish Upcoming Box:\n{upcoming_text}")
                        except Exception:
                            print("     ⚠️ Could not find or read Upcoming box for Spanish. Falling back to Stream.")
                        
                        # Also scrape the Stream for recent posts
                        # Scroll a bit to find recent posts
                        page.mouse.wheel(0, 500)
                        time.sleep(1)
                        stream_content = page.locator("body").inner_text()
                        class_texts.append(f"Spanish Stream Content:\n{stream_content}")

                    elif "Science" in class_name:
                        print("  -> Logic: Check Stream for 'Weekly Agenda'")
                        # Scroll a bit to find older posts
                        for _ in range(3):
                            page.mouse.wheel(0, 500)
                            time.sleep(1.5)
                        content = page.locator("body").inner_text()
                        class_texts.append(f"Science Stream Content (Look for Weekly Agenda):\n{content}")

                    else:
                        # Fallback for unknown classes
                        print("  -> Logic: Generic scrape")
                        class_texts.append(page.locator("body").inner_text())

                    results[class_name] = class_texts

                except Exception as e:
                    print(f"❌ Error scraping class {class_name}: {e}")
                    results[class_name] = [f"Error: {e}"]

                # Back to dashboard
                page.goto("https://classroom.google.com")
                page.wait_for_load_state("load")
                time.sleep(2)

        except Exception as e:
            print(f"❌ Global error: {e}")
        finally:
            browser_context.close()

    return results
