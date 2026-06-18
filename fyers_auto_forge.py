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
        # Launch headless browser (invisible)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("🌐 Phantom navigating to Fyers Login...")
        page.goto(login_url)

        # 1. Enter Phone Number / Login ID
        print("⏳ Waiting for Client ID box...")
        # Rely on the placeholder text or type attribute instead of fragile IDs
        page.locator("input[type='text'], input[placeholder*='Client ID'], input[placeholder*='Mobile']").first.wait_for(state="visible", timeout=15000)
        page.locator("input[type='text'], input[placeholder*='Client ID'], input[placeholder*='Mobile']").first.fill(FYERS_PHONE)
        
        # Click the first visible button (usually 'Continue' or 'Login')
        page.locator("button:visible").first.click()
        print("👤 Inserted Client ID.")

        # 2. Enter TOTP (Mathematical Generation)
        print("⏳ Waiting for OTP fields to render...")
        # Fyers OTP usually has 6 number-type inputs
        page.locator("input[type='number'], input[type='password']").first.wait_for(state="visible", timeout=15000)
        
        totp = pyotp.TOTP(TOTP_SECRET)
        current_code = totp.now()
        
        # Find all the visible input boxes for the OTP
        otp_boxes = page.locator("input[type='number']:visible, input[type='password']:visible").all()
        
        if len(otp_boxes) >= 6:
            for i, digit in enumerate(current_code):
                otp_boxes[i].fill(digit)
        else:
            # Fallback: if it's a single text box now
            otp_boxes[0].fill(current_code)
            
        # Click the next 'Continue/Submit' button
        page.locator("button:visible").first.click()
        print("🔐 Mathematical TOTP Inserted.")

        # 3. Enter PIN
        print("⏳ Waiting for PIN fields to render...")
        time.sleep(2) # Brief pause for UI transition
        
        page.locator("input[type='number'], input[type='password']").first.wait_for(state="visible", timeout=15000)
        
        pin_boxes = page.locator("input[type='number']:visible, input[type='password']:visible").all()
        
        if len(pin_boxes) >= 4:
             for i, digit in enumerate(FYERS_PIN):
                 pin_boxes[i].fill(digit)
        else:
            # Fallback for single box
            pin_boxes[0].fill(FYERS_PIN)
            
        page.locator("button:visible").first.click()
        print("🔢 PIN Inserted.")

        # 4. Extract the Payload
        print("⏳ Waiting for Fyers Server Crash (127.0.0.1 redirect)...")
        time.sleep(5) # Crucial: Wait for the final redirect
        
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
