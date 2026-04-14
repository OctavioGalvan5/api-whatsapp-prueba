import requests, os
from dotenv import load_dotenv
load_dotenv(override=True)
t = os.getenv("WHATSAPP_API_TOKEN")
r = requests.get("https://graph.facebook.com/v21.0/debug_token", params={"input_token": t, "access_token": t})
d = r.json().get("data", {})
print("Scopes:")
for s in d.get("scopes", []):
    print(f"  - {s}")
print(f"Tipo: {d.get('type')}")
print(f"Valid: {d.get('is_valid')}")
has_catalog = "catalog_management" in d.get("scopes", [])
print(f"\ncatalog_management: {'SI' if has_catalog else 'NO - FALTA ESTE PERMISO'}")
