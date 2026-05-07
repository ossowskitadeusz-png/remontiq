import sys
import os
import json
from datetime import date

sys.path.append('c:/Users/TedWa/OneDrive/Dokumenty/Nowy folder (2)')
import app

# test insertion
try:
    print("Testing insertion")
    app.create_project_metadata(
        project_name="Test",
        project_description="",
        planned_start_date=date.today(),
        planned_end_date=date.today(),
        total_budget=10000.0,
        investor_name="Jan",
        crew_lead_name="Karol",
        crew_contact="123",
        scope_of_work="Test scope",
        special_conditions="",
        status="PLANNING"
    )
    print("Success")
except Exception as e:
    print("Error:", repr(e))
    if hasattr(e, 'args'):
        print(e.args)
