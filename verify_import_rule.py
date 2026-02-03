import requests
import pandas as pd
import io

BASE_URL = "http://localhost:3000"

def verify_import_rule():
    print("Creating test CSV...")
    # Create a DataFrame for testing
    # Row 1: New contact, no Client ID -> Should Skip
    # Row 2: New contact, with Client ID -> Should Create
    # Row 3: Existing contact (we'll need a phone that definitely exists or create one first)
    # To reliably test Row 3, we should ensure the contact exists. 
    # But for this specific rule "Block creation if no Client ID", we mainly care about Row 1 vs Row 2.
    
    # Let's use random phones to ensure they are "new"
    import random
    rnd = random.randint(10000, 99999)
    phone_new_no_id = f"54911{rnd}0001"
    phone_new_with_id = f"54911{rnd}0002"
    client_id_valid = f"TEST-CLI-{rnd}"
    
    data = [
        {"Phone": phone_new_no_id, "Name": "Should Skip", "Contact ID": ""},
        {"Phone": phone_new_with_id, "Name": "Should Create", "Contact ID": client_id_valid},
    ]
    
    df = pd.DataFrame(data)
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_content = csv_buffer.getvalue()
    
    files = {
        'file': ('test_contacts.csv', csv_content, 'text/csv')
    }
    
    session = requests.Session()
    # Login first
    print("Logging in...")
    login_resp = session.post(f"{BASE_URL}/login", data={"password": "admin"}) # Default dev password
    if login_resp.url.endswith("/login"): # Failed login redirects back to login
         print("[WARNING] Login might have failed. URL:", login_resp.url)
    
    print(f"Sending import request to {BASE_URL}/api/contacts/import...")
    try:
        response = session.post(f"{BASE_URL}/api/contacts/import", files=files)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            # We expect:
            # - Total processed: 2
            # - Created: 1 (phone_new_with_id)
            # - Skipped/Error: 1 (phone_new_no_id) or maybe just not created.
            # The current API returns specific counters usually.
            
            print("\n--- Verification Results ---")
            print(f"Items processed: {result.get('total', 'N/A')}")
            print(f"Created/Updated: {result.get('updated', 'N/A')}") # The API might aggregate created/updated or have separate
            
            # Let's verify existence separately
            print("\nVerifying existence of contacts in DB...")
            
            # Check phone_new_no_id (Should NOT exist)
            r1 = session.get(f"{BASE_URL}/api/contacts/{phone_new_no_id}")
            if r1.status_code == 200 and r1.json().get('found'):
                print(f"[FAIL] Contact {phone_new_no_id} was created but should have been skipped.")
            else:
                print(f"[PASS] Contact {phone_new_no_id} was NOT created (Correct).")
                
            # Check phone_new_with_id (Should exist)
            r2 = session.get(f"{BASE_URL}/api/contacts/{phone_new_with_id}")
            if r2.status_code == 200 and r2.json().get('found'):
                print(f"[PASS] Contact {phone_new_with_id} was created (Correct).")
            else:
                print(f"[FAIL] Contact {phone_new_with_id} was NOT created but should have been.")
                
        else:
            print("[FAIL] Import request failed.")
            
    except Exception as e:
        print(f"Error executing request: {e}")

if __name__ == "__main__":
    verify_import_rule()
