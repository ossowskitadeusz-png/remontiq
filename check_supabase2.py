from supabase import create_client
import json

url = "https://mgrrsrgnalxtbrvzqyid.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1ncnJzcmduYWx4dGJydnpxeWlkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgwOTQ4NTksImV4cCI6MjA5MzY3MDg1OX0.LtzUjbFOb9uV3T4ptJFbNcp3UHiKl2EDbvw1d1ZZZX0"
supabase = create_client(url, key)

try:
    print("Testing insertion")
    supabase.table("project_metadata").insert({
        "project_name": "Test",
        "project_description": "",
        "planned_start_date": "2026-05-08",
        "planned_end_date": "2026-06-08",
        "total_budget": 10000.0,
        "investor_name": "Jan",
        "crew_lead_name": "Karol",
        "crew_contact": "123",
        "scope_of_work": "Test scope",
        "special_conditions": "",
        "status": "PLANNING"
    }).execute()
    print("Success")
except Exception as e:
    print("Error details:", repr(e))
    if hasattr(e, 'message'): print(e.message)
    if hasattr(e, 'details'): print(e.details)
    try:
        err_json = json.dumps(e.args[0] if e.args else None, indent=2)
        print("JSON err:", err_json)
    except:
        pass
