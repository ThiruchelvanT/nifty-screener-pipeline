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
# 3. LAUNCH THE PHANTOM (Playwright)
# ==========================================
auth_code = None

def run_ghost():
    global auth_code
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("🌐 Phantom navigating to Fyers Login...")
        page.goto(login_url)

        # 1. Enter Phone Number / Login ID
        print("⏳ Waiting for Client ID box...")
        id_box = page.locator("input[type='text'], input[placeholder*='Client ID'], input[placeholder*='Mobile']").first
        id_box.wait_for(state="visible", timeout=15000)
        
        # 🚨 THE FIX: Type like a human with a 100ms delay between keys
        id_box.type(FYERS_PHONE, delay=100)
        print("👤 Typed Client ID like a human.")
        
        # 🚨 THE FIX: Wait specifically for the button to become ENABLED, not just visible
        submit_btn = page.locator("button:visible").first
        submit_btn.wait_for(state="attached", timeout=10000) # Wait for it to exist in DOM
        
        # In Playwright, checking if a button is enabled sometimes requires a small loop if the site's JS is slow
        for _ in range(10):
            if submit_btn.is_enabled():
                break
            time.sleep(0.5)
            
        submit_btn.click()
        print("🔘 Clicked Submit.")

        def run_ghost():
    global auth_code
    with sync_playwright() as p:
        # Launch headless browser (invisible)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("🌐 Phantom navigating to Fyers Login...")
        page.goto(login_url)

        # 1. Enter Phone Number / Login ID
        print("⏳ Waiting for Client ID box...")
        id_box = page.locator("input[type='text'], input[placeholder*='Client ID'], input[placeholder*='Mobile']").first
        id_box.wait_for(state="visible", timeout=15000)
        
        # Click the box to ensure it has focus, then type
        id_box.click()
        page.keyboard.type(FYERS_PHONE, delay=100)
        print("👤 Typed Client ID.")
        
        # Use Keyboard Enter instead of trying to find the submit button
        page.keyboard.press("Enter")
        print("🔘 Pressed Enter.")

        # 2. Enter TOTP (Mathematical Generation)
        print("⏳ Waiting for OTP screen transition (3 seconds)...")
        time.sleep(3) # Blind wait for the JS transition
        
        totp = pyotp.TOTP(TOTP_SECRET)
        current_code = totp.now()
        
        # We assume the first OTP box is auto-focused by Fyers. 
        # We just blast the keys into the ether.
        print(f"🔐 Injecting TOTP keystrokes...")
        page.keyboard.type(current_code, delay=100)
        time.sleep(1) # Let JS register the typing
        page.keyboard.press("Enter")

        # 3. Enter PIN
        print("⏳ Waiting for PIN screen transition (3 seconds)...")
        time.sleep(3) 
        
        print("🔢 Injecting PIN keystrokes...")
        page.keyboard.type(FYERS_PIN, delay=100)
        time.sleep(1)
        page.keyboard.press("Enter")

        # 4. Extract the Payload
        print("⏳ Waiting for Fyers Server Crash (127.0.0.1 redirect)...")
        time.sleep(5) 
        
        final_url = page.url
        print(f"📍 Final URL Intercepted: {final_url}")
        
        parsed_url = urlparse(final_url)
        query_params = parse_qs(parsed_url.query)
        
        if 'auth_code' in query_params:
            auth_code = query_params['auth_code'][0]
            print("✅ Payload Extracted!")
        else:
            print("❌ Failed to extract auth_code from URL.")
            
        browser.close()

        # 4. Extract the Payload
        print("⏳ Waiting for Fyers Server Crash (127.0.0.1 redirect)...")
        time.sleep(5) 
        
        final_url = page.url
        print(f"📍 Final URL Intercepted: {final_url}")
        
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
    
    # Securely update the vault
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
