import json
import datetime
import time
import google.generativeai as genai
import config

def parse_class_data(scraper_results: dict) -> dict:
    """
    Sends raw scraped text to Gemini to extract homework and format as JSON.
    Returns a dictionary mapping class name to a list of homework dictionary objects.
    """
    print("--- Starting Gemini Parsing ---")
    if not config.GEMINI_API_KEY:
        print(
            "❌ No Gemini API key found. Set GEMINI_API_KEY or GOOGLE_API_KEY in .env "
            "next to this script or GoogleClassroomAgent.exe."
        )
        return {name: [] for name in scraper_results}
    genai.configure(api_key=config.GEMINI_API_KEY)
    
    # Using gemini-flash-latest which is confirmed to be available in your project
    model = genai.GenerativeModel('gemini-flash-latest')
    
    parsed_results = {}
    
    today = datetime.datetime.now()
    today_str = today.strftime("%A, %m/%d/%Y")
    tomorrow = today + datetime.timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%A, %m/%d/%Y")
    
    # Rate limiting counter
    request_count = 0

    for class_name, raw_texts in scraper_results.items():
        if not raw_texts or any("Error" in t for t in raw_texts):
            parsed_results[class_name] = []
            continue
            
        print(f"Parsing data for: {class_name}")
        
        # Exponential backoff retry loop for each request
        max_retries = 5
        retry_delay = 30  # Start with 30s delay
        
        combined_text = "\n\n=== NEXT SECTION ===\n\n".join(raw_texts)
        
        # System instructions / prompt
        prompt = f"""
        You are a smart homework extraction assistant.
        Today's date is: {today_str}
        Tomorrow's date is: {tomorrow_str}
        
        I am giving you raw text scraped from a Google Classroom for the class '{class_name}'.
        Note: Some content may be from a Google Slides presentation (Agenda).
        
        YOUR GOAL: Extract all homework assignments assigned for today or due today/tomorrow.
        
        CLASS-SPECIFIC EXTRACTION RULES:
        1. ELA Group 3 - Mrs. Schultz: Homework is listed under the section "To-Do/Reminders".
        2. Spanish: Check both the 'Upcoming' box text and the Stream content. Even if 'Upcoming' is empty, check the Stream for any recent posts from the teacher mentioning homework or assignments.
        3. P3 Science: Look for "Weekly Agenda" text. Extract specifically the homework listed in BOLD under each day. Only return homework for TODAY ({today.strftime('%A')}).
        4. Ms. Lyman SS: Homework is listed under the box titled "don't forget".
        5. Geometry: Under the current day ({today.strftime('%A')}), it will state the homework.
        
        GENERAL RULES:
        - Date Conversion: Convert relative dates (e.g. "Tomorrow") to "MM/DD/YY" based on today ({today_str}). Use "Unknown" if unclear.
        - Exclude: Anything that is just class instruction, activity descriptions, or "Inquiry Activity". We ONLY want active homework/assignments.
        
        OUTPUT FORMAT:
        Return ONLY a raw JSON array. NO markdown formatting, NO code fences like ```json, NO backticks, NO explanation. Just the JSON array.
        
        [
          {{
            "class": "{class_name}",
            "assignment": "Assignment Name",
            "due_date": "MM/DD/YY",
            "source": "Agenda" or "Classwork"
          }}
        ]
        
        If there is no homework found, return:
        []
        
        RAW TEXT TO PARSE:
        {combined_text}
        """

        success = False
        for attempt in range(max_retries):
            try:
                # Add a base delay for rate limiting between different classes
                # Target ~10 requests per minute (one every ~6 seconds) with a small safety margin.
                if request_count > 0 and attempt == 0:
                    print(f"⏳ Waiting 7 seconds to maintain ~10 RPM rate limit...")
                    time.sleep(7)
                
                response = model.generate_content(prompt)
                raw_response = response.text.strip()
                
                # Clean possible markdown just in case the model disobeys
                if raw_response.startswith("```json"):
                    raw_response = raw_response[7:]
                if raw_response.startswith("```"):
                    raw_response = raw_response[3:]
                if raw_response.endswith("```"):
                    raw_response = raw_response[:-3]
                    
                raw_response = raw_response.strip()
                
                try:
                    json_data = json.loads(raw_response)
                    parsed_results[class_name] = json_data
                    print(f"  -> Found {len(json_data)} assignments.")
                    request_count += 1
                    success = True
                    break
                except json.JSONDecodeError as decode_error:
                    print(f"  -> ❌ Failed to parse JSON from Gemini. Raw response:\n{raw_response}")
                    parsed_results[class_name] = []
                    success = True # Don't retry on bad JSON format usually
                    break
                    
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "quota" in error_str.lower():
                    wait_time = retry_delay * (2 ** attempt) + (time.time() % 5) # Exp backoff + jitter
                    print(f"  -> ⚠️ Quota hit (429). Retrying in {int(wait_time)} seconds... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"  -> ❌ Gemini API Error: {e}")
                    parsed_results[class_name] = []
                    break
        
        if not success:
            print(f"  -> ❌ Failed to parse {class_name} after {max_retries} retries.")
            parsed_results[class_name] = []
            
    print("--- Parsing Complete ---\n")
    return parsed_results
