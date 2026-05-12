from supabase import create_client
import json

url = "https://mgrrsrgnalxtbrvzqyid.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1ncnJzcmduYWx4dGJydnpxeWlkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgwOTQ4NTksImV4cCI6MjA5MzY3MDg1OX0.LtzUjbFOb9uV3T4ptJFbNcp3UHiKl2EDbvw1d1ZZZX0"
supabase = create_client(url, key)

res = supabase.table("tasks").select("*").limit(1).execute()
print("KOLUMNY:")
if res.data:
    for k in sorted(res.data[0].keys()):
        print(f" - {k}")

res_all = supabase.table("tasks").select("commercial_status, kanban_status, execution_status").execute()
if res_all.data:
    print("\nSTATU SY:")
    print("commercial_status:", sorted(list(set(str(r.get('commercial_status')) for r in res_all.data))))
    print("kanban_status:", sorted(list(set(str(r.get('kanban_status')) for r in res_all.data))))
    print("execution_status:", sorted(list(set(str(r.get('execution_status')) for r in res_all.data))))

print("\nCOUNTS:")
print("Total:", len(res_all.data))
