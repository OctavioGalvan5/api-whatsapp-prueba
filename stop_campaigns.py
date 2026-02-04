from app import app, db, Campaign, CampaignLog

def stop_campaigns():
    with app.app_context():
        # Find running campaigns
        running_campaigns = Campaign.query.filter_by(status='sending').all()
        
        if not running_campaigns:
            print("No campaigns currently in 'sending' status.")
            return

        for camp in running_campaigns:
            print(f"Stopping campaign: {camp.name} (ID: {camp.id})")
            
            # 1. Update campaign status
            camp.status = 'paused_limit'
            
            # 2. Update all pending logs to 'paused_limit' so the worker loop runs out of items
            # Using bulk update for speed
            result = db.session.query(CampaignLog).filter_by(
                campaign_id=camp.id, 
                status='pending'
            ).update({CampaignLog.status: 'paused_limit'}, synchronize_session=False)
            
            print(f"  - Updated {result} pending logs to 'paused_limit'.")
            
            db.session.commit()
            print(f"  - Campaign {camp.name} stopped successfully.")

if __name__ == "__main__":
    stop_campaigns()
