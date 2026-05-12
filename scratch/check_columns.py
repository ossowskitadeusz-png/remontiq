from supabase import create_client
import os

url = "https://mgrrsrgnalxtbrvzqyid.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1ncnJzcmduYWx4dGJydnpxeWlkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgwOTQ4NTksImV4cCI6MjA5MzY3MDg1OX0.LtzUjbFOb9uV3T4ptJFbNcp3UHiKl2EDbvw1d1ZZZX0"
supabase = create_client(url, key)

# We can't run raw SQL via the client easily, but we can try to insert/update a dummy and see if it fails
# Or better, just try to select it.

try:
    res = supabase.table("tasks").select("state, state_changed_by").limit(1).execute()
    print("SUCCESS: Columns 'state' and 'state_changed_by' exist.")
except Exception as e:
    print(f"FAILURE: Columns missing or error: {e}")
