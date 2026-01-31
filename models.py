from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Message(db.Model):
    """Modelo para almacenar mensajes de WhatsApp."""
    __tablename__ = 'whatsapp_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    wa_message_id = db.Column(db.String(100), unique=True, nullable=True)
    phone_number = db.Column(db.String(20), nullable=False, index=True)
    direction = db.Column(db.String(10), nullable=False)  # 'inbound' o 'outbound'
    message_type = db.Column(db.String(20), nullable=False)  # text, image, audio, etc.
    content = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    # Relación con estados
    statuses = db.relationship('MessageStatus', backref='message', lazy=True, order_by='MessageStatus.timestamp')
    
    @property
    def latest_status(self):
        """Obtiene el último estado del mensaje."""
        if self.statuses:
            return self.statuses[-1].status
        return None
    
    def to_dict(self):
        return {
            'id': self.id,
            'wa_message_id': self.wa_message_id,
            'phone_number': self.phone_number,
            'direction': self.direction,
            'message_type': self.message_type,
            'content': self.content,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'latest_status': self.statuses[-1].status if self.statuses else None
        }


class MessageStatus(db.Model):
    """Modelo para almacenar estados de mensajes (sent, delivered, read, failed)."""
    __tablename__ = 'whatsapp_message_statuses'
    
    id = db.Column(db.Integer, primary_key=True)
    wa_message_id = db.Column(db.String(100), db.ForeignKey('whatsapp_messages.wa_message_id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, index=True)  # sent, delivered, read, failed
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    error_code = db.Column(db.String(50), nullable=True)
    error_title = db.Column(db.String(200), nullable=True)
    error_details = db.Column(db.Text, nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'wa_message_id': self.wa_message_id,
            'status': self.status,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'error_code': self.error_code,
            'error_title': self.error_title,
            'error_details': self.error_details
        }

class Contact(db.Model):
    """Modelo para gestión de contactos (Mini-CRM)."""
    __tablename__ = 'whatsapp_contacts'
    
    phone_number = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    tags = db.Column(db.JSON, default=list)  # Lista de tags (máx 6)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    custom_field_1 = db.Column(db.String(255), nullable=True)
    custom_field_2 = db.Column(db.String(255), nullable=True)
    custom_field_3 = db.Column(db.String(255), nullable=True)
    custom_field_4 = db.Column(db.String(255), nullable=True)
    custom_field_5 = db.Column(db.String(255), nullable=True)
    custom_field_6 = db.Column(db.String(255), nullable=True)
    custom_field_7 = db.Column(db.String(255), nullable=True)
    
    def to_dict(self):
        return {
            'phone_number': self.phone_number,
            'name': self.name,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'custom_field_1': self.custom_field_1,
            'custom_field_2': self.custom_field_2,
            'custom_field_3': self.custom_field_3,
            'custom_field_4': self.custom_field_4,
            'custom_field_5': self.custom_field_5,
            'custom_field_6': self.custom_field_6,
            'custom_field_7': self.custom_field_7,
            'notes': self.notes,
            'tags': self.tags or [],
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
