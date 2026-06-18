import os
import pyotp
import psycopg2
import time
from urllib.parse import urlparse, parse_qs
from fyers_apiv3 import fyersModel
from playwright.sync_api import sync_playwright

print("👻 Waking the Phantom Browser...")

# ==========================================
# 1. LOAD & SANITIZE THE CREDENTIALS
# ==========================================
CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
# 🚨 THE FIX: .strip() removes accidental invisible spaces from GitHub Secrets
FYERS_PHONE = os.getenv("FYERS_PHONE", "").strip()        
FYERS_PIN = os.getenv("FYERS_PIN", "").strip()            
TOTP_SECRET = os.getenv("FYERS_TOTP_SECRET", "").strip()  

DB_PASSWORD = os.getenv("NEON_PASSWORD", "").strip()
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
        # Spoof a real Windows machine
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
        page.locator("input:visible").first.click()
        page.keyboard.type(FYERS_PHONE, delay=150) 
        
        # 🚨 THE FIX: Press Tab to unfocus the box and force React validation
        page.keyboard.press("Tab")
        page.wait_for_timeout(1000)

        print("⏳ Waiting for Login Button to turn blue...")
        submit_btn = page.locator("button[type='submit']:visible, button[id*='Submit']:visible").first
        
        for i in range(20): 
            if submit_btn.is_enabled():
                break
            page.wait_for_timeout(500)
            if i == 19:
                raise Exception(f"CRITICAL: Fyers rejected the Client ID length. Button stayed disabled. Check your GitHub FYERS_PHONE secret.")
        
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
        
        page.keyboard.press("Tab")
        page.wait_for_timeout(1000)

        print("⏳ Waiting for OTP Button to turn blue...")
        otp_btn = page.locator("button[type='submit']:visible, button[id*='Submit']:visible").first
        for i in range(20):
            if otp_btn.is_enabled():
                break
            page.wait_for_timeout(500)
            if i == 19:
                raise Exception("CRITICAL: Fyers rejected the TOTP code. Check your FYERS_TOTP_SECRET.")
        
        otp_btn.click()
        print("🔘 Clicked OTP Submit.")

        # --- STEP 3: PIN ---
        print("⏳ Waiting for PIN screen to render (5s)...")
        page.wait_for_timeout(5000)

        print("🔢 Injecting PIN...")
        page.locator("input:visible").first.click()
        page.keyboard.type(FYERS_PIN, delay=150)
        
        page.keyboard.press("Tab")
        page.wait_for_timeout(1000)

        print("⏳ Waiting for PIN Button to turn blue...")
        pin_btn = page.locator("button[type='submit']:visible, button[id*='Submit']:visible").first
        for i in range(20):
            if pin_btn.is_enabled():
                break
            page.wait_for_timeout(500)
            if i == 19:
                raise Exception("CRITICAL: Fyers rejected the PIN. Check your FYERS_PIN secret.")
            
        pin_btn.click()
        print("🔘 Clicked PIN Submit.")

        # --- STEP 4: ACTIVE URL SNIFFER ---
        print("⏳ Polling for final redirect payload...")
        for _ in range(40): 
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
