from app import app, db
from models import CampaignLog, MessageStatus

def sync_campaign_statuses():
    """
    Sincroniza los estados 'read' y 'delivered' de la tabla de mensajes
    hacia los logs de campaña para corregir datos históricos.
    """
    with app.app_context():
        # Obtener logs que no estén ya finalizados (read/failed)
        print("Iniciando sincronización de estados...")
        logs = CampaignLog.query.filter(~CampaignLog.status.in_(['read', 'failed'])).all()
        
        updated_count = 0
        for log in logs:
            if not log.message_id:
                continue
                
            # Buscar el estado más avanzado en MessageStatus
            # Prioridad: read > delivered > sent
            statuses = MessageStatus.query.filter_by(wa_message_id=log.message_id).all()
            if not statuses:
                continue
                
            status_map = {s.status: s for s in statuses}
            
            new_status = None
            error_detail = None
            
            if 'read' in status_map:
                new_status = 'read'
            elif 'failed' in status_map:
                new_status = 'failed'
                error_detail = status_map['failed'].error_details
            elif 'delivered' in status_map:
                new_status = 'delivered'
            
            # Solo actualizar si es un estado "mejor" o diferente que avance
            if new_status and new_status != log.status:
                log.status = new_status
                if error_detail:
                    log.error_detail = error_detail
                updated_count += 1
                print(f"Update Log {log.id} ({log.contact_phone}): {log.status} -> {new_status}")
        
        if updated_count > 0:
            db.session.commit()
            print(f"✅ Se actualizaron {updated_count} registros de campaña.")
        else:
            print("No se encontraron registros desactualizados.")

if __name__ == "__main__":
    sync_campaign_statuses()
