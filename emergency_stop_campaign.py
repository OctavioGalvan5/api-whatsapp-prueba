from app import app, db, Campaign

def stop_campaign():
    with app.app_context():
        campaign_name = "Regularización de datos"
        # Find running campaigns matching name
        campaigns = Campaign.query.filter(
            Campaign.name.ilike(f"%{campaign_name}%"),
            Campaign.status.in_(['sending', 'scheduled'])
        ).all()
        
        if not campaigns:
            print(f"No active campaign found with name '{campaign_name}'")
            return

        for c in campaigns:
            print(f"Stopping campaign: {c.name} (ID: {c.id}) - Status: {c.status}")
            c.status = 'paused'
        
        db.session.commit()
        print("Campaign(s) stopped successfully.")

if __name__ == "__main__":
    stop_campaign()
