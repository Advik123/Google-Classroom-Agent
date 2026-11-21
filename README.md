# Google Classroom Automation Agent - Setup Guide

Welcome to the Google Classroom Automation Agent! This script automates logging into your Google Classroom, extracting your homework, and logging it into a Google Doc using AI.

Follow these step-by-step instructions to get everything set up.

### 1. Install Python 3.10+
If you don't already have Python installed, download it here:
[Python Download Page](https://www.python.org/downloads/)
*Important for Windows users: Check the box "Add Python to PATH" during installation.*

### 2. Install Project Dependencies
Open your terminal (Command Prompt or PowerShell) and navigate to the folder where you placed these files. Run the following command:
```bash
pip install -r requirements.txt
```

To run the **Classroom scraper** (`main.py`) as well, also install the optional file:
```bash
pip install -r requirements-scraper.txt
```

### 3. Install Playwright Browsers
This command downloads the Chromium browser that the script will use to navigate Google Classroom.
```bash
python -m playwright install chromium
```

### 4. Get a Free Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/) and sign in with your Google account.
2. Click "Get API key" (or "Create API key").
3. Copy the created key. You will need to paste it into `config.py`.

### 5. Set up a Google Cloud Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown at the top and select **New Project**. Name it something like "HomeworkAgent".
3. Once created, ensure your new project is selected.
4. Go to **APIs & Services > Library**.
5. Search for **Google Docs API** and click **Enable**.
6. Search for **Google Drive API** and click **Enable**.

### 6. Create a Service Account (Credentials JSON)
1. In the Google Cloud Console, go to **APIs & Services > Credentials**.
2. Click **Create Credentials** at the top and select **Service account**.
3. Name it "Classroom Agent" and click **Create and Continue**, then **Done**.
4. You will see the new Service Account listed at the bottom under "Service Accounts". **Copy its email address**.
5. Click the pencil icon (or click the email address) to edit the Service Account.
6. Go to the **Keys** tab.
7. Click **Add Key > Create new key**.
8. Choose **JSON** and click **Create**. A file will download to your computer.
9. Move this `.json` file into the folder with the rest of your agent's code (`GoogleClassroomAgent`). Name it `credentials.json` or remember its path!

### 7. Create the Google Doc
1. Go to your personal Google Drive and create a new Google Doc.
2. Title it exactly: **Homework Log**
3. Click **Share** in the top right.
4. Paste the **Service Account email address** you copied in Step 6 into the "Add people and groups" box.
5. Grant the service account **Editor** access and click **Send**. (This allows the script to write to your document).

### 8. Find your Chrome Profile Path
The script needs to use your existing Chrome profile so it stays logged in to Google Classroom without needing passwords.
- **Windows generally:** `C:\Users\YourUsername\AppData\Local\Google\Chrome\User Data`
- **Mac generally:** `/Users/YourUsername/Library/Application Support/Google/Chrome`
Update the `CHROME_PROFILE_PATH` in `config.py` with your path.

*Note: Before running the script, you must completely close out of all normal Google Chrome browser windows, otherwise you may get an error about the user data directory being locked.*

### 9. Configure the Script
Open `config.py` and fill in your details:
- `GEMINI_API_KEY`: Paste your key from Step 4.
- `GOOGLE_CREDENTIALS_PATH`: Provide the full or relative path to the `.json` file from Step 6.
- `CHROME_PROFILE_PATH`: Paste your path from Step 8.
- Double-check `CLASSROOM_ACCOUNT` and `CLASS_NAMES` if necessary.

### 10. Run the Script
In your terminal, within the project folder, run:
```bash
python main.py
```

### What to Expect
When you run the script, a visible Chrome window will open (using Chromium) and automatically navigate to Google Classroom. You will see terminal output telling you exactly which class it is scanning. After scraping, it will contact the Gemini AI, parse the results, append them to your "Homework Log" Google Doc, and finally print a cleanly formatted homework summary to your terminal.

### Vercel (Flask web app)
The dashboard (`app.py`) can be deployed to [Vercel](https://vercel.com/). Static files live under `public/static/` (per Vercel’s Flask guidance). Playwright is not required for the web app; use `requirements-scraper.txt` only for `main.py`.

In the Vercel project, set these **Environment Variables** (Production, and Preview if you use them):

- `GEMINI_API_KEY` — your Gemini key (or `GOOGLE_API_KEY` for the same value).
- `HOMEWORK_LOG_DOC_ID` — the Google Doc ID of your homework log.
- `GOOGLE_CREDENTIALS_JSON` — the full service account JSON as a single string, **or** `GOOGLE_CREDENTIALS_B64` — the same JSON **base64-encoded** (useful to avoid multiline env issues).

Redeploy after changing variables. The homework doc must still be **shared** with the service account email.
