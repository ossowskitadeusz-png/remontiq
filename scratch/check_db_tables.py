
import os
from supabase import create_client

url = "https://mgrrsrgnalxtbrvzqyid.supabase.co"
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

tables = ["tasks", "project_metadata", "project_logs", "activity_log", "daily_logs", "expenses"]

for table in tables:
    try:
        res = supabase.table(table).select("*").limit(1).execute()
        print(f"Table {table} EXISTS.")
        if res.data:
            print(f"   Columns: {list(res.data[0].keys())}")
        else:
            print(f"   (Empty)")
    except Exception as e:
        print(f"Table {table} ERROR: {e}")
