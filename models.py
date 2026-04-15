from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import pytz

db = SQLAlchemy()


# ==========================================
# CRM USERS
# ==========================================

class CrmUser(db.Model):
    """Usuarios del CRM con permisos granulares."""
    __tablename__ = 'crm_users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    can_see_untagged = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    permissions   = db.relationship('CrmUserPermission',    backref='user',     lazy='joined', cascade='all, delete-orphan')
    tag_visibility = db.relationship('CrmUserTagVisibility', backref='user_vis', lazy='joined', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_permission(self, permission):
        if self.is_admin:
            return True
        return any(p.permission == permission for p in self.permissions)

    def get_permissions(self):
        return [p.permission for p in self.permissions]

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'display_name': self.display_name,
            'is_admin': self.is_admin,
            'is_active': self.is_active,
            'can_see_untagged': self.can_see_untagged,
            'permissions': self.get_permissions(),
            'tag_visibility': [v.tag_id for v in self.tag_visibility],
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class CrmUserPermission(db.Model):
    """Permisos individuales por usuario."""
    __tablename__ = 'crm_user_permissions'

    user_id = db.Column(db.Integer, db.ForeignKey('crm_users.id', ondelete='CASCADE'), primary_key=True)
    permission = db.Column(db.String(50), primary_key=True)


class CrmUserTagVisibility(db.Model):
    """Etiquetas visibles por usuario. Si no tiene filas → no ve nada (salvo admin)."""
    __tablename__ = 'crm_user_tag_visibility'

    user_id = db.Column(db.Integer, db.ForeignKey('crm_users.id', ondelete='CASCADE'), primary_key=True)
    tag_id  = db.Column(db.Integer, db.ForeignKey('whatsapp_tags.id', ondelete='CASCADE'), primary_key=True)

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
    sent_by = db.Column(db.String(100), nullable=True)  # NULL=entrante, 'bot'=chatbot, username=agente
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
            'latest_status': self.statuses[-1].status if self.statuses else None,
            'sent_by': self.sent_by
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
    created_by = db.Column(db.String(100), nullable=True)

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
# CONVERSATION NOTES (Internal team notes)
# ==========================================

class ConversationNote(db.Model):
    """Notas internas del equipo sobre conversaciones."""
    __tablename__ = 'conversation_notes'

    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        tz_argentina = pytz.timezone('America/Argentina/Buenos_Aires')
        created_ar = None
        if self.created_at:
            if self.created_at.tzinfo is None:
                created_utc = pytz.utc.localize(self.created_at)
            else:
                created_utc = self.created_at
            created_ar = created_utc.astimezone(tz_argentina).isoformat()

        return {
            'id': self.id,
            'phone_number': self.phone_number,
            'content': self.content,
            'created_at': created_ar
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
# AUTO TAG RULES
# ==========================================

class AutoTagRule(db.Model):
    """Reglas para etiquetar contactos automáticamente basándose en la conversación."""
    __tablename__ = 'auto_tag_rules'

    id = db.Column(db.Integer, primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('whatsapp_tags.id'), nullable=False)
    prompt_condition = db.Column(db.Text, nullable=False)  # Pregunta SÍ/NO para la IA
    inactivity_minutes = db.Column(db.Integer, default=30)  # Esperar X min antes de analizar
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    activated_at = db.Column(db.DateTime, default=datetime.utcnow)  # Última vez que se activó — filtra mensajes anteriores
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tag = db.relationship('Tag', backref='auto_tag_rules')

    def to_dict(self):
        return {
            'id': self.id,
            'tag_id': self.tag_id,
            'tag_name': self.tag.name if self.tag else None,
            'tag_color': self.tag.color if self.tag else None,
            'prompt_condition': self.prompt_condition,
            'inactivity_minutes': self.inactivity_minutes,
            'is_active': self.is_active,
            'activated_at': self.activated_at.isoformat() if self.activated_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ==========================================
# AUTO TAG LOG
# ==========================================

class AutoTagLog(db.Model):
    """Log de cada análisis del auto-tagger."""
    __tablename__ = 'auto_tag_logs'

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('auto_tag_rules.id', ondelete='SET NULL'), nullable=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('whatsapp_contacts.id', ondelete='SET NULL'), nullable=True)
    phone_number = db.Column(db.String(20), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('whatsapp_tags.id', ondelete='SET NULL'), nullable=True)
    result = db.Column(db.String(20), nullable=False)  # 'tagged', 'skipped', 'already_tagged', 'error'
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    rule = db.relationship('AutoTagRule', backref='logs')
    contact = db.relationship('Contact', backref='auto_tag_logs')
    tag = db.relationship('Tag', backref='auto_tag_logs')

    __table_args__ = (
        db.Index('idx_auto_tag_logs_created', 'created_at'),
        db.Index('idx_auto_tag_logs_result', 'result'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'rule_id': self.rule_id,
            'phone_number': self.phone_number,
            'contact_name': self.contact.name if self.contact else None,
            'tag_name': self.tag.name if self.tag else None,
            'result': self.result,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ==========================================
# FOLLOW-UP SEQUENCES
# ==========================================

class FollowUpSequence(db.Model):
    """Secuencias de mensajes de seguimiento automático."""
    __tablename__ = 'followup_sequences'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('whatsapp_tags.id'), nullable=False)  # Tag que dispara la secuencia
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Ventana horaria de envío (por secuencia)
    send_window_start = db.Column(db.String(5), nullable=True)   # "09:00", None = sin restricción
    send_window_end   = db.Column(db.String(5), nullable=True)   # "20:00"
    send_weekdays     = db.Column(db.JSON, nullable=True)        # [0,1,2,3,4] = Lu-Vi, None = todos

    tag = db.relationship('Tag', backref='followup_sequences')
    steps = db.relationship('FollowUpStep', backref='sequence', lazy='select', order_by='FollowUpStep.order', cascade='all, delete-orphan')
    enrollments = db.relationship('FollowUpEnrollment', backref='sequence', lazy='select', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'tag_id': self.tag_id,
            'tag_name': self.tag.name if self.tag else None,
            'is_active': self.is_active,
            'send_window_start': self.send_window_start,
            'send_window_end': self.send_window_end,
            'send_weekdays': self.send_weekdays,
            'steps': [s.to_dict() for s in self.steps],
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class FollowUpStep(db.Model):
    """Pasos individuales dentro de una secuencia de seguimiento."""
    __tablename__ = 'followup_steps'

    id = db.Column(db.Integer, primary_key=True)
    sequence_id = db.Column(db.Integer, db.ForeignKey('followup_sequences.id', ondelete='CASCADE'), nullable=False)
    order = db.Column(db.Integer, nullable=False)  # 1, 2, 3...
    delay_hours = db.Column(db.Float, nullable=False)  # Horas a esperar desde el paso anterior (o desde el tag)
    template_name = db.Column(db.String(100), nullable=False)
    template_language = db.Column(db.String(10), default='es_AR')
    template_params = db.Column(db.JSON, nullable=True)  # Parámetros variables del template
    remove_tag_on_execute = db.Column(db.Boolean, default=False)  # Quitar la etiqueta disparadora al ejecutar este paso
    # Programación fija: 'delay' (X horas desde el paso anterior) o 'fixed_time' (próximo día/hora específico)
    schedule_type = db.Column(db.String(20), default='delay')  # 'delay' | 'fixed_time'
    scheduled_weekday = db.Column(db.Integer, nullable=True)   # 0=Lunes … 6=Domingo
    scheduled_time = db.Column(db.String(5), nullable=True)    # "HH:MM" en hora local

    def to_dict(self):
        return {
            'id': self.id,
            'sequence_id': self.sequence_id,
            'order': self.order,
            'delay_hours': self.delay_hours,
            'template_name': self.template_name,
            'template_language': self.template_language,
            'template_params': self.template_params,
            'remove_tag_on_execute': self.remove_tag_on_execute or False,
            'schedule_type': self.schedule_type or 'delay',
            'scheduled_weekday': self.scheduled_weekday,
            'scheduled_time': self.scheduled_time
        }


class FollowUpEnrollment(db.Model):
    """Registro de un contacto enrollado en una secuencia de follow-up."""
    __tablename__ = 'followup_enrollments'

    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('whatsapp_contacts.id', ondelete='CASCADE'), nullable=False)
    sequence_id = db.Column(db.Integer, db.ForeignKey('followup_sequences.id', ondelete='CASCADE'), nullable=False)
    current_step = db.Column(db.Integer, default=1)  # Paso actual (1-based)
    status = db.Column(db.String(20), default='pending')  # pending, cancelled, finished
    next_send_at = db.Column(db.DateTime, nullable=True)  # Cuándo enviar el próximo mensaje
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    cancelled_at = db.Column(db.DateTime, nullable=True)

    contact = db.relationship('Contact', backref=db.backref('followup_enrollments', passive_deletes=True))

    __table_args__ = (
        db.UniqueConstraint('contact_id', 'sequence_id', name='uq_enrollment_contact_sequence'),
        db.Index('idx_enrollments_status_next', 'status', 'next_send_at'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'contact_id': self.contact_id,
            'contact_phone': self.contact.phone_number if self.contact else None,
            'contact_name': self.contact.name if self.contact else None,
            'sequence_id': self.sequence_id,
            'sequence_name': self.sequence.name if self.sequence else None,
            'current_step': self.current_step,
            'status': self.status,
            'next_send_at': self.next_send_at.isoformat() if self.next_send_at else None,
            'enrolled_at': self.enrolled_at.isoformat() if self.enrolled_at else None,
            'cancelled_at': self.cancelled_at.isoformat() if self.cancelled_at else None
        }


# ==========================================
# CATALOG PRODUCTS
# ==========================================

class CatalogProduct(db.Model):
    """Productos del catálogo de WhatsApp/Meta."""
    __tablename__ = 'catalog_products'

    retailer_id = db.Column(db.String(100), primary_key=True)
    wa_product_id = db.Column(db.String(100), nullable=True)
    name = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String(10), nullable=True)
    availability = db.Column(db.String(20), default='in_stock')  # in_stock / out_of_stock
    image_url = db.Column(db.Text, nullable=True)
    synced_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'retailer_id': self.retailer_id,
            'wa_product_id': self.wa_product_id,
            'name': self.name,
            'description': self.description,
            'price': float(self.price) if self.price is not None else None,
            'currency': self.currency,
            'availability': self.availability,
            'image_url': self.image_url,
            'synced_at': self.synced_at.isoformat() if self.synced_at else None,
        }


# ==========================================
# ORDERS
# ==========================================

ACTIVE_ORDER_STATUSES = ('pendiente', 'confirmado', 'pendiente_envio', 'enviado')
TERMINAL_ORDER_STATUSES = ('entregado', 'cancelado', 'terminado')

class Order(db.Model):
    """Órdenes de compra (WhatsApp + manuales)."""
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('whatsapp_contacts.id', ondelete='SET NULL'), nullable=True)
    phone_number = db.Column(db.String(20), nullable=False)
    source = db.Column(db.String(20), default='whatsapp')  # whatsapp / manual
    wa_message_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(30), default='pendiente')
    payment_status = db.Column(db.String(20), default='sin_pagar')
    payment_method = db.Column(db.String(20), nullable=True)
    total = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String(10), default='ARS')
    shipping_address = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    seen_at = db.Column(db.DateTime, nullable=True)
    seen_by_id = db.Column(db.Integer, db.ForeignKey('crm_users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('crm_users.id', ondelete='SET NULL'), nullable=True)
    last_edited_by_id = db.Column(db.Integer, db.ForeignKey('crm_users.id', ondelete='SET NULL'), nullable=True)
    terminated_at = db.Column(db.DateTime, nullable=True)
    terminated_by_id = db.Column(db.Integer, db.ForeignKey('crm_users.id', ondelete='SET NULL'), nullable=True)

    contact = db.relationship('Contact', backref=db.backref('orders', passive_deletes=True))
    items = db.relationship('OrderItem', backref='order', cascade='all, delete-orphan', lazy='select')
    seen_by = db.relationship('CrmUser', foreign_keys=[seen_by_id])
    created_by = db.relationship('CrmUser', foreign_keys=[created_by_id])
    last_edited_by = db.relationship('CrmUser', foreign_keys=[last_edited_by_id])
    terminated_by = db.relationship('CrmUser', foreign_keys=[terminated_by_id])

    __table_args__ = (
        db.Index('idx_orders_contact', 'contact_id'),
        db.Index('idx_orders_status', 'status'),
        db.Index('idx_orders_seen_at', 'seen_at'),
        db.Index('idx_orders_created_at', 'created_at'),
    )

    @property
    def order_number(self):
        return f"#{self.id:04d}"

    @property
    def is_active_order(self):
        return self.status in ACTIVE_ORDER_STATUSES

    def to_dict(self):
        tz_ar = pytz.timezone('America/Argentina/Buenos_Aires')

        def fmt(dt):
            if not dt:
                return None
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            return dt.astimezone(tz_ar).isoformat()

        return {
            'id': self.id,
            'order_number': self.order_number,
            'contact_id': self.contact_id,
            'contact_name': self.contact.name if self.contact else None,
            'phone_number': self.phone_number,
            'source': self.source,
            'wa_message_id': self.wa_message_id,
            'status': self.status,
            'payment_status': self.payment_status,
            'payment_method': self.payment_method,
            'total': float(self.total) if self.total is not None else None,
            'currency': self.currency,
            'shipping_address': self.shipping_address,
            'notes': self.notes,
            'seen_at': fmt(self.seen_at),
            'seen_by': self.seen_by.display_name if self.seen_by else None,
            'created_at': fmt(self.created_at),
            'updated_at': fmt(self.updated_at),
            'created_by': self.created_by.display_name if self.created_by else None,
            'last_edited_by': self.last_edited_by.display_name if self.last_edited_by else None,
            'terminated_at': fmt(self.terminated_at),
            'terminated_by': self.terminated_by.display_name if self.terminated_by else None,
            'items': [i.to_dict() for i in self.items],
        }


class OrderItem(db.Model):
    """Items individuales de una orden."""
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    retailer_id = db.Column(db.String(100), nullable=False)
    product_name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default='ARS')

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'retailer_id': self.retailer_id,
            'product_name': self.product_name,
            'quantity': self.quantity,
            'unit_price': float(self.unit_price) if self.unit_price is not None else None,
            'currency': self.currency,
            'subtotal': float(self.unit_price * self.quantity) if self.unit_price is not None else None,
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

