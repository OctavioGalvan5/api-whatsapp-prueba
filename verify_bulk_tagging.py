import logging
# Desactivar logs de Flask/Werkzeug
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

import time
import io
import pandas as pd
from app import app, db, Contact, Tag

def verify_bulk_tagging():
    TEST_TAG = "PERF_TAG_TEST"
    CONTACT_PREFIX = "TAG-TEST-"
    COUNT = 1000  # Probar con 1000 para no tardar tanto, si es N+1 se notará igual.
    
    print(f"--- Setting up test data ({COUNT} contacts) ---")
    
    with app.app_context():
        # Clean previous run
        Contact.query.filter(Contact.contact_id.like(f'{CONTACT_PREFIX}%')).delete(synchronize_session=False)
        Tag.query.filter_by(name=TEST_TAG).delete()
        db.session.commit()
        
        # Create contacts
        new_contacts = []
        base_phone = 5491190000000
        for i in range(COUNT):
            c = Contact(
                contact_id=f"{CONTACT_PREFIX}{i}",
                phone_number=str(base_phone + i),
                name=f"Tag Test User {i}"
            )
            new_contacts.append(c)
        
        db.session.bulk_save_objects(new_contacts)
        db.session.commit()
        print("Contacts created.")

        # Get IDs back
        contacts = Contact.query.filter(Contact.contact_id.like(f'{CONTACT_PREFIX}%')).all()
        contact_ids = [c.id for c in contacts]

        print("--- Starting Bulk Tagging Request (UI Endpoint) ---")
        client = app.test_client()
        
        # MOCK LOGIN
        with client.session_transaction() as sess:
            sess['logged_in'] = True
        
        start_time = time.time()
        
        data = {
            'contact_ids': contact_ids,
            'tag': TEST_TAG,
            'action': 'add'
        }
        
        response = client.post('/api/contacts/bulk-tags', json=data)
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"Request duration: {duration:.2f} seconds")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json}")
        
        if duration > 5.0:
            print("[FAIL] Performance is too slow (>5s). Likely N+1 query issue on tags.")
        else:
            print("[PASS] Performance is acceptable.")

        # CLEANUP
        print("--- Cleaning up ---")
        Contact.query.filter(Contact.contact_id.like(f'{CONTACT_PREFIX}%')).delete(synchronize_session=False)
        Tag.query.filter_by(name=TEST_TAG).delete()
        db.session.commit()
        print("Cleanup done.")

if __name__ == "__main__":
    verify_bulk_tagging()
