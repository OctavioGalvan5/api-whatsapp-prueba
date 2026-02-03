from app import app, db, Campaign, CampaignLog, Contact, Tag, contact_tags
from sqlalchemy import func

def debug_campaign():
    with app.app_context():
        # 1. Find the campaign
        campaign_name = "Regularización de datos"
        campaign = Campaign.query.filter(Campaign.name.ilike(f"%{campaign_name}%")).first()
        
        if not campaign:
            print(f"Campaign '{campaign_name}' not found.")
            # List validation
            candidates = Campaign.query.order_by(Campaign.created_at.desc()).limit(5).all()
            print("Latest campaigns:", [c.name for c in candidates])
            return

        print(f"Analyzing Campaign: {campaign.name} (ID: {campaign.id})")
        print(f"Status: {campaign.status}")
        print(f"Tag ID: {campaign.tag_id}")

        # 2. Analyze Logs
        total_logs = CampaignLog.query.filter_by(campaign_id=campaign.id).count()
        unique_contact_ids = db.session.query(CampaignLog.contact_id)\
            .filter_by(campaign_id=campaign.id)\
            .distinct().count()
        
        print(f"Total Logs: {total_logs}")
        print(f"Unique Contact IDs in Logs: {unique_contact_ids}")
        
        if total_logs > unique_contact_ids:
            print("WARNING: Duplicate logs found for same contact_id!")
            # Show example
            dupes = db.session.query(CampaignLog.contact_id, func.count(CampaignLog.id))\
                .filter_by(campaign_id=campaign.id)\
                .group_by(CampaignLog.contact_id)\
                .having(func.count(CampaignLog.id) > 1)\
                .limit(5).all()
            print(f"Sample duplicates: {dupes}")

        # 3. Analyze Contacts with Tag
        tag_id = campaign.tag_id
        contacts_with_tag = Contact.query.filter(Contact.tags.any(Tag.id == tag_id)).count()
        print(f"Contacts with Tag ID {tag_id}: {contacts_with_tag}")

        # 4. Check for Duplicate Phones in Contacts
        print("Checking for duplicate phones in all contacts...")
        phone_dupes = db.session.query(Contact.phone_number, func.count(Contact.id))\
            .group_by(Contact.phone_number)\
            .having(func.count(Contact.id) > 1)\
            .count()
        print(f"Phone numbers appearing more than once: {phone_dupes}")

        # 5. Check for duplicate pairs in contact_tags
        print("Checking for duplicates in contact_tags table...")
        tag_dupes = db.session.query(contact_tags.c.contact_id, contact_tags.c.tag_id, func.count('*'))\
            .group_by(contact_tags.c.contact_id, contact_tags.c.tag_id)\
            .having(func.count('*') > 1)\
            .count()
        print(f"Duplicate (contact_id, tag_id) pairs: {tag_dupes}")

if __name__ == "__main__":
    debug_campaign()
