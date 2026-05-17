"""
RemontIQ — Weryfikacja stanu systemu
Sprawdza: baza danych, tabele, kluczowe kolumny, dane testowe
"""
import sys
import os
from supabase import create_client

# Dynamicznie pobierz dane z env lub .streamlit/secrets.toml
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    try:
        import toml
        secrets_path = os.path.join(".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            secrets = toml.load(secrets_path)
            SUPABASE_URL = secrets.get("supabase", {}).get("url")
            SUPABASE_KEY = secrets.get("supabase", {}).get("key")
    except Exception:
        pass

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Missing SUPABASE_URL or SUPABASE_KEY environment variables.")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def check(label, fn):
    try:
        result = fn()
        print(f"  ✅ {label}: {result}")
    except Exception as e:
        print(f"  ❌ {label}: {e}")

print("\n" + "="*60)
print("  RemontIQ — WERYFIKACJA SYSTEMU")
print("="*60)

# 1. Połączenie z bazą
print("\n📡 POŁĄCZENIE Z SUPABASE:")
check("Supabase URL dostępny", lambda: supabase.table("project_metadata").select("id").limit(1).execute().data is not None)

# 2. Tabele i kolumny
print("\n🗄️  TABELE GŁÓWNE:")
tables = {
    "project_metadata": "id, project_name, status, total_budget, planned_start_date, planned_end_date",
    "tasks": "id, name, kanban_status, is_blocked, blocker_reason",
    "crew_requests": "id, title, status, linked_task_id, investor_note, expected_delivery_date",
    "task_blockers": "id, task_id, blocker_type, is_resolved",
    "task_inspection": "id, task_id, inspection_status, submitted_at",
    "decisions": "id, title, status, due_date",
    "issues": "id, title, severity, status",
    "expenses": "id, description, amount",
    "materials": "id, name, status",
    "rooms": "id, name",
    "daily_logs": "id, content, date",
}

for table, cols in tables.items():
    def _check(t=table, c=cols):
        res = supabase.table(t).select(c).limit(1).execute()
        count = len(supabase.table(t).select("id").execute().data or [])
        return f"OK ({count} rekordów)"
    check(table, _check)

# 3. Kluczowe kolumny w tasks (Sprint 6)
print("\n🔑 KOLUMNY SPRINT 6 W TASKS:")
sprint6_cols = ["kanban_status", "task_priority", "is_blocked", "blocker_reason", "blocker_type", "depends_on_task_ids"]
for col in sprint6_cols:
    def _check_col(c=col):
        res = supabase.table("tasks").select(c).limit(1).execute()
        return f"istnieje"
    check(f"tasks.{col}", _check_col)

# 4. Kolumny Sprint 6 w crew_requests
print("\n🔑 KOLUMNY SPRINT 6 W CREW_REQUESTS:")
cr_cols = ["investor_note", "expected_delivery_date", "confirmed_at", "delivered_at", "linked_task_id"]
for col in cr_cols:
    def _check_cr(c=col):
        res = supabase.table("crew_requests").select(c).limit(1).execute()
        return "istnieje"
    check(f"crew_requests.{col}", _check_cr)

# 5. Stan projektu
print("\n🏗️  STAN PROJEKTU:")
def check_project():
    res = supabase.table("project_metadata").select("*").order("created_at", desc=True).limit(1).execute()
    if res.data:
        p = res.data[0]
        return f"{p.get('project_name')} | Status: {p.get('status')} | Budżet: {p.get('total_budget')} zł"
    return "BRAK PROJEKTU — utwórz w menu 0. Charter"
check("Aktywny projekt", check_project)

# 6. Zadania
print("\n📋 ZADANIA:")
def check_tasks():
    res = supabase.table("tasks").select("kanban_status, is_blocked").execute()
    tasks = res.data or []
    if not tasks:
        return "BRAK ZADAŃ — Karol nie dodał jeszcze zadań"
    statuses = {}
    for t in tasks:
        s = t.get("kanban_status", "BACKLOG")
        statuses[s] = statuses.get(s, 0) + 1
    blocked = sum(1 for t in tasks if t.get("is_blocked"))
    return f"{len(tasks)} zadań | Blokery: {blocked} | Statusy: {statuses}"
check("Zadania na Kanbanie", check_tasks)

# 7. Oczekujące odbiory
print("\n🔔 ODBIORY:")
def check_inspections():
    res = supabase.table("task_inspection").select("inspection_status").execute()
    items = res.data or []
    if not items:
        return "BRAK — żadne zadanie nie zostało zgłoszone do odbioru"
    pending = sum(1 for i in items if i.get("inspection_status") == "PENDING")
    approved = sum(1 for i in items if i.get("inspection_status") == "APPROVED")
    return f"Oczekujące: {pending} | Zatwierdzone: {approved}"
check("task_inspection", check_inspections)

# 8. Zgłoszenia ekipy
print("\n🛠️  ZGŁOSZENIA EKIPY:")
def check_crew_requests():
    res = supabase.table("crew_requests").select("status").execute()
    items = res.data or []
    if not items:
        return "BRAK zgłoszeń"
    statuses = {}
    for r in items:
        s = r.get("status", "Nowe")
        statuses[s] = statuses.get(s, 0) + 1
    return f"{len(items)} zgłoszeń | {statuses}"
check("crew_requests", check_crew_requests)

print("\n" + "="*60)
print("  WERYFIKACJA ZAKOŃCZONA")
print("="*60 + "\n")
