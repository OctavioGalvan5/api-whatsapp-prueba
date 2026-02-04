"""
Script to FORCE immediate categorization of all conversations.
Ignores the 15-minute inactivity rule.
Run: python force_categorize.py
"""
import os
import sys
import logging

# Configure logging to see output
logging.basicConfig(level=logging.INFO)

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
import conversation_categorizer

# OVERRIDE configuration to force immediate processing
print("⚡ Forcing immediate categorization (0 min inactivity)...")
conversation_categorizer.INACTIVITY_MINUTES = 0 

# Run the job
if __name__ == "__main__":
    conversation_categorizer.run_categorization(app.app_context())
    print("✅ Done! Check /sessions to see results.")
