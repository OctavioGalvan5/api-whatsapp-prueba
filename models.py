from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pytz

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

    # Índices para optimización de queries del dashboard
    __table_args__ = (
        db.Index('ix_messages_phone_ts', 'phone_number', 'timestamp'),
        db.Index('idx_messages_timestamp', 'timestamp'),
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
    db.Column('tag_id', db.Integer, db.ForeignKey('whatsapp_tags.id'), primary_key=True),
    db.Index('idx_contact_tags_tag', 'tag_id')  # Índice para JOIN en campañas
)

class Tag(db.Model):
    """Modelo para etiquetas de contactos (normalizado)."""
    __tablename__ = 'whatsapp_tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(20), default='green')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_system = db.Column(db.Boolean, default=False, nullable=False)

    def __str__(self):
        return self.name

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color,
            'is_active': self.is_active,
            'is_system': self.is_system
        }

class Contact(db.Model):
    """Modelo para gestión de contactos (Mini-CRM)."""
    __tablename__ = 'whatsapp_contacts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # ID interno (no editable)
    contact_id = db.Column(db.String(50), unique=True, nullable=True, index=True)  # ID externo (editable por usuario)
    phone_number = db.Column(db.String(20), unique=False, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=True, index=True)
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

    # Restricción única e índices para evitar duplicados y optimizar queries
    __table_args__ = (
        db.UniqueConstraint('campaign_id', 'contact_id', name='uq_campaign_contact_log'),
        db.Index('idx_campaign_logs_campaign_status', 'campaign_id', 'status'),
        db.Index('idx_campaign_logs_campaign_contact', 'campaign_id', 'contact_id'),
    )

    contact = db.relationship('Contact', backref='campaign_logs', foreign_keys=[contact_id])


# ==========================================
# CONVERSATION CATEGORIZATION
# ==========================================

class ConversationTopic(db.Model):
    """Temas para categorizar conversaciones del chatbot."""
    __tablename__ = 'conversation_topics'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    keywords = db.Column(db.JSON, default=list)  # Lista de palabras clave
    color = db.Column(db.String(20), default='blue')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    sessions = db.relationship('ConversationSession', backref='topic', lazy='select')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'keywords': self.keywords or [],
            'color': self.color,
            'session_count': len(self.sessions) if self.sessions else 0
        }


class ConversationSession(db.Model):
    """Sesiones de conversación categorizadas automáticamente."""
    __tablename__ = 'conversation_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False, index=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('conversation_topics.id'), nullable=True)
    rating = db.Column(db.String(20), nullable=True)  # excelente, buena, neutral, mala, problematica
    started_at = db.Column(db.DateTime, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=False)
    message_count = db.Column(db.Integer, default=0)
    summary = db.Column(db.Text, nullable=True)
    auto_categorized = db.Column(db.Boolean, default=True)
    has_unanswered_questions = db.Column(db.Boolean, default=False, nullable=False)
    escalated_to_human = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_sessions_phone_started', 'phone_number', 'started_at'),
    )
    
    def to_dict(self):
        # Convertir fechas UTC a zona horaria de Argentina
        tz_argentina = pytz.timezone('America/Argentina/Buenos_Aires')

        started_at_ar = None
        if self.started_at:
            # Si la fecha no tiene tzinfo, asumimos que es UTC
            if self.started_at.tzinfo is None:
                started_at_utc = pytz.utc.localize(self.started_at)
            else:
                started_at_utc = self.started_at
            started_at_ar = started_at_utc.astimezone(tz_argentina).isoformat()

        ended_at_ar = None
        if self.ended_at:
            # Si la fecha no tiene tzinfo, asumimos que es UTC
            if self.ended_at.tzinfo is None:
                ended_at_utc = pytz.utc.localize(self.ended_at)
            else:
                ended_at_utc = self.ended_at
            ended_at_ar = ended_at_utc.astimezone(tz_argentina).isoformat()

        return {
            'id': self.id,
            'phone_number': self.phone_number,
            'topic': self.topic.to_dict() if self.topic else None,
            'topic_name': self.topic.name if self.topic else 'Sin categorizar',
            'rating': self.rating,
            'started_at': started_at_ar,
            'ended_at': ended_at_ar,
            'message_count': self.message_count,
            'summary': self.summary,
            'auto_categorized': self.auto_categorized,
            'has_unanswered_questions': self.has_unanswered_questions,
            'escalated_to_human': self.escalated_to_human
        }


# ==========================================
# RAG DOCUMENTS
# ==========================================

class RagDocument(db.Model):
    """Documentos subidos para el RAG del chatbot."""
    __tablename__ = 'rag_documents'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)  # pdf, xlsx, csv, docx, txt
    file_size = db.Column(db.Integer, nullable=False)  # bytes
    file_hash = db.Column(db.String(64), nullable=False, index=True)  # SHA256
    minio_path = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, processing, ready, error
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'file_hash': self.file_hash,
            'status': self.status,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ==========================================
# CHATBOT CONFIG
# ==========================================

class ChatbotConfig(db.Model):
    """Configuración global del chatbot."""
    __tablename__ = 'chatbot_config'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=None):
        """Obtiene un valor de configuración."""
        config = ChatbotConfig.query.filter_by(key=key).first()
        return config.value if config else default

    @staticmethod
    def set(key, value):
        """Establece un valor de configuración."""
        config = ChatbotConfig.query.filter_by(key=key).first()
        if config:
            config.value = value
        else:
            config = ChatbotConfig(key=key, value=value)
            db.session.add(config)
        db.session.commit()
        return config

    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

