"""
Script para diagnosticar teléfonos duplicados en campañas.
Ejecutar: python debug_duplicate_phones.py
"""
import os
import sys

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Contact, Tag, Campaign, CampaignLog
from sqlalchemy import func

def check_duplicate_phones_in_tag(tag_id):
    """Verifica si hay teléfonos duplicados en un tag específico."""
    with app.app_context():
        tag = Tag.query.get(tag_id)
        if not tag:
            print(f"Tag {tag_id} no encontrado")
            return
        
        print(f"\n=== Análisis del Tag: {tag.name} (ID: {tag_id}) ===\n")
        
        # Obtener contactos con este tag
        contacts = Contact.query.filter(Contact.tags.any(Tag.id == tag_id)).all()
        print(f"Total contactos con este tag: {len(contacts)}")
        
        # Buscar duplicados por teléfono
        phone_counts = {}
        for c in contacts:
            if c.phone_number not in phone_counts:
                phone_counts[c.phone_number] = []
            phone_counts[c.phone_number].append(c)
        
        duplicates = {phone: contacts for phone, contacts in phone_counts.items() if len(contacts) > 1}
        
        if duplicates:
            print(f"\n⚠️  DUPLICADOS ENCONTRADOS: {len(duplicates)} teléfonos con múltiples entradas\n")
            for phone, contacts in list(duplicates.items())[:10]:  # Mostrar máximo 10
                print(f"📱 {phone}:")
                for c in contacts:
                    print(f"   - ID: {c.id}, Contact ID: {c.contact_id}, Nombre: {c.name}")
        else:
            print("\n✅ No se encontraron teléfonos duplicados en este tag.")

def check_campaign_logs(campaign_id):
    """Verifica logs duplicados en una campaña."""
    with app.app_context():
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            print(f"Campaña {campaign_id} no encontrada")
            return
        
        print(f"\n=== Análisis de Campaña: {campaign.name} (ID: {campaign_id}) ===\n")
        
        logs = CampaignLog.query.filter_by(campaign_id=campaign_id).all()
        print(f"Total logs: {len(logs)}")
        
        # Buscar duplicados por teléfono
        phone_counts = {}
        for log in logs:
            if log.contact_phone not in phone_counts:
                phone_counts[log.contact_phone] = []
            phone_counts[log.contact_phone].append(log)
        
        duplicates = {phone: logs for phone, logs in phone_counts.items() if len(logs) > 1}
        
        if duplicates:
            print(f"\n⚠️  DUPLICADOS EN LOGS: {len(duplicates)} teléfonos con múltiples envíos\n")
            for phone, logs in list(duplicates.items())[:10]:
                print(f"📱 {phone}:")
                for log in logs:
                    print(f"   - Log ID: {log.id}, Contact ID: {log.contact_id}, Status: {log.status}")
        else:
            print("\n✅ No se encontraron logs duplicados para el mismo teléfono.")

def list_campaigns():
    """Lista las campañas disponibles."""
    with app.app_context():
        campaigns = Campaign.query.order_by(Campaign.created_at.desc()).limit(10).all()
        print("\n=== Últimas 10 Campañas ===\n")
        for c in campaigns:
            print(f"ID: {c.id} | {c.name} | Tag: {c.tag.name if c.tag else 'N/A'} | Status: {c.status}")

if __name__ == "__main__":
    print("=== Diagnóstico de Duplicados en Campañas ===")
    
    # Listar campañas
    list_campaigns()
    
    # Pedir ID de campaña
    campaign_id = input("\nIngrese ID de campaña a analizar (o Enter para saltar): ").strip()
    if campaign_id:
        check_campaign_logs(int(campaign_id))
        
        # Obtener tag de la campaña para análisis
        with app.app_context():
            camp = Campaign.query.get(int(campaign_id))
            if camp and camp.tag_id:
                check_duplicate_phones_in_tag(camp.tag_id)
