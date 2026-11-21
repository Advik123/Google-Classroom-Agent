import sys
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build
import config

# Scopes needed for Google Docs and Drive APIs
SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']

def authenticate_google_docs():
    """Authenticate and return the Docs and Drive service objects."""
    try:
        creds = service_account.Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_PATH, scopes=SCOPES)
        
        docs_service = build('docs', 'v1', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
        return docs_service, drive_service
    except Exception as e:
        print(f"❌ Error authenticating with Google Docs API. Check your credentials file: {e}")
        return None, None

def find_homework_log_doc(drive_service):
    """Searches Google Drive for a document titled 'Homework Log'."""
    try:
        results = drive_service.files().list(
            q="name='Homework Log' and mimeType='application/vnd.google-apps.document' and trashed=false",
            spaces='drive',
            fields='nextPageToken, files(id, name)'
        ).execute()
        
        items = results.get('files', [])
        if not items:
            return None
        return items[0]['id']
    except Exception as e:
        print(f"❌ Error searching for 'Homework Log' doc: {e}")
        return None

def write_to_doc(parsed_data: dict):
    """
    Writes the structured homework data to the 'Homework Log' Google Doc.
    Expects parsed_data to be { "Class Name": [{"class": "...", "assignment": "...", "due_date": "...", "source": "..."}] }
    """
    print("--- Starting Google Docs Update ---")
    docs_service, drive_service = authenticate_google_docs()
    
    if not docs_service or not drive_service:
        print("Skipping docs update due to authentication failure.")
        return False
        
    doc_id = find_homework_log_doc(drive_service)
    
    if not doc_id:
        print("❌ Could not find a document named 'Homework Log' in Drive.")
        print("Please create one and ensure it is shared with your service account email.")
        return False
        
    print(f"Found 'Homework Log' doc (ID: {doc_id}). Checking for duplicates...")
    
    # 1. Read existing content to prevent duplicates
    try:
        doc = docs_service.documents().get(documentId=doc_id).execute()
        existing_content = str(doc.get('body').get('content', ''))
    except Exception as e:
        print(f"⚠️ Could not read existing doc content, proceeding without deduplication: {e}")
        existing_content = ""

    # Flatten all assignments and filter duplicates
    all_assignments = []
    new_assignments = []
    
    existing_content_lower = existing_content.lower()

    for class_list in parsed_data.values():
        for hw in class_list:
            task_name = hw.get("assignment", "")
            class_name = hw.get("class", "").split("-")[0].strip()
            
            # Simple check: if project name and task name are already in the doc, skip
            # We check both to avoid skipping "Quiz" in ELA if "Quiz" in Science already exists
            unique_marker = f"{class_name} — {task_name}"
            task_lower = task_name.strip().lower()

            # Skip if the exact "Class — Task" marker already exists
            if unique_marker in existing_content:
                print(f"  -> Skipping duplicate: {unique_marker}")
            # Also skip if the assignment text already appears anywhere in the doc
            elif task_lower and task_lower in existing_content_lower:
                print(f"  -> Skipping duplicate based on assignment text: {task_name}")
            else:
                new_assignments.append(hw)

    if not new_assignments:
        print("✅ No new homework assignments to add (everything is already in the log).")
        return True

    print(f"Adding {len(new_assignments)} new items to the log...")

    # Group by due date (using only new assignments)
    grouped = defaultdict(list)
    for hw in new_assignments:
        date_str = hw.get("due_date", "Unknown").strip()
        grouped[date_str].append(hw)
        
    # Sort groups
    def date_sort_key(date_str):
        if date_str.lower() in ["unknown", "n/a", "none"]:
            return "99/99/99"
        try:
            parts = date_str.split("/")
            if len(parts) == 3:
                m, d, y = map(int, parts)
                if y < 100: y += 2000
                return f"{y:04d}/{m:02d}/{d:02d}"
        except: pass
        return date_str
        
    sorted_dates = sorted(grouped.keys(), key=date_sort_key)

    # Helper to find where to insert new bullets under an existing "Due X" section
    def find_section_insert_index(content, header_text):
        header_idx = None
        for idx, elem in enumerate(content):
            para = elem.get('paragraph')
            if not para:
                continue
            text = "".join(r.get('textRun', {}).get('content', '') for r in para.get('elements', []))
            if text.strip().startswith(header_text.strip()):
                header_idx = idx
                break

        if header_idx is None:
            return None

        # Move forward until we hit the next "Due" header or a blank line
        last_idx = header_idx
        for j in range(header_idx + 1, len(content)):
            para = content[j].get('paragraph')
            if not para:
                break
            text = "".join(r.get('textRun', {}).get('content', '') for r in para.get('elements', [])).strip()
            if text.startswith("Due ") or text.startswith("Due Date Unknown") or text == "":
                break
            last_idx = j

        return content[last_idx].get('endIndex', 1) - 1

    requests = []
    append_text = "\n\n"

    body_content = doc.get('body', {}).get('content', [])

    # Prepare insert operations per date
    for date in sorted_dates:
        header = f"Due {date}\n" if date.lower() not in ["unknown", "n/a", "none"] else "Due Date Unknown\n"

        # Build bullets text for this date
        bullets_text = ""
        for hw in grouped[date]:
            cls = hw.get("class", "Unknown")
            short_class = cls.split("-")[0].split(":")[0].strip() 
            if "Science" in cls: short_class = "Science"
            if "Spanish" in cls: short_class = "Spanish"
            if "Group 3" in cls: short_class = "ELA"
            if "SS" in cls: short_class = "SS"
            if "Geometry" in cls: short_class = "Geometry"
            
            task = hw.get("assignment", "Unknown")
            bullets_text += f"    • {short_class} — {task}\n"

        # If a section for this due date already exists, insert bullets under it.
        insert_index = find_section_insert_index(body_content, header.strip())
        if insert_index is not None:
            if bullets_text:
                requests.append({
                    'insertText': {
                        'location': {'index': insert_index},
                        'text': bullets_text
                    }
                })
        else:
            # No existing section for this date; append a brand new one at the end.
            append_text += header + bullets_text

    try:
        # Get end index again to be safe
        content = body_content
        end_index = content[-1]['endIndex'] - 1 if content else 1
        if end_index <= 0: end_index = 1

        # If there are any new date sections to append, add them as a single operation at the end.
        if append_text.strip():
            requests.append({
                'insertText': {
                    'location': {'index': end_index},
                    'text': append_text
                }
            })
        
        if requests:
            docs_service.documents().batchUpdate(
                documentId=doc_id, body={'requests': requests}).execute()
            print("✅ Homework Log doc updated successfully with new items.")
        else:
            print("✅ No new write operations were necessary (all items were duplicates or already organized).")
        print("--- Google Docs Update Complete ---\n")
        return True
    except Exception as e:
        print(f"❌ Error updating Google Doc: {e}")
        return False

def generate_summary(parsed_data: dict, docs_success: bool):
    """Prints final summary to console."""
    import datetime
    today_str = datetime.datetime.now().strftime("%B %d, %Y")
    
    print(f"=== HOMEWORK SUMMARY - {today_str} ===")
    
    for class_name, items in parsed_data.items():
        short_name = class_name.split()[0].replace(":", "") 
        if "Science" in class_name: short_name = "Science"
        if "Spanish" in class_name: short_name = "Spanish"
        if "ELA" in class_name: short_name = "ELA Group 3"
        if "SS" in class_name: short_name = "SS"
        if "Geometry" in class_name: short_name = "Geometry"
        
        if not items:
            print(f"- {short_name}: No homework found.")
        else:
            for hw in items:
                task = hw.get("assignment", "Unknown Task")
                due = hw.get("due_date", "Unknown Date")
                src = hw.get("source", "Unknown Source")
                print(f"- {short_name}: {task} — Due {due} (Source: {src})")
                
    print("")
    if docs_success:
        print("✅ Homework Log doc updated successfully.")
    else:
        print("❌ Homework Log doc was NOT updated.")
