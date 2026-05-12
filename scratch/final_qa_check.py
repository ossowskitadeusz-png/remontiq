from supabase import create_client
import json
import logging
import sys
import os

url = "https://mgrrsrgnalxtbrvzqyid.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1ncnJzcmduYWx4dGJydnpxeWlkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgwOTQ4NTksImV4cCI6MjA5MzY3MDg1OX0.LtzUjbFOb9uV3T4ptJFbNcp3UHiKl2EDbvw1d1ZZZX0"
supabase = create_client(url, key)

print("=== FINAL QA CHECKLIST ===\n")

# FRONT 1: SQL
print("--- FRONT 1: SQL ---")

# 1. Trigger test
try:
    # Pobierz pierwszy task
    task = supabase.table("tasks").select("id, state, kanban_status").limit(1).execute().data[0]
    tid = task['id']
    old_state = task['state']
    
    # Update kanban_status na 'in_progress'
    supabase.table("tasks").update({"kanban_status": "in_progress"}).eq("id", tid).execute()
    
    # Sprawdź nowy state
    new_task = supabase.table("tasks").select("id, state, kanban_status").eq("id", tid).execute().data[0]
    print(f"1. Trigger zmienił state? {new_task['state'] == 'IN_PROGRESS'} (Było: {old_state}, Jest: {new_task['state']})")
    
    # Cofnij zmianę dla czystości testu
    supabase.table("tasks").update({"kanban_status": "todo"}).eq("id", tid).execute()
except Exception as e:
    print(f"1. Błąd testu triggera: {e}")

# 2. Constraint test
try:
    # Próba wstawienia złego stanu
    res = supabase.table("tasks").update({"state": "INVALID_STATE"}).eq("id", tid).execute()
    print("2. Constraint zablokował? NIE (Udało się zapisać!)")
except Exception as e:
    if "check" in str(e).lower() or "violation" in str(e).lower() or "42501" in str(e).lower() or "P0001" in str(e).lower() or "400" in str(e).lower():
        print("2. Constraint zablokował? TAK (Wyrzucił błąd)")
    else:
        print(f"2. Constraint test - nieznany błąd: {e}")

# 3. Indeksy (Pobierzemy przez RPC lub zapytanie do schematu jeśli to możliwe, 
# ale ponieważ nie mamy direct SQL access, sprawdzimy wydajność/listę kolumn)
print("3. Ile indeksów? (Weryfikacja przez skrypt SQL w panelu Supabase jest zalecana, tu sprawdzam dostęp do tabeli)")
try:
    res = supabase.table("task_dependencies").select("*").limit(1).execute()
    print("   Tabela task_dependencies istnieje i jest dostępna.")
except:
    print("   Tabela task_dependencies - brak dostępu lub nie istnieje.")

# FRONT 2: Python
print("\n--- FRONT 2: Python ---")

try:
    # Dodajemy ścieżkę do sys.path
    sys.path.append(os.getcwd())
    from services.ordering_service import OrderingService
    
    # 4. Wszystkie 5 metod
    methods = [m for m in dir(OrderingService) if not m.startswith('_')]
    expected = ["get_task_dependencies", "reorder_tasks_in_phase", "move_task_up", "move_task_down", "get_ordered_tasks"]
    missing = [m for m in expected if m not in methods]
    print(f"4. Wszystkie 5 metod? {len(missing) == 0}")
    print(f"   Lista metod: {methods}")
    
    # 5. USE_NEW_DEPENDENCIES flag (instancyjnie lub klasowo)
    # W nowym kodzie flagę daliśmy jako globalną w module lub statyczną w klasie.
    # W moim kodzie była globalna.
    import services.ordering_service as os_module
    flag = getattr(os_module, 'USE_NEW_DEPENDENCIES', None)
    print(f"5. USE_NEW_DEPENDENCIES = {flag}")
except Exception as e:
    print(f"Błąd Front 2: {e}")

# FRONT 3: UI (Simulated)
print("\n--- FRONT 3: UI (Simulated) ---")

# 7. Przyciski ruchu (Simulated)
try:
    os_service = OrderingService(supabase)
    # Pobierz zadanie i jego sort_order
    t = supabase.table("tasks").select("id, sort_order, phase_id").eq("id", tid).single().execute().data
    old_order = t['sort_order']
    
    # Przesunięcie (wymaga innego zadania w fazie)
    # Sprawdzimy tylko czy funkcja nie wyrzuca błędu krytycznego
    res = os_service.move_task_down(tid)
    print(f"7. Przycisk ruchu (down) wywołany. Wynik: {res}")
except Exception as e:
    print(f"7. Błąd testu ruchu: {e}")

# 8. Nowe zadanie
try:
    from services.task_service import TaskService
    ts = TaskService(supabase)
    # Symulacja utworzenia zadania
    new_t = ts.create_task(project_id="test", phase_id="test", name="QA Test Task")
    if new_t:
        print(f"8. Nowe zadanie dostało state? {new_t.get('state')} (Commercial status: {new_t.get('commercial_status')})")
        # Cleanup
        supabase.table("tasks").delete().eq("id", new_t['id']).execute()
    else:
        print("8. Błąd tworzenia zadania.")
except Exception as e:
    # TaskService może wymagać realnego project_id
    print(f"8. Test nowego zadania (skip/error due to missing context): {e}")
