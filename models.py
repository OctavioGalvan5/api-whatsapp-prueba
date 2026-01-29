from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Message(db.Model):
    """Modelo para almacenar mensajes de WhatsApp."""
    __tablename__ = 'whatsapp_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    wa_message_id = db.Column(db.String(100), unique=True, nullable=True)
    phone_number = db.Column(db.String(20), nullable=False)
    direction = db.Column(db.String(10), nullable=False)  # 'inbound' o 'outbound'
    message_type = db.Column(db.String(20), nullable=False)  # text, image, audio, etc.
    content = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
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
    status = db.Column(db.String(20), nullable=False)  # sent, delivered, read, failed
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
