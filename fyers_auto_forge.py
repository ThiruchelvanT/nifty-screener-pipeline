import os
import pyotp
import psycopg2
import time
from urllib.parse import urlparse, parse_qs
from fyers_apiv3 import fyersModel
from playwright.sync_api import sync_playwright

print("👻 Waking the Phantom Browser...")

# ==========================================
# 1. LOAD THE CREDENTIALS
# ==========================================
# These will be passed from GitHub Secrets
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
FYERS_PHONE = os.getenv("FYERS_PHONE")        # Your Fyers Login ID / Phone Number
FYERS_PIN = os.getenv("FYERS_PIN")            # Your 4-digit Fyers PIN
TOTP_SECRET = os.getenv("FYERS_TOTP_SECRET")  # The raw base32 Mathematical Key you extracted

DB_PASSWORD = os.getenv("NEON_PASSWORD")
NEON_HOST = "ep-holy-star-amh8eg8r-pooler.c-5.us-east-1.aws.neon.tech"

if not all([CLIENT_ID, SECRET_KEY, FYERS_PHONE, FYERS_PIN, TOTP_SECRET, DB_PASSWORD]):
    raise ValueError("⚠️ CRITICAL: Missing GitHub Secrets for the Ghost Protocol.")

# ==========================================
# 2. INITIATE THE LOGIN SEQUENCE
# ==========================================
redirect_uri = "https://127.0.0.1"

session = fyersModel.SessionModel(
    client_id=CLIENT_ID,
    secret_key=SECRET_KEY,
    redirect_uri=redirect_uri,
    response_type="code",
    grant_type="authorization_code"
)

login_url = session.generate_authcode()
print("🔗 Generated Initial Auth URL.")

# ==========================================
# 3. THE AEGIS PHANTOM PROTOCOL
# ==========================================
auth_code = None

def run_ghost():
    global auth_code
    with sync_playwright() as p:
        # Spoof a real Windows machine to prevent basic bot-blocking
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("🌐 Navigating to Fyers...")
        page.goto(login_url)

        # --- STEP 1: CLIENT ID ---
        print("⏳ Settling page...")
        page.wait_for_timeout(4000) 

        print("👤 Typing Client ID...")
        # Find the very first visible text input on the screen and click it to ensure focus
        page.locator("input:visible").first.click()
        page.keyboard.type(FYERS_PHONE, delay=150) 

        print("⏳ Waiting for Login Button to turn blue...")
        submit_btn = page.locator("button[type='submit']:visible, button[id*='Submit']:visible").first
        for _ in range(20): # Check for up to 10 seconds
            if not submit_btn.is_disabled():
                break
            page.wait_for_timeout(500)
        
        submit_btn.click()
        print("🔘 Clicked ID Submit.")

        # --- STEP 2: TOTP ---
        print("⏳ Waiting for OTP screen to render (5s)...")
        page.wait_for_timeout(5000)

        totp = pyotp.TOTP(TOTP_SECRET)
        current_code = totp.now()

        print("🔐 Injecting TOTP...")
        page.locator("input:visible").first.click()
        page.keyboard.type(current_code, delay=150)

        print("⏳ Waiting for OTP Button to turn blue...")
        otp_btn = page.locator("button[type='submit']:visible, button[id*='Submit']:visible").first
        for _ in range(20):
            if not otp_btn.is_disabled():
                break
            page.wait_for_timeout(500)
        
        otp_btn.click()
        print("🔘 Clicked OTP Submit.")

        # --- STEP 3: PIN ---
        print("⏳ Waiting for PIN screen to render (5s)...")
        page.wait_for_timeout(5000)

        print("🔢 Injecting PIN...")
        page.locator("input:visible").first.click()
        page.keyboard.type(FYERS_PIN, delay=150)

        print("⏳ Waiting for PIN Button to turn blue...")
        pin_btn = page.locator("button[type='submit']:visible, button[id*='Submit']:visible").first
        for _ in range(20):
            if not pin_btn.is_disabled():
                break
            page.wait_for_timeout(500)
            
        pin_btn.click()
        print("🔘 Clicked PIN Submit.")

        # --- STEP 4: ACTIVE URL SNIFFER ---
        print("⏳ Polling for final redirect payload...")
        for _ in range(40): # Poll actively for up to 20 seconds
            current_url = page.url
            if 'auth_code=' in current_url:
                print("🎯 Target acquired in URL!")
                break
            page.wait_for_timeout(500)

        final_url = page.url
        print(f"📍 Final Intercept: {final_url}")
        
        parsed_url = urlparse(final_url)
        query_params = parse_qs(parsed_url.query)
        
        if 'auth_code' in query_params:
            auth_code = query_params['auth_code'][0]
            print("✅ Payload Extracted!")
        else:
            print("❌ Failed to extract auth_code from URL.")
            
        browser.close()

run_ghost()

if not auth_code:
    raise Exception("Ghost failed to acquire the auth_code.")

# ==========================================
# 4. FORGE THE MASTER TOKEN
# ==========================================
print("🔨 Forging Master Token...")
session.set_token(auth_code)
response = session.generate_token()

if "access_token" not in response:
    raise Exception(f"Failed to forge Master Token: {response}")

master_token = response["access_token"]
print("💎 Master Token Successfully Forged.")

# ==========================================
# 5. LOCK IN NEONDB VAULT
# ==========================================
print("💾 Connecting to NeonDB Vault...")
try:
    conn = psycopg2.connect(
        host=NEON_HOST, port="5432", dbname="neondb",    
        user="neondb_owner", password=DB_PASSWORD
    )
    cursor = conn.cursor()
    
    update_query = """
        UPDATE system_config 
        SET key_value = %s, last_updated = NOW() 
        WHERE key_name = 'FYERS_ACCESS_TOKEN';
    """
    cursor.execute(update_query, (master_token,))
    conn.commit()
    
    print("✅ MASTER TOKEN SECURED IN DATABASE. Pipeline is primed.")
    
except Exception as e:
    print(f"❌ Failed to secure token in database: {e}")
finally:
    if 'cursor' in locals(): cursor.close()
    if 'conn' in locals(): conn.close()
