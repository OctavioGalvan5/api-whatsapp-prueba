from app import app, Campaign

def check_status():
    with app.app_context():
        sending = Campaign.query.filter_by(status='sending').count()
        print(f"Campaigns in 'sending' status: {sending}")
        
        if sending > 0:
            camps = Campaign.query.filter_by(status='sending').all()
            for c in camps:
                print(f" - {c.name} (ID: {c.id})")

if __name__ == "__main__":
    check_status()
