from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Message(db.Model):
    """Modelo para almacenar mensajes de WhatsApp."""
    __tablename__ = 'whatsapp_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    wa_message_id = db.Column(db.String(100), unique=True, nullable=True)
    phone_number = db.Column(db.String(20), nullable=False, index=True)
    direction = db.Column(db.String(10), nullable=False, index=True)  # 'inbound' o 'outbound'
    message_type = db.Column(db.String(20), nullable=False)  # text, image, audio, etc.
    content = db.Column(db.Text, nullable=True)
    media_id = db.Column(db.String(100), nullable=True)
    media_url = db.Column(db.String(255), nullable=True)
    caption = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    # Relación con estados — lazy='joined' carga statuses en un solo JOIN al traer mensajes
    statuses = db.relationship('MessageStatus', backref='message', lazy='joined', order_by='MessageStatus.timestamp')

    # Índice compuesto para queries por contacto ordenadas por fecha
    # Si la tabla ya existe, crear manualmente:
    #   CREATE INDEX IF NOT EXISTS ix_messages_phone_ts ON whatsapp_messages (phone_number, timestamp);
    __table_args__ = (
        db.Index('ix_messages_phone_ts', 'phone_number', 'timestamp'),
    )
    
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
            'media_url': self.media_url,
            'caption': self.caption,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'latest_status': self.statuses[-1].status if self.statuses else None
        }


class MessageStatus(db.Model):
    """Modelo para almacenar estados de mensajes (sent, delivered, read, failed)."""
    __tablename__ = 'whatsapp_message_statuses'

    id = db.Column(db.Integer, primary_key=True)
    wa_message_id = db.Column(db.String(100), db.ForeignKey('whatsapp_messages.wa_message_id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, index=True)  # sent, delivered, read, failed
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
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

# Tabla de asociación Contacto-Etiqueta (usa contact_id después de migración)
contact_tags = db.Table('whatsapp_contact_tags',
    db.Column('contact_id', db.Integer, db.ForeignKey('whatsapp_contacts.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('whatsapp_tags.id'), primary_key=True)
)

class Tag(db.Model):
    """Modelo para etiquetas de contactos (normalizado)."""
    __tablename__ = 'whatsapp_tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(20), default='green')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __str__(self):
        return self.name

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color
        }

class Contact(db.Model):
    """Modelo para gestión de contactos (Mini-CRM)."""
    __tablename__ = 'whatsapp_contacts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # ID interno (no editable)
    contact_id = db.Column(db.String(50), unique=True, nullable=True, index=True)  # ID externo (editable por usuario)
    phone_number = db.Column(db.String(20), unique=False, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    tags_json = db.Column('tags', db.JSON, default=list)  # Legacy JSON, usar 'tags' relationship
    tags = db.relationship('Tag', secondary=contact_tags, backref='contacts')
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
            'id': self.id,
            'contact_id': self.contact_id,
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
            'tags': [t.name for t in self.tags],
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Campaign(db.Model):
    """Modelo para campañas de marketing masivo."""
    __tablename__ = 'whatsapp_campaigns'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    template_name = db.Column(db.String(100), nullable=False)
    template_language = db.Column(db.String(10), default='es_AR')
    tag_id = db.Column(db.Integer, db.ForeignKey('whatsapp_tags.id'), nullable=False)
    status = db.Column(db.String(20), default='draft')  # draft, sending, completed, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=True)
    variables = db.Column(db.JSON, nullable=True)  # Mapping {"1": "first_name", "2": "custom_field_1"}

    tag = db.relationship('Tag', backref='campaigns')
    logs = db.relationship('CampaignLog', backref='campaign', lazy='select')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'template_name': self.template_name,
            'template_language': self.template_language,
            'tag_name': self.tag.name if self.tag else None,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


class CampaignLog(db.Model):
    """Registro individual de envío dentro de una campaña."""
    __tablename__ = 'whatsapp_campaign_logs'

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('whatsapp_campaigns.id'), nullable=False)
    contact_id = db.Column(db.Integer, db.ForeignKey('whatsapp_contacts.id'), nullable=True)  # Nuevo: referencia por ID
    contact_phone = db.Column(db.String(20), nullable=False)  # Mantener para histórico
    message_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, sent, failed, delivered, read
    error_detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    contact = db.relationship('Contact', backref='campaign_logs', foreign_keys=[contact_id])
