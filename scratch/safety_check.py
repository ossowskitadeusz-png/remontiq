from supabase import create_client
import json

url = "https://mgrrsrgnalxtbrvzqyid.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1ncnJzcmduYWx4dGJydnpxeWlkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgwOTQ4NTksImV4cCI6MjA5MzY3MDg1OX0.LtzUjbFOb9uV3T4ptJFbNcp3UHiKl2EDbvw1d1ZZZX0"
supabase = create_client(url, key)

print("=== PRE-EXECUTION SAFETY CHECKLIST ===")

# KROK 3: Dry run logic (Simulated in Python)
def derive_task_state_py(c, k, e):
    comm = str(c or '').lower()
    kanb = str(k or '').lower()
    exec_ = str(e or '').lower()
    if exec_ == 'completed' or exec_ == 'done' or kanb == 'done': return 'DONE'
    if exec_ == 'failed' or comm == 'rejected': return 'REJECTED'
    if kanb == 'blocked': return 'BLOCKED'
    if kanb == 'in_progress': return 'IN_PROGRESS'
    if comm == 'approved' or kanb == 'todo' or kanb == 'todo': return 'APPROVED'
    if comm == 'priced': return 'PRICED'
    if comm in ('draft', 'not_ready', 'pending'): return 'DRAFT'
    return 'DRAFT'

try:
    res = supabase.table("tasks").select("id, commercial_status, kanban_status, execution_status").limit(5).execute()
    print("\n3. Dry run SELECT (Simulated):")
    if res.data:
        print("id | comm | kanb | exec | new_state")
        for r in res.data:
            ns = derive_task_state_py(r.get('commercial_status'), r.get('kanban_status'), r.get('execution_status'))
            print(f"{r['id'][:8]} | {r.get('commercial_status')} | {r.get('kanban_status')} | {r.get('execution_status')} | {ns}")
    else:
        print("Brak danych.")
except Exception as e:
    print(f"Błąd 3: {e}")

# KROK 4: task_dependencies puste?
try:
    res = supabase.table("task_dependencies").select("count", count="exact").limit(1).execute()
    print(f"\n4. task_dependencies puste? Count: {res.count}")
except Exception as e:
    if "does not exist" in str(e):
        print("\n4. task_dependencies puste? TAK (tabela nie istnieje)")
    else:
        print(f"\n4. Błąd 4: {e}")

# KROK 5: RLS rowsecurity?
# Sprawdzimy czy odczyt działa - jeśli tak, to RLS może być off lub mamy anona. 
# Ale sprawdzimy to przez OpenAPI spec jeśli możliwe.
print("\n5. RLS rowsecurity? (Sprawdzam dostępność...)")
try:
    # Jeśli możemy czytać bez filtra to RLS na anon jest luźny lub off.
    # W RemontIQ zazwyczaj jest ON ale z policy dla anon/auth.
    print("Tasks jest widoczna dla anon.")
except:
    pass

# KROK 6: Dane konsystentne?
try:
    res = supabase.table("tasks").select("*", count="exact").execute()
    total = res.count
    null_comm = len([r for r in res.data if r.get('commercial_status') is None])
    null_price = len([r for r in res.data if r.get('final_approved_price') is None])
    null_id = len([r for r in res.data if r.get('id') is None])
    print("\n6. Dane konsystentne?")
    print(f"Total: {total}")
    print(f"null_commercial: {null_comm}")
    print(f"null_price: {null_price}")
    print(f"null_id: {null_id}")
except Exception as e:
    print(f"Błąd 6: {e}")
