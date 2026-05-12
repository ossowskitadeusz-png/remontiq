from supabase import create_client
import json

url = "https://mgrrsrgnalxtbrvzqyid.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1ncnJzcmduYWx4dGJydnpxeWlkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgwOTQ4NTksImV4cCI6MjA5MzY3MDg1OX0.LtzUjbFOb9uV3T4ptJFbNcp3UHiKl2EDbvw1d1ZZZX0"
supabase = create_client(url, key)

print("=== FINAL SYSTEM VERIFICATION (No Emojis) ===")

# 1. Violations
try:
    res = supabase.table("tasks").select("id, state").execute()
    valid_states = ["DRAFT", "PRICED", "APPROVED", "IN_PROGRESS", "BLOCKED", "DONE", "REJECTED"]
    violations = [r for r in res.data if r.get('state') not in valid_states]
    print(f"1. Violations count: {len(violations)}")
    if len(violations) == 0:
        print("   SUCCESS: All records have valid state.")
except Exception as e:
    print(f"1. Error: {e}")

# 2. Test Constraint
try:
    tid = res.data[0]['id']
    supabase.table("tasks").update({"state": "HACKER_STATE"}).eq("id", tid).execute()
    print("2. Test Constraint: FAILED (Accepted invalid state)")
except Exception as e:
    print(f"2. Test Constraint: PASSED (Rejected invalid state: {str(e)[:40]}...)")

# 3. Python Service
try:
    import sys
    import os
    sys.path.append(os.getcwd())
    from services.ordering_service import OrderingService
    methods = [m for m in dir(OrderingService) if not m.startswith('_')]
    expected = ["get_task_dependencies", "reorder_tasks_in_phase", "move_task_up", "move_task_down", "get_ordered_tasks"]
    all_present = all(m in methods for m in expected)
    print(f"3. Python Service: {'OK' if all_present else 'MISSING'}")
    print(f"   Methods: {methods}")
except Exception as e:
    print(f"3. Error: {e}")
