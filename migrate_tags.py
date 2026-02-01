"""
Script de migración: convierte tags JSON de contactos a la tabla normalizada Tag + contact_tags.
Ejecutar UNA VEZ después de hacer deploy con los nuevos modelos:
    python migrate_tags.py
"""
import sys
sys.path.insert(0, '.')

from app import app
from models import db, Tag, contact_tags


def migrate():
    with app.app_context():
        db.create_all()

        # Leer tags JSON directamente con SQL (evita conflicto con el nuevo atributo 'tags' del modelo)
        rows = db.session.execute(
            db.text("SELECT phone_number, tags FROM whatsapp_contacts WHERE tags IS NOT NULL AND tags::text != '[]'")
        ).fetchall()

        if not rows:
            print("No hay tags JSON que migrar.")
            return

        tag_cache = {}  # nombre -> Tag object
        total_links = 0
        skipped = 0

        for phone, tags_json in rows:
            if not tags_json:
                continue
            for tag_name in tags_json:
                tag_name = tag_name.strip()
                if not tag_name:
                    continue

                # Crear Tag si no existe
                if tag_name not in tag_cache:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db.session.add(tag)
                        db.session.flush()
                    tag_cache[tag_name] = tag

                # Crear enlace si no existe
                existing = db.session.execute(
                    db.text("SELECT 1 FROM whatsapp_contact_tags WHERE contact_phone = :phone AND tag_id = :tid"),
                    {'phone': phone, 'tid': tag_cache[tag_name].id}
                ).first()

                if not existing:
                    db.session.execute(
                        db.text("INSERT INTO whatsapp_contact_tags (contact_phone, tag_id) VALUES (:phone, :tid)"),
                        {'phone': phone, 'tid': tag_cache[tag_name].id}
                    )
                    total_links += 1
                else:
                    skipped += 1

        db.session.commit()
        print(f"Migración completada:")
        print(f"  Tags únicos creados/encontrados: {len(tag_cache)}")
        print(f"  enlaces nuevos: {total_links}")
        print(f"  enlaces ya existentes (skipped): {skipped}")


if __name__ == '__main__':
    migrate()
