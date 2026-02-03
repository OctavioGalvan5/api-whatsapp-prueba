import logging
# Desactivar logs de Flask/Werkzeug para no ensuciar la salida
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

import time
import io
import pandas as pd
from app import app, db, Contact

def verify_performance():
    print("Generating large test dataset (500 rows)...")
    
    # Crear 500 contactos simulados
    # Mezcla de nuevos y existentes
    data = []
    base_phone = 5491100000000
    for i in range(500):
        phone = base_phone + i 
        
        row = {
            "Contact ID": f"PERF-TEST-{i}",
            "Telefono": str(phone),
            "Nombre": f"Test User {i}",
            "Apellido": "Performance",
            "Notas": "Performance Test Batch Import"
        }
        data.append(row)
        
    df = pd.DataFrame(data)
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_content = csv_buffer.getvalue() # str
    # Para test_client, necesitamos bytes o usar StringIO correectamente con in-memory file
    # Flask test client prefiere BytesIO para archivos
    bytes_content = csv_content.encode('utf-8')
    
    print("Initializing Flask test client...")
    client = app.test_client()
    
    # Login mock (si es necesario por la lógica de sesión)
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        
    print("Sending import request with 500 rows to /api/contacts/import...")
    
    start_time = time.time()
    try:
        data = {
            'file': (io.BytesIO(bytes_content), 'perf_test.csv')
        }
        response = client.post('/api/contacts/import', data=data, content_type='multipart/form-data')
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"Request duration: {duration:.2f} seconds")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print(f"Response: {response.json}")
            
            if duration < 5.0: 
                print("[PASS] Performance is good (< 5s for 500 rows)")
            else:
                print(f"[WARN] Performance is slower than expected ({duration:.2f}s)")
                
            # Verificar cleanup (opcional, para no llenar la BD)
            # with app.app_context():
            #     Contact.query.filter(Contact.contact_id.like('PERF-TEST-%')).delete(synchronize_session=False)
            #     db.session.commit()
            #     print("Test data cleaned up.")
                
        else:
            print(f"[FAIL] Request failed: {response.data.decode('utf-8')}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_performance()
