import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
import hashlib
import time
from typing import List, Dict
from supabase import create_client, Client
import plotly.graph_objects as go

# ==========================================
# 1. SUPABASE CONNECTION (Chmura)
# ==========================================
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

try:
    supabase = get_supabase()
except Exception as e:
    st.error("Błąd połączenia z Supabase. Sprawdź plik secrets.toml.")
    st.stop()

def read_table(table_name, select="*", filters=None, order_by=None):
    query = supabase.table(table_name).select(select)
    if filters:
        for k, v in filters.items():
            query = query.eq(k, v)
    # Filtr is_deleted stosujemy tylko tam, gdzie jest potrzebny (np. task_comments, expenses)
    # Dla ogólnej funkcji usuwamy wymuszenie, by nie sypało błędami w nowych tabelach.
    if order_by:
        query = query.order(order_by[0], desc=order_by[1])
    res = query.execute()
    return pd.DataFrame(res.data)

def get_project_metadata():
    res = supabase.table("project_metadata").select("*").order("created_at", desc=True).limit(1).execute()
    return res.data[0] if res.data else None

def create_project_metadata(**kwargs):
    if 'planned_start_date' in kwargs and isinstance(kwargs['planned_start_date'], date):
        kwargs['planned_start_date'] = kwargs['planned_start_date'].isoformat()
    if 'planned_end_date' in kwargs and isinstance(kwargs['planned_end_date'], date):
        kwargs['planned_end_date'] = kwargs['planned_end_date'].isoformat()
    supabase.table("project_metadata").insert(kwargs).execute()

def update_project_metadata(project_id, **kwargs):
    if 'actual_start_date' in kwargs and isinstance(kwargs['actual_start_date'], date):
        kwargs['actual_start_date'] = kwargs['actual_start_date'].isoformat()
    if 'actual_end_date' in kwargs and isinstance(kwargs['actual_end_date'], date):
        kwargs['actual_end_date'] = kwargs['actual_end_date'].isoformat()
    supabase.table("project_metadata").update(kwargs).eq("id", project_id).execute()

def get_project_days_info(project_meta):
    start = datetime.strptime(project_meta['planned_start_date'], "%Y-%m-%d").date()
    end = datetime.strptime(project_meta['planned_end_date'], "%Y-%m-%d").date()
    today = date.today()
    total_days = (end - start).days
    elapsed_days = (today - start).days
    remaining_days = (end - today).days
    progress_pct = max(0, min(100, int((elapsed_days / total_days) * 100) if total_days > 0 else 0))
    return {
        "total_days": total_days, "elapsed_days": elapsed_days, 
        "remaining_days": remaining_days, "progress_pct": progress_pct,
        "is_started": today >= start, "is_ended": today >= end
    }

def get_tasks_with_dependencies():
    try:
        response = supabase.table("tasks_with_dependencies").select("*").order("planned_start_date").execute()
        return response.data or []
    except Exception:
        return []

def complete_task(task_id):
    supabase.table("tasks").update({"status": "Done", "progress_percent": 100, "actual_end_date": datetime.now().isoformat()}).eq("id", task_id).execute()
    return {"status": "ok"}

def add_investor_note(task_id, note):
    supabase.table("tasks").update({"investor_note": note}).eq("id", task_id).execute()
    return {"status": "ok"}

def create_task_by_crew(task_name, task_description, planned_start_date, planned_end_date, assigned_to, depends_on_tasks=None):
    payload = {
        "name": task_name, "description": task_description,
        "planned_start_date": planned_start_date.isoformat(), "planned_end_date": planned_end_date.isoformat(),
        "assigned_to": ", ".join(assigned_to), "status": "Backlog", "progress_percent": 0,
        "created_by_crew": True, "depends_on_task_ids": depends_on_tasks or []
    }
    supabase.table("tasks").insert(payload).execute()
    return {"status": "ok"}

def can_task_start(task_id):
    try:
        task = supabase.table("tasks_with_dependencies").select("*").eq("id", task_id).execute()
        if not task.data: return {"can_start": False, "reason": "Zadanie nie znalezione"}
        
        task_data = task.data[0]
        if task_data.get("all_dependencies_met", False):
            return {"can_start": True, "message": "✅ Wszystkie zależności spełnione"}
        else:
            blocking = supabase.table("tasks").select("id, name, status").contains("depends_on_task_ids", [task_id]).execute()
            blocking_names = [t['name'] for t in (blocking.data or []) if t['status'] != 'Done']
            return {"can_start": False, "reason": f"Czeka na: {', '.join(blocking_names) if blocking_names else 'Inne zadania'}", "blocking_tasks": blocking_names}
    except Exception as e:
        return {"can_start": False, "reason": str(e)}

def get_kanban_board():
    try:
        response = supabase.table("tasks").select("*").order("task_priority").execute()
        tasks = response.data or []
        kanban = {'BACKLOG': [], 'READY': [], 'IN_PROGRESS': [], 'AWAITING_INSPECTION': [], 'COMPLETED': []}
        for task in tasks:
            status = task.get('kanban_status') or 'BACKLOG'
            if status in kanban: kanban[status].append(task)
        return kanban
    except Exception:
        return {'BACKLOG': [], 'READY': [], 'IN_PROGRESS': [], 'AWAITING_INSPECTION': [], 'COMPLETED': []}

def update_kanban_status(task_id, new_status):
    supabase.table("tasks").update({"kanban_status": new_status}).eq("id", task_id).execute()
    return {"status": "ok"}

def start_task(task_id):
    task_name = (supabase.table("tasks").select("name").eq("id", task_id).execute().data or [{}])[0].get("name", "?")
    supabase.table("tasks").update({"kanban_status": "IN_PROGRESS", "actual_start_date": datetime.now().isoformat()}).eq("id", task_id).execute()
    log_activity("task_started", f"Karol rozpoczął: {task_name}", "Karol", "investor", task_id)
    return {"status": "ok"}

def submit_for_inspection(task_id, notes="", photos=None):
    task_name = (supabase.table("tasks").select("name").eq("id", task_id).execute().data or [{}])[0].get("name", "?")
    inspection_data = {"task_id": task_id, "submitted_by": "Karol", "submitted_at": datetime.now().isoformat(), "submission_notes": notes, "submission_photos": photos or [], "inspection_status": "PENDING"}
    response = supabase.table("task_inspection").insert(inspection_data).execute()
    supabase.table("tasks").update({"kanban_status": "AWAITING_INSPECTION"}).eq("id", task_id).execute()
    log_activity("inspection_submitted", f"Karol zgłosił do odbioru: {task_name}", "Karol", "investor", task_id)
    return {"status": "ok", "inspection_id": response.data[0]['id'] if response.data else None}

def report_blocker(task_id, description, blocker_type="OTHER"):
    """Zapisuje powód, status przed blokadą i blokuje zadanie."""
    try:
        # Pobierz dane zadania przed blokadą
        task_data = supabase.table("tasks").select("kanban_status, name").eq("id", task_id).execute().data[0]
        old_status = task_data['kanban_status']
        
        blocker_data = {
            "task_id": task_id, "blocker_type": blocker_type, "description": description,
            "reported_by": "Karol", "reported_at": datetime.now().isoformat(), "is_resolved": False
        }
        supabase.table("task_blockers").insert(blocker_data).execute()
        
        # Zapamiętaj status i zablokuj
        supabase.table("tasks").update({
            "is_blocked": True,
            "blocker_reason": description,
            "status_before_block": old_status
        }).eq("id", task_id).execute()
        
        log_activity("Karol", "blocker_reported", task_id, f"Blokada: {description}")
        return True
    except Exception: return False

def resolve_blocker(blocker_id, resolution_note=""):
    """Odblokowuje zadanie i PRZYWRACA poprzedni status."""
    try:
        resp = supabase.table("task_blockers").select("task_id").eq("id", blocker_id).execute()
        if not resp.data: return False
        task_id = resp.data[0]['task_id']
        
        # Pobierz status do przywrócenia
        task_data = supabase.table("tasks").select("status_before_block").eq("id", task_id).execute().data[0]
        restore_status = task_data.get('status_before_block') or "IN_PROGRESS"
        
        supabase.table("task_blockers").update({
            "is_resolved": True, "resolved_at": datetime.now().isoformat(), "resolution_note": resolution_note
        }).eq("id", blocker_id).execute()
        
        # Sprawdź czy są inne aktywne blokery dla tego zadania
        remaining = supabase.table("task_blockers").select("id").eq("task_id", task_id).eq("is_resolved", False).execute()
        if not remaining.data:
            supabase.table("tasks").update({
                "is_blocked": False, "blocker_reason": None, 
                "kanban_status": restore_status, "status_before_block": None
            }).eq("id", task_id).execute()
            
        log_activity("Inwestor", "blocker_resolved", task_id, "Zadanie odblokowane i przywrócone")
        return True
    except Exception: return False

def get_blockers_for_task(task_id):
    """Pobiera aktywne blokery dla zadania."""
    try:
        return supabase.table("task_blockers").select("*").eq("task_id", task_id).eq("is_resolved", False).execute().data or []
    except: return []

def get_pending_inspections():
    try:
        return supabase.table("task_inspection").select("*").eq("inspection_status", "PENDING").order("submitted_at").execute().data or []
    except: return []

def approve_inspection(inspection_id, notes=""):
    response = supabase.table("task_inspection").select("task_id").eq("id", inspection_id).execute()
    if not response.data: return {"status": "error"}
    task_id = response.data[0]['task_id']
    task_name = (supabase.table("tasks").select("name").eq("id", task_id).execute().data or [{}])[0].get("name", "?")
    supabase.table("task_inspection").update({"inspection_status": "APPROVED", "inspected_by": "Inwestor", "inspected_at": datetime.now().isoformat(), "inspection_notes": notes}).eq("id", inspection_id).execute()
    supabase.table("tasks").update({"kanban_status": "COMPLETED", "status": "Done", "actual_end_date": datetime.now().isoformat(), "progress_percent": 100}).eq("id", task_id).execute()
    log_activity("task_completed", f"Inwestor zatwierdził: {task_name}", "Inwestor", "crew", task_id)
    return {"status": "ok"}

def request_rework(inspection_id, rework_description):
    response = supabase.table("task_inspection").select("task_id").eq("id", inspection_id).execute()
    if not response.data: return {"status": "error"}
    task_id = response.data[0]['task_id']
    task_name = (supabase.table("tasks").select("name").eq("id", task_id).execute().data or [{}])[0].get("name", "?")
    supabase.table("task_inspection").update({"inspection_status": "REQUIRES_REWORK", "inspected_by": "Inwestor", "inspected_at": datetime.now().isoformat(), "rework_description": rework_description}).eq("id", inspection_id).execute()
    supabase.table("tasks").update({"kanban_status": "IN_PROGRESS"}).eq("id", task_id).execute()
    log_activity("inspection_rework", f"Wymaga poprawek: {task_name} — {rework_description[:60]}", "Inwestor", "crew", task_id)
    return {"status": "ok"}

def get_crew_kpis():
    try:
        response = supabase.table("tasks").select("*").execute()
        tasks = response.data or []
        total = len(tasks)
        in_progress = len([t for t in tasks if t.get('kanban_status') == 'IN_PROGRESS' and not t.get('is_blocked')])
        blocked = len([t for t in tasks if t.get('is_blocked')])
        completed = len([t for t in tasks if t.get('kanban_status') == 'COMPLETED'])
        awaiting = len([t for t in tasks if t.get('kanban_status') == 'AWAITING_INSPECTION'])
        
        project_meta = get_project_metadata()
        days_to_end = 0
        if project_meta:
            end_date = datetime.strptime(project_meta['planned_end_date'], "%Y-%m-%d").date()
            days_to_end = (end_date - date.today()).days
        
        return {
            "total_tasks": total, "in_progress": in_progress, "blocked": blocked, 
            "completed": completed, "awaiting_inspection": awaiting, 
            "days_to_end": max(0, days_to_end), "completion_rate": int((completed / total * 100) if total > 0 else 0)
        }
    except:
        return {"total_tasks": 0, "in_progress": 0, "blocked": 0, "completed": 0, "awaiting_inspection": 0, "days_to_end": 0, "completion_rate": 0}

def get_crew_requests_grouped():
    """Zwróć zgłoszenia ekipy pogrupowane po statusie."""
    try:
        response = supabase.table("crew_requests").select("*").order("created_at", desc=True).execute()
        requests = response.data or []
        grouped = {"Nowe": [], "Potwierdzone": [], "Dostarczone": [], "Anulowane": []}
        for req in requests:
            s = req.get("status", "Nowe")
            if s not in grouped:
                s = "Nowe"
            grouped[s].append(req)
        return grouped
    except Exception:
        return {"Nowe": [], "Potwierdzone": [], "Dostarczone": [], "Anulowane": []}

def confirm_crew_request(request_id, investor_note="", expected_delivery_date=None):
    """Inwestor potwierdza: 'Wiem, zajmuję się tym'."""
    payload = {
        "status": "Potwierdzone",
        "investor_note": investor_note,
        "confirmed_at": datetime.now().isoformat(),
    }
    if expected_delivery_date:
        payload["expected_delivery_date"] = expected_delivery_date.isoformat() if hasattr(expected_delivery_date, 'isoformat') else str(expected_delivery_date)
    supabase.table("crew_requests").update(payload).eq("id", request_id).execute()
    return {"status": "ok"}

def mark_crew_request_delivered(request_id):
    """Inwestor potwierdza dostawę: 'Materiał jest na budowie'."""
    supabase.table("crew_requests").update({
        "status": "Dostarczone",
        "delivered_at": datetime.now().isoformat()
    }).eq("id", request_id).execute()
    return {"status": "ok"}

def cancel_crew_request(request_id):
    """Inwestor anuluje zgłoszenie — odblokuj powiązane zadanie."""
    req_data = supabase.table("crew_requests").select("linked_task_id").eq("id", request_id).execute()
    supabase.table("crew_requests").update({"status": "Anulowane"}).eq("id", request_id).execute()
    if req_data.data and req_data.data[0].get("linked_task_id"):
        task_id = req_data.data[0]["linked_task_id"]
        remaining = supabase.table("crew_requests").select("id").eq("linked_task_id", task_id).in_("status", ["Nowe", "Potwierdzone"]).execute()
        if not remaining.data:
            supabase.table("tasks").update({"is_blocked": False, "blocker_reason": None}).eq("id", task_id).execute()
    return {"status": "ok"}

def submit_crew_request_with_blocker(title, needed_by, is_blocker, linked_task_id=None):
    """Karol zgłasza potrzebę — jeśli pilne, auto-blokuje zadanie i zapisuje jego status."""
    payload = {"title": title, "needed_by": str(needed_by), "is_blocker": is_blocker, "status": "Nowe", "linked_task_id": linked_task_id}
    supabase.table("crew_requests").insert(payload).execute()
    if linked_task_id and is_blocker:
        # Pobierz obecny status do pamięci
        t_data = supabase.table("tasks").select("kanban_status").eq("id", linked_task_id).execute().data[0]
        old_status = t_data['kanban_status']
        
        supabase.table("tasks").update({
            "is_blocked": True, 
            "blocker_reason": f"Brak: {title}", 
            "status_before_block": old_status
        }).eq("id", linked_task_id).execute()
        
        supabase.table("task_blockers").insert({
            "task_id": linked_task_id, "blocker_type": "MISSING_MATERIAL", 
            "description": f"Zgłoszono brak: {title}", "reported_by": "Karol", "is_resolved": False
        }).execute()
    return {"status": "ok"}


def log_activity(event_type, description, created_by, visible_to="both", task_id=None):
    """Zapisz zdarzenie do activity_log — pojawi się w banerze alertów."""
    try:
        payload = {
            "event_type": event_type,
            "description": description,
            "created_by": created_by,
            "visible_to": visible_to,
        }
        if task_id:
            payload["task_id"] = str(task_id)
        supabase.table("activity_log").insert(payload).execute()
    except Exception:
        pass

def add_comment(task_id, author_name, author_role, content):
    """Dodaj komentarz i zaloguj aktywność."""
    if not content.strip(): return
    try:
        payload = {
            "task_id": str(task_id),
            "author_name": author_name,
            "author_role": author_role,
            "content": content
        }
        supabase.table("task_comments").insert(payload).execute()
        # Powiadom drugą stronę
        visible_to = "investor" if author_role == "crew" else "crew"
        task_name = (supabase.table("tasks").select("name").eq("id", task_id).execute().data or [{}])[0].get("name", "?")
        log_activity("comment_added", f"💬 {author_name} do {task_name}: {content[:50]}...", author_name, visible_to, task_id)
    except Exception:
        pass

def get_comments(task_id):
    """Pobierz historię komentarzy dla zadania."""
    try:
        return supabase.table("task_comments").select("*").eq("task_id", str(task_id)).order("created_at", desc=False).execute().data or []
    except Exception:
        return []

# ============================================
# SPRINT 9: SORTOWANIE ZADAŃ (Backend)
# ============================================

def get_tasks_ordered():
    """Pobiera wszystkie zadania posortowane po position_in_queue"""
    try:
        response = supabase.table("tasks").select("*").order("position_in_queue").execute()
        tasks = response.data or []
        for task in tasks:
            if task.get('room_id'):
                room_r = supabase.table("rooms").select("name").eq("id", task['room_id']).execute()
                task['room_name'] = room_r.data[0]['name'] if room_r.data else "—"
            else:
                task['room_name'] = "—"
        return tasks
    except Exception:
        return []

def move_task_up(task_id):
    """Przesuwa zadanie wyżej (zmniejsza position_in_queue)"""
    try:
        task_r = supabase.table("tasks").select("position_in_queue").eq("id", task_id).execute()
        if not task_r.data: return False
        curr = task_r.data[0]['position_in_queue']
        prev_r = supabase.table("tasks").select("id").eq("position_in_queue", curr - 1).execute()
        if not prev_r.data: return False
        prev_id = prev_r.data[0]['id']
        supabase.table("tasks").update({"position_in_queue": curr - 1}).eq("id", task_id).execute()
        supabase.table("tasks").update({"position_in_queue": curr}).eq("id", prev_id).execute()
        return True
    except Exception: return False

def move_task_down(task_id):
    """Przesuwa zadanie niżej (zwiększa position_in_queue)"""
    try:
        task_r = supabase.table("tasks").select("position_in_queue").eq("id", task_id).execute()
        if not task_r.data: return False
        curr = task_r.data[0]['position_in_queue']
        next_r = supabase.table("tasks").select("id").eq("position_in_queue", curr + 1).execute()
        if not next_r.data: return False
        nxt_id = next_r.data[0]['id']
        supabase.table("tasks").update({"position_in_queue": curr + 1}).eq("id", task_id).execute()
        supabase.table("tasks").update({"position_in_queue": curr}).eq("id", nxt_id).execute()
        return True
    except Exception: return False

def get_filtered_comments(task_name=None, author_role=None, order="newest_first"):
    """Pobiera komentarze z filtracją i kontekstem zadania."""
    try:
        comments = supabase.table("task_comments").select("*").execute().data or []
        for c in comments:
            t_r = supabase.table("tasks").select("name, room_id").eq("id", c['task_id']).execute()
            if t_r.data:
                c['task_name'] = t_r.data[0]['name']
                if t_r.data[0].get('room_id'):
                    r_r = supabase.table("rooms").select("name").eq("id", t_r.data[0]['room_id']).execute()
                    c['room_name'] = r_r.data[0]['name'] if r_r.data else "—"
                else: c['room_name'] = "—"
            else:
                c['task_name'], c['room_name'] = "Nieznane", "—"
        if task_name: comments = [c for c in comments if c['task_name'] == task_name]
        if author_role: comments = [c for c in comments if c['author_role'] == author_role]
        rev = True if order == "newest_first" else False
        return sorted(comments, key=lambda x: x['created_at'], reverse=rev)
    except Exception: return []

def render_comment_section(task_id, role):
    """Wyświetla czat w stylu WhatsApp."""
    comments = get_comments(task_id)
    user_name = "Karol" if role == "crew" else "Inwestor"
    
    with st.expander(f"💬 Chat ({len(comments)})"):
        render_whatsapp_chat(comments, user_name, task_id, context="kanban")
        render_chat_input(task_id, user_name, context="kanban")

def calculate_budget_forecast():
    """Oblicz prognozę wyczerpania budżetu."""
    try:
        meta = get_project_metadata()
        if not meta or not meta.get('planned_start_date'): return None
        
        total_budget = meta.get('total_budget', 0)
        expenses_df = read_table("expenses")
        spent = expenses_df['amount'].sum() if not expenses_df.empty else 0
        
        start_date = datetime.strptime(meta['planned_start_date'], "%Y-%m-%d").date()
        days_passed = (date.today() - start_date).days
        
        daily_burn = spent / max(1, days_passed)
        remaining = total_budget - spent
        days_left = int(remaining / daily_burn) if daily_burn > 0 else 999
        
        forecast_date = date.today() + timedelta(days=days_left)
        
        status = "🟢 OK"
        if days_left < 14: status = "🔴 KRITYCZNIE"
        elif days_left < 30: status = "🟡 OSTRZEŻENIE"
        
        return {
            "total": total_budget, "spent": spent, "remaining": remaining,
            "daily_burn": int(daily_burn), "days_until_depleted": days_left,
            "forecast_date": forecast_date, "status": status
        }
    except Exception:
        return None

def calculate_health_score():
    """Oblicza Health Score projektu (średnia ważona 35/25/25/15)."""
    try:
        # 1. POSTĘP (35%)
        tasks = supabase.table("tasks").select("kanban_status, planned_end_date").execute().data or []
        if not tasks: return {"score": 0, "status": "⚪ BRAK DANYCH", "metrics": {}, "details": {}}
        
        comp_count = len([t for t in tasks if t.get('kanban_status') == 'COMPLETED'])
        prog_score = (comp_count / len(tasks)) * 100
        
        # 2. HARMONOGRAM (25%)
        today = date.today()
        delays = []
        for t in tasks:
            if t.get('planned_end_date'):
                p_end = datetime.strptime(t['planned_end_date'], "%Y-%m-%d").date()
                if t['kanban_status'] != 'COMPLETED' and p_end < today:
                    delays.append((today - p_end).days)
        avg_delay = sum(delays)/len(delays) if delays else 0
        sched_score = 100 if avg_delay == 0 else (75 if avg_delay <= 3 else (50 if avg_delay <= 7 else 25))
        
        # 3. BUDŻET (25%)
        meta = get_project_metadata()
        total_b = meta.get('total_budget', 0) if meta else 0
        exp_df = read_table("expenses")
        spent = exp_df['amount'].sum() if not exp_df.empty else 0
        
        if total_b > 0:
            b_pct = (spent / total_b) * 100
            budg_score = 100 if b_pct <= 80 else (75 if b_pct <= 95 else (50 if b_pct <= 110 else 0))
        else: b_pct, budg_score = 0, 100
        
        # 4. BLOKERY (15%)
        block_count = len([t for t in tasks if t.get('is_blocked')])
        block_score = 100 if block_count == 0 else (75 if block_count <= 2 else (50 if block_count <= 5 else 25))
        
        final = round((prog_score*0.35) + (sched_score*0.25) + (budg_score*0.25) + (block_score*0.15))
        status = "🟢 ZDROWY" if final >= 80 else ("🟡 OSTRZEŻENIE" if final >= 60 else "🔴 KRYTYCZNIE")
        
        return {
            "score": final, "status": status,
            "metrics": {"progress": round(prog_score), "schedule": sched_score, "budget": budg_score, "blockers": block_score},
            "details": {"completed": comp_count, "total": len(tasks), "delay": round(avg_delay, 1), "spent": spent, "budget": total_b, "pct": round(b_pct, 1), "blockers": block_count}
        }
    except Exception: return {"score": 0, "status": "❌ BŁĄD", "metrics": {}, "details": {}}

def get_burn_down_data():
    """Pobiera dane do wykresu burn-down."""
    try:
        meta = get_project_metadata()
        if not meta or not meta.get('planned_start_date'): return None
        
        total_b = meta.get('total_budget', 0)
        start_d = datetime.strptime(meta['planned_start_date'], "%Y-%m-%d").date()
        
        # Planowany koniec z Charteru
        charter = supabase.table("project_charter").select("planned_end_date").execute().data
        end_d = datetime.strptime(charter[0]['planned_end_date'], "%Y-%m-%d").date() if charter else start_d + timedelta(days=30)
        
        total_days = (end_d - start_d).days
        exp_df = read_table("expenses")
        
        planned_line, actual_line, dates = [], [], []
        curr_spent = 0
        
        for i in range(total_days + 1):
            curr_d = start_d + timedelta(days=i)
            dates.append(curr_d.strftime("%d.%m"))
            
            # PLAN (liniowy spadek)
            planned_rem = max(0, total_b - (total_b * (i / total_days))) if total_days > 0 else 0
            planned_line.append(planned_rem)
            
            # REAL (skumulowane wydatki)
            if not exp_df.empty:
                day_spent = exp_df[exp_df['date'] == str(curr_d)]['amount'].sum()
                curr_spent += day_spent
            
            if curr_d <= date.today():
                actual_line.append(max(0, total_b - curr_spent))
        
        return {"planned": planned_line, "actual": actual_line, "dates": dates, "total": total_b, "spent": curr_spent}
    except Exception: return None

def get_activity_banner(role):
    """Pobierz zdarzenia od ostatniej wizyty dla danej roli."""
    try:
        last_visit = st.session_state.get("last_visit")
        query = supabase.table("activity_log").select("*").order("created_at", desc=True).limit(10)
        if role == "investor":
            query = query.in_("visible_to", ["investor", "both"])
        else:
            query = query.in_("visible_to", ["crew", "both"])
        events = query.execute().data or []
        if last_visit:
            events = [e for e in events if e["created_at"] > last_visit]
        return events
    except Exception:
        return []

EVENT_ICONS = {
    "task_started":           ("🟧", "crew"),
    "inspection_submitted":   ("🔔", "investor"),
    "inspection_approved":    ("✅", "crew"),
    "inspection_rework":      ("❌", "crew"),
    "blocker_reported":       ("🔴", "investor"),
    "blocker_resolved":       ("🟢", "crew"),
    "request_confirmed":      ("🟡", "crew"),
    "request_delivered":      ("📦", "crew"),
    "request_cancelled":      ("⬜", "crew"),
    "task_completed":         ("✅", "investor"),
    "comment_added":          ("💬", "both"),
}

# ============================================
# SPRINT 11: PHOTO UPLOAD SYSTEM
# ============================================

def upload_task_photo(task_id, file):
    """Uploaduje zdjęcie do Supabase Storage (task_photos)."""
    try:
        # Walidacja rozmiaru (max 5 MB)
        if len(file.getvalue()) > 5 * 1024 * 1024:
            return {"success": False, "error": "Plik zbyt duży. Max 5 MB."}
        
        # Ścieżka: task_photos/task_{id}/{timestamp}_{name}
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        f_path = f"task_{task_id}/{ts}_{file.name}"
        
        # Upload
        supabase.storage.from_("task_photos").upload(
            file=file.getvalue(), path=f_path, file_options={"content-type": file.type}
        )
        
        # Public URL
        url = supabase.storage.from_("task_photos").get_public_url(f_path)
        return {"success": True, "url": url["publicUrl"]}
    except Exception as e:
        return {"success": False, "error": str(e)}

def add_comment_with_photo(task_id, author_name, author_role, content, image_url=None):
    """Dodaje komentarz z opcjonalnym linkiem do zdjęcia."""
    try:
        supabase.table("task_comments").insert({
            "task_id": task_id, "author_name": author_name, "author_role": author_role,
            "content": content, "image_url": image_url
        }).execute()
        
        log_activity(author_name, "comment_added", task_id, 
                     f"Dodano komentarz" + (" ze zdjęciem" if image_url else ""))
        return True
    except Exception: return False

def get_comments_with_photos(task_id):
    """Pobiera wszystkie komentarze dla zadania."""
    try:
        return supabase.table("task_comments").select("*").eq("task_id", str(task_id)).order("created_at", desc=False).execute().data or []
    except Exception: return []

# ============================================
# SPRINT 14: CHAT UPGRADE (Backend)
# ============================================

LAST_SYNC_TIME = {} 

def get_all_comments_grouped():
    """Pobiera wszystkie aktywne komentarze pogrupowane po zadaniach."""
    try:
        t_r = supabase.table("tasks").select("id, name").execute()
        tasks = {t['id']: t['name'] for t in (t_r.data or [])}
        c_r = supabase.table("task_comments").select("*").eq("is_deleted", False).order("created_at").execute()
        comments = c_r.data or []
        grouped = {}
        for c in comments:
            tid = c.get('task_id')
            if tid not in grouped:
                grouped[tid] = {"task_id": tid, "task_name": tasks.get(tid, f"Zadanie {tid}"), "comments": []}
            grouped[tid]['comments'].append(c)
        return list(grouped.values())
    except Exception: return []

def generate_unique_key(task_id, context, element_type):
    """Generuje unikalny klucz hash dla elementu UI."""
    combined = f"{task_id}_{context}_{element_type}_{datetime.now().strftime('%M%S')}"
    return hashlib.md5(combined.encode()).hexdigest()[:12]

def should_refresh_comments(task_id, interval=5):
    """Sprawdza czy czas na auto-odświeżanie."""
    if task_id not in LAST_SYNC_TIME:
        LAST_SYNC_TIME[task_id] = datetime.now()
        return True
    if (datetime.now() - LAST_SYNC_TIME[task_id]).total_seconds() >= interval:
        LAST_SYNC_TIME[task_id] = datetime.now()
        return True
    return False

def edit_comment(comment_id, new_content, edited_by):
    """Edytuje komentarz z zachowaniem wersji."""
    try:
        old = supabase.table("task_comments").select("*").eq("id", comment_id).execute().data[0]
        orig = old.get('original_content') or old.get('content')
        count = (old.get('edit_count') or 0) + 1
        supabase.table("task_comments").update({
            "content": new_content, "original_content": orig,
            "edited_at": datetime.now().isoformat(), "edit_count": count,
            "last_sync": datetime.now().isoformat()
        }).eq("id", comment_id).execute()
        return True
    except Exception: return False

def delete_comment(comment_id):
    """Soft-delete komentarza."""
    try:
        supabase.table("task_comments").update({
            "is_deleted": True, "edited_at": datetime.now().isoformat(),
            "last_sync": datetime.now().isoformat()
        }).eq("id", comment_id).execute()
        return True
    except Exception: return False

@st.fragment(run_every=7)
def render_whatsapp_chat(comments, current_user, task_id, context="chat"):
    """WhatsApp-style chat z edycją, usuwaniem i auto-odświeżaniem fragmentu."""
    # Odświeżamy komentarze bezpośrednio wewnątrz fragmentu
    all_grouped = get_all_comments_grouped()
    task_data = next((g for g in all_grouped if g['task_id'] == task_id), None)
    current_comments = task_data['comments'] if task_data else comments
    
    st.caption("⏱️ Czat odświeża się automatycznie co 7s")
    for idx, c in enumerate(current_comments):
        if c.get('is_deleted'): continue
        author = c.get('author_name', 'Nieznany')
        is_me = (author == current_user)
        bg = "#e0e0e0" if is_me else "#0084ff"
        txt = "#000" if is_me else "#fff"
        align = "flex-end" if is_me else "flex-start"
        margin = "30%" if is_me else "0"
        ts = c.get('created_at', '')[11:16]
        edit_tag = f" (edytowane {c['edit_count']}x)" if c.get('edit_count', 0) > 0 else ""
        
        st.markdown(f"""
        <div style="display: flex; justify-content: {align}; margin-bottom: 8px; margin-left: {margin};">
            <div style="background-color: {bg}; color: {txt}; padding: 12px 16px; border-radius: 18px; max-width: 85%; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="font-size: 11px; font-weight: bold; opacity: 0.8;">{author}</div>
                {c.get('content', '')}
                <div style="font-size: 10px; opacity: 0.6; text-align: right;">{ts}{edit_tag}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if c.get('image_url'):
            st.image(c['image_url'], width="stretch")
            
        if is_me:
            c_edit, c_del, _ = st.columns([1, 1, 8])
            if c_edit.button("✏️", key=generate_unique_key(task_id, context, f"edit_{idx}")):
                st.session_state[f"edit_mode_{c['id']}"] = True
            if c_del.button("🗑️", key=generate_unique_key(task_id, context, f"del_{idx}")):
                if delete_comment(c['id']): st.rerun()
                
            if st.session_state.get(f"edit_mode_{c['id']}"):
                with st.expander("Edytuj wiadomość", expanded=True):
                    new_val = st.text_area("Treść", value=c['content'], key=generate_unique_key(task_id, context, f"area_{idx}"))
                    if st.button("Zapisz", key=generate_unique_key(task_id, context, f"save_{idx}")):
                        if edit_comment(c['id'], new_val, current_user):
                            st.session_state[f"edit_mode_{c['id']}"] = False
                            st.rerun()

def render_chat_input(task_id, current_user, context="input"):
    """Input box z unikalnymi kluczami hash."""
    with st.container():
        c1, c2, c3 = st.columns([3, 1, 0.8])
        msg = c1.text_input("Wiadomość", placeholder="Napisz...", label_visibility="collapsed", key=generate_unique_key(task_id, context, "msg"))
        up = c2.file_uploader("📸", type=["jpg", "png"], label_visibility="collapsed", key=generate_unique_key(task_id, context, "up"))
        if c3.button("➤", key=generate_unique_key(task_id, context, "btn"), type="primary", width="stretch"):
            if msg.strip():
                url = None
                if up:
                    res = upload_task_photo(task_id, up)
                    if res['success']: url = res['url']
                role = "investor" if current_user != "Karol" else "crew"
                add_comment_with_photo(task_id, current_user, role, msg, url)
                st.rerun()

# ==========================================
# 2. SCORING ENGINE (V3.0 - Sprint 4)
# ==========================================
def calculate_smart_recommendations():
    today = date.today()
    recs = []
    
    # --- 1. RYZYKA (ISSUES) ---
    iss = read_table("issues")
    for _, row in iss.iterrows():
        if row['status'] in ('Rozwiązane', 'Zignorowane', 'Przekształcone w zadanie'): continue
        score = 0
        reasons = []
        if row['severity'] == 'Krytyczne': score += 250; reasons.append("KRYTYCZNY PROBLEM!")
        elif row['severity'] == 'Średnie': score += 90; reasons.append("Średni problem")
        elif row['severity'] == 'Niskie': score += 20; reasons.append("Niski priorytet")
        if score > 0: recs.append({"Typ": "🚨 Ryzyko", "Zadanie": row['title'], "Wynik": score, "Powód": " | ".join(reasons)})

    # --- 2. DECYZJE ---
    decs = read_table("decisions")
    for _, row in decs.iterrows():
        if row['status'] != 'Do podjęcia': continue
        score, reasons = 0, []
        if pd.isna(row['due_date']) or not row['due_date']:
            recs.append({"Typ": "🤔 Decyzja", "Zadanie": f"Brak daty dla decyzji: {row['title']}", "Wynik": 10, "Powód": "Uzupełnij termin podjęcia decyzji"})
            continue
            
        due = pd.to_datetime(row['due_date']).date()
        days_left = (due - today).days
        
        if row['impact'] == 'Krytyczny':
            if days_left < 0: score += 180; reasons.append("SPÓŹNIONA KRYTYCZNA DECYZJA!")
            elif days_left <= 3: score += 120; reasons.append(f"Zostało {days_left} dni (Krytyczna)")
        elif row['impact'] == 'Średni' and days_left <= 3:
            score += 90; reasons.append(f"Zostało {days_left} dni (Średnia)")
            
        if score > 0: recs.append({"Typ": "🤔 Decyzja", "Zadanie": row['title'], "Wynik": score, "Powód": " | ".join(reasons)})

    # --- 3. EKIPA ---
    reqs = read_table("crew_requests")
    for _, row in reqs.iterrows():
        if row['status'] in ('Załatwione', 'Anulowane', 'Przekształcone w zadanie'): continue
        score, reasons = 0, []
        needed_date = pd.to_datetime(row['needed_by']).date() if pd.notna(row['needed_by']) and row['needed_by'] else today
        days_left = (needed_date - today).days
        
        if row['is_blocker']: score += 200; reasons.append("BLOKUJE PRACĘ!")
        if days_left <= 1: score += 150; reasons.append("Na dzisiaj/jutro!")
        elif days_left <= 4: score += 100; reasons.append(f"Potrzebne za {days_left} dni")
        if score > 0: recs.append({"Typ": "🛠️ Ekipa", "Zadanie": row['title'], "Wynik": score, "Powód": " | ".join(reasons)})

    # --- 4. MATERIAŁY ---
    mats = read_table("materials")
    for _, row in mats.iterrows():
        if row['status'] in ('Dostarczone', 'Na miejscu', 'Anulowane', 'Zamontowane'): continue
        # Ignore fully delivered
        if pd.notna(row['quantity_received']) and pd.notna(row['quantity_planned']):
            if row['quantity_received'] >= row['quantity_planned'] and row['quantity_planned'] > 0:
                continue

        score, reasons = 0, []
        if pd.isna(row['needed_by']) or not row['needed_by']:
            recs.append({"Typ": "📦 Materiał", "Zadanie": f"Wybierz datę: {row['name']}", "Wynik": 10, "Powód": "Brak daty dostawy"})
            continue

        needed = pd.to_datetime(row['needed_by']).date()
        lead_time = int(row['lead_time_days'] or 0)
        days_to_order = ((needed - timedelta(days=lead_time)) - today).days
        
        if days_to_order <= 0: score += 150; reasons.append("Spóźnione zamówienie!")
        elif days_to_order <= 3: score += 80; reasons.append(f"Zamów za max {days_to_order} dni")
        if score > 0: recs.append({"Typ": "📦 Materiał", "Zadanie": f"Zamów: {row['name']}", "Wynik": score, "Powód": " | ".join(reasons)})
            
    if not recs: return pd.DataFrame()
    return pd.DataFrame(recs).sort_values("Wynik", ascending=False).head(5)


# ==========================================
# 3. INTERFEJS UŻYTKOWNIKA I LOGOWANIE
# ==========================================
st.set_page_config(page_title="RemontIQ Cloud", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# DARK MODE CSS — Sprint 7
# ==========================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* === DARK BACKGROUND === */
.stApp {
    background: linear-gradient(135deg, #0f1117 0%, #1a1f2e 100%);
    color: #e2e8f0;
}

/* === SIDEBAR === */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1f2e 0%, #141824 100%);
    border-right: 1px solid #2d3748;
}
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }

/* === CARDS / CONTAINERS === */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] > div[data-testid="element-container"] > div[data-baseweb] {
    background: #1e2533;
    border: 1px solid #2d3748;
    border-radius: 12px;
}

/* === METRICS === */
[data-testid="metric-container"] {
    background: #1e2533;
    border: 1px solid #2d3748;
    border-radius: 10px;
    padding: 12px 16px;
}
[data-testid="stMetricValue"] { color: #63b3ed !important; font-weight: 700; }
[data-testid="stMetricDelta"] { font-size: 12px !important; }

/* === BUTTONS === */
.stButton > button {
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.2s ease;
    border: 1px solid #4a5568;
    background: #2d3748;
    color: #e2e8f0;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(99, 179, 237, 0.3);
    border-color: #63b3ed;
    background: #374151;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #2b6cb0, #3182ce);
    border-color: #3182ce;
    color: white;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #3182ce, #4299e1);
    box-shadow: 0 4px 16px rgba(49, 130, 206, 0.5);
}

/* === INPUTS === */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > div {
    background: #1a1f2e !important;
    color: #e2e8f0 !important;
    border: 1px solid #4a5568 !important;
    border-radius: 8px !important;
}

/* === ALARM PULSE ANIMATION === */
@keyframes pulse-red {
    0%, 100% { box-shadow: 0 0 0 0 rgba(229, 62, 62, 0.4); }
    50% { box-shadow: 0 0 0 8px rgba(229, 62, 62, 0); }
}
.alarm-pulse {
    animation: pulse-red 2s infinite;
    border-radius: 10px;
}

/* === KANBAN COLUMN HEADERS === */
h3 { color: #90cdf4 !important; border-bottom: 2px solid #2d3748; padding-bottom: 8px; }

/* === DIVIDER === */
hr { border-color: #2d3748 !important; margin: 20px 0 !important; }

/* === TABS === */
[data-baseweb="tab-list"] { background: #1e2533 !important; border-radius: 10px; }
[data-baseweb="tab"] { color: #a0aec0 !important; }
[aria-selected="true"] { color: #63b3ed !important; background: #2d3748 !important; border-radius: 8px; }

/* === EXPANDER === */
[data-testid="stExpander"] {
    background: #1e2533;
    border: 1px solid #2d3748;
    border-radius: 10px;
}

/* === SUCCESS / WARNING / ERROR === */
[data-testid="stAlert"] { border-radius: 8px !important; }

/* === ACTIVITY BANNER === */
.activity-banner {
    background: linear-gradient(135deg, #1a2744, #1e3a5f);
    border: 1px solid #2b6cb0;
    border-left: 4px solid #63b3ed;
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 16px;
}
.activity-item {
    padding: 4px 0;
    font-size: 13px;
    color: #bee3f8;
}
</style>
""", unsafe_allow_html=True)

if "role" not in st.session_state:
    st.session_state["role"] = None

def logout():
    st.session_state["role"] = None
    st.rerun()

# --- EKRAN LOGOWANIA ---
if st.session_state["role"] is None:
    st.markdown("<h1 style='text-align:center;margin-top:80px'>RemontIQ</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#a0aec0'>Podaj PIN dostępu do aplikacji.</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            pin = st.text_input("PIN", type="password", placeholder="Wpisz 4-cyfrowy PIN")
            if st.form_submit_button("Zaloguj", width="stretch", type="primary"):
                inv_pin = st.secrets.get("auth", {}).get("investor_pin", "9999")
                crw_pin = st.secrets.get("auth", {}).get("crew_pin", "1234")
                if pin == str(inv_pin):
                    st.session_state["role"] = "investor"
                    st.session_state["last_visit"] = st.session_state.get("current_visit", None)
                    st.session_state["current_visit"] = datetime.now().isoformat()
                    st.rerun()
                elif pin == str(crw_pin):
                    st.session_state["role"] = "crew"
                    st.session_state["last_visit"] = st.session_state.get("current_visit", None)
                    st.session_state["current_visit"] = datetime.now().isoformat()
                    st.rerun()
                else:
                    st.error("Nieprawidłowy PIN!")
    st.stop()

def render_activity_banner(role):
    """Pokaż baner z nowymi zdarzeniami od ostatniej wizyty."""
    import time
    events = get_activity_banner(role)
    if not events:
        return
    
    # Session state do ukrywania bannera po czasie
    if "banner_visible_until" not in st.session_state:
        st.session_state["banner_visible_until"] = time.time() + 10 # 10 sekund

    if time.time() > st.session_state["banner_visible_until"]:
        return

    items_html = ""
    for e in events[:5]:
        icon = EVENT_ICONS.get(e["event_type"], ("\u2139\ufe0f", "both"))[0]
        ts = str(e.get("created_at", ""))[:16].replace("T", " ")
        items_html += f'<div class="activity-item">{icon} {e["description"]} <span style="color:#718096;font-size:11px">({ts})</span></div>'
    
    st.markdown(f"""
    <div class="activity-banner">
        <div style="font-weight:700;color:#90cdf4;margin-bottom:6px">
            🔔 Nowe zdarzenia ({len(events)})
        </div>
        {items_html}
    </div>""", unsafe_allow_html=True)



# ==========================================
# WIDOK EKIPY BUDOWLANEJ
# ==========================================
if st.session_state["role"] == "crew":
    c1, c2 = st.columns([4, 1])
    c1.title("\U0001f477 Dashboard Ekipy")
    if c2.button("Wyloguj"): logout()

    render_activity_banner("crew")

    from motywacja import get_daily_message, get_bonus_meme
    import random
    
    # Calculate day number based on earliest room
    try:
        df_rooms_for_date = supabase.table("rooms").select("created_at").order("created_at").limit(1).execute()
        if df_rooms_for_date.data:
            start_date = pd.to_datetime(df_rooms_for_date.data[0]['created_at']).date()
        else:
            start_date = date.today()
    except Exception:
        start_date = date.today()
        
    day_number = (date.today() - start_date).days + 1
    if day_number < 1: day_number = 1
    
    msg = get_daily_message(day_number)
    
    st.info(f"📅 **DZIEŃ {day_number} / 30**")
    st.success(msg)
    
    if random.random() > 0.7:  # 30% chance to show a bonus meme
        st.warning(get_bonus_meme())
    
    st.divider()
    
    st.markdown("""
<style>
    .kpi-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 20px; color: white; text-align: center; box-shadow: 0 8px 16px rgba(0,0,0,0.1); font-weight: bold; }
    .blocker-badge { background: #ff6b6b; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
    .log-decision { background: #2b6cb0; color: white; padding: 10px; border-radius: 8px; margin-bottom: 5px; border-left: 5px solid #90cdf4; }
    .log-issue { background: #9b2c2c; color: white; padding: 10px; border-radius: 8px; margin-bottom: 5px; border-left: 5px solid #feb2b2; }
</style>
""", unsafe_allow_html=True)
    
    st.subheader("📈 Szybki Przegląd")
    kpis = get_crew_kpis()
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("🟢 Aktywne", kpis['in_progress'])
    with col2: st.metric("❌ Zablokowane", kpis['blocked'])
    with col3: st.metric("🔔 Do Odbioru", kpis['awaiting_inspection'])
    with col4: st.metric("✅ Ukończone", kpis['completed'])
    with col5: st.metric("⏳ Dni do Końca", kpis['days_to_end'])
    
    st.divider()
    
    # --- PROJEKT LOGS DLA EKIPY ---
    st.subheader("🔔 Decyzje i Problemy")
    try:
        active_logs = supabase.table("project_logs").select("*").neq("status", "RESOLVED").neq("status", "DONE").order("created_at", desc=True).limit(5).execute().data or []
        if active_logs:
            for l in active_logs:
                cls = "log-decision" if l['type'] == "DECISION" else "log-issue"
                label = "💡 DECYZJA" if l['type'] == "DECISION" else "🚨 PROBLEM"
                st.markdown(f"""
                <div class="{cls}">
                    <div style="font-size:10px; font-weight:bold; opacity:0.8;">{label} | {l.get('due_date') or ''}</div>
                    <div style="font-size:14px;">{l['title']}</div>
                    <div style="font-size:11px; font-style:italic; opacity:0.9;">Wynik: {l.get('result') or 'Oczekiwanie...'}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ Brak aktywnych blokad z Dziennika.")
    except Exception:
        st.info("Dziennik jest pusty.")
    
    st.divider()
    
    tab_kanban, tab_plan, tab_comm, tab_rep = st.tabs(["🗂️ Tablica Kanban", "📅 Manager Harmonogramu", "💬 Centrum Komunikacji", "📝 Zgłoś / Raport"])

    with tab_kanban:
        # ===== GANTT CHART =====
        all_tasks_gantt = supabase.table("tasks").select(
            "id,name,kanban_status,planned_start_date,planned_end_date,is_blocked"
        ).order("planned_start_date").execute().data or []

        if all_tasks_gantt:
            with st.expander("📅 Mój Harmonogram", expanded=True):
                GANTT_COLORS = {
                    "BACKLOG":             "#4a5568",
                    "READY":               "#2b6cb0",
                    "IN_PROGRESS":         "#c05621",
                    "AWAITING_INSPECTION": "#744210",
                    "COMPLETED":           "#276749",
                }
                fig = go.Figure()
                today_str = date.today().isoformat()

                for task in all_tasks_gantt:
                    s_date = task.get("planned_start_date") or today_str
                    e_date = task.get("planned_end_date") or today_str
                    if s_date == e_date:  # min 1 day width
                        e_date = (datetime.strptime(e_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                    status = task.get("kanban_status") or "BACKLOG"
                    color = "#e53e3e" if task.get("is_blocked") else GANTT_COLORS.get(status, "#4a5568")
                    label = task["name"]
                    if task.get("is_blocked"): label += " 🔴"
                    hover = (
                        f"<b>{task['name']}</b><br>"
                        f"Status: {status}<br>"
                        f"Start: {task.get('planned_start_date','?')}<br>"
                        f"Koniec: {task.get('planned_end_date','?')}"
                    )
                    fig.add_trace(go.Bar(
                        name=task["name"],
                        y=[label],
                        x=[(datetime.strptime(e_date, "%Y-%m-%d") - datetime.strptime(s_date, "%Y-%m-%d")).days],
                        base=[s_date],
                        orientation="h",
                        marker=dict(color=color, line=dict(color="#1a1f2e", width=1)),
                        hovertemplate=hover + "<extra></extra>",
                        showlegend=False,
                    ))

                # Linia DZISIAJ (Metoda bezpieczna)
                fig.add_shape(
                    type="line", x0=today_str, x1=today_str,
                    y0=0, y1=1, yref="paper",
                    line=dict(color="#fc8181", width=2, dash="dash")
                )
                fig.add_annotation(
                    x=today_str, y=1, yref="paper",
                    text="DZISIAJ", showarrow=False,
                    font=dict(color="#fc8181"), yshift=10
                )

                fig.update_layout(
                    barmode="overlay",
                    height=max(120, len(all_tasks_gantt) * 48),
                    paper_bgcolor="#1a1f2e",
                    plot_bgcolor="#1a1f2e",
                    font=dict(color="#e2e8f0", family="Inter"),
                    xaxis=dict(
                        type="date",
                        gridcolor="#2d3748",
                        tickformat="%d %b",
                        color="#a0aec0",
                    ),
                    yaxis=dict(gridcolor="#2d3748", color="#a0aec0"),
                    margin=dict(l=10, r=10, t=10, b=10),
                )
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

                # Legenda
                st.markdown("""
                <div style="display:flex;gap:16px;font-size:12px;color:#a0aec0;flex-wrap:wrap;margin-top:4px">
                <span style="color:#4a5568">&#9632; Do Zrobienia</span>
                <span style="color:#c05621">&#9632; W Trakcie</span>
                <span style="color:#744210">&#9632; Do Odbioru</span>
                <span style="color:#276749">&#9632; Zamkni&#x0119;te</span>
                <span style="color:#e53e3e">&#9632; Zablokowane</span>
                </div>""", unsafe_allow_html=True)

        kanban = get_kanban_board()
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.markdown("### 📦 DO ZROBIENIA")
            for task in kanban.get('BACKLOG', []) + kanban.get('READY', []):
                with st.container(border=True):
                    st.markdown(f"**{task['name']}**")
                    st.caption(f"Start: {task['planned_start_date']}")
                    render_comment_section(task['id'], "crew")
                    if st.button("▶️ ROZPOCZNIJ", key=f"start_{task['id']}", width="stretch"):
                        start_task(task['id'])
                        st.rerun()

        with c2:
            st.markdown("### 🟧 W TRAKCIE")
            for task in kanban.get('IN_PROGRESS', []):
                blocked = task.get('is_blocked', False)
                with st.container(border=True):
                    st.markdown(f"**{task['name']}**")
                    if blocked: st.markdown("<span class='blocker-badge'>🔴 ZABLOKOWANE</span>", unsafe_allow_html=True)
                    st.caption(f"Do: {task['planned_end_date']}")
                    render_comment_section(task['id'], "crew")
                    if blocked:
                        st.warning(f"⛔ {task.get('blocker_reason')}")
                    else:
                        if st.button("🔔 DO ODBIORU", key=f"inspect_{task['id']}", width="stretch", type="primary"):
                            submit_for_inspection(task['id'])
                            st.rerun()
                        
                        # --- NOWY FORMULARZ BLOKADY (Sprint 13) ---
                        with st.expander("⛔ ZABLOKUJ ZADANIE"):
                            reason = st.text_area("Dlaczego stoisz? (wymagane)", key=f"reason_{task['id']}")
                            if st.button("Potwierdź blokadę", key=f"conf_block_{task['id']}", type="primary"):
                                if reason.strip():
                                    report_blocker(task['id'], reason)
                                    st.rerun()
                                else:
                                    st.error("Musisz podać powód!")

        with c3:
            st.markdown("### 🔔 DO ODBIORU")
            for task in kanban.get('AWAITING_INSPECTION', []):
                with st.container(border=True):
                    st.markdown(f"**{task['name']}**")
                    st.info("⏳ Czeka na akceptację")
                    render_comment_section(task['id'], "crew")

        with c4:
            st.markdown("### ✅ ZAMKNIĘTE")
            for task in kanban.get('COMPLETED', []):
                with st.container(border=True):
                    st.markdown(f"**{task['name']}**")
                    st.success("Zatwierdzone")
                    render_comment_section(task['id'], "crew")

    with tab_plan:
        st.markdown("## 📅 Manager Harmonogramu")
        st.caption("Ustaw kolejność zadań [↑↓], edytuj szczegóły lub dodaj nowe zadanie na końcu.")
        
        tasks_ord = get_tasks_ordered()
        
        if tasks_ord:
            for idx, t in enumerate(tasks_ord):
                col1, col2, col3, col4, col5 = st.columns([0.5, 4, 2, 0.5, 0.5])
                with col1: st.write(f"#{idx+1}")
                with col2: st.markdown(f"**{t['name']}** | 📍 {t.get('room_name', '—')}")
                with col3: st.caption(f"📅 {t.get('planned_start_date', '—')}")
                with col4:
                    if st.button("↑", key=f"up_{t['id']}"):
                        if move_task_up(t['id']): st.rerun()
                with col5:
                    if st.button("↓", key=f"down_{t['id']}"):
                        if move_task_down(t['id']): st.rerun()
                st.divider()

        # MODAL EDYCJI (Selectbox + Form)
        st.subheader("✏️ Edytuj lub Dodaj Zadanie")
        edit_option = st.selectbox("Wybierz zadanie do edycji lub 'NOWE ZADANIE'", 
                                    ["➕ NOWE ZADANIE"] + [f"{t['name']} (#{idx+1})" for idx, t in enumerate(tasks_ord)])
        
        with st.form("task_editor_form", clear_on_submit=True):
            if edit_option == "➕ NOWE ZADANIE":
                t_to_edit = {"name": "", "description": "", "planned_start_date": str(date.today()), "planned_end_date": str(date.today()), "room_id": None}
                st.info("Tworzysz nowe zadanie")
            else:
                idx_sel = int(edit_option.split("#")[-1].replace(")", "")) - 1
                t_to_edit = tasks_ord[idx_sel]
                st.info(f"Edytujesz: {t_to_edit['name']}")

            name_in = st.text_input("Nazwa zadania *", value=t_to_edit['name'])
            desc_in = st.text_area("Opis / Notatki", value=t_to_edit.get('description', ''))
            
            # Pobierz pokoje
            rooms_df = read_table("rooms", select="id, name")
            r_list = [{"id": None, "name": "Brak (Ogólne)"}]
            for _, r in rooms_df.iterrows(): r_list.append({"id": r['id'], "name": r['name']})
            
            curr_r_idx = next((i for i, r in enumerate(r_list) if r['id'] == t_to_edit.get('room_id')), 0)
            room_in = st.selectbox("Pomieszczenie", options=r_list, format_func=lambda x: x['name'], index=curr_r_idx)
            
            c1, c2 = st.columns(2)
            start_in = c1.date_input("Start", value=datetime.strptime(t_to_edit['planned_start_date'][:10], "%Y-%m-%d") if t_to_edit.get('planned_start_date') else date.today())
            end_in = c2.date_input("Koniec", value=datetime.strptime(t_to_edit['planned_end_date'][:10], "%Y-%m-%d") if t_to_edit.get('planned_end_date') else date.today())

            if st.form_submit_button("💾 ZAPISZ ZMIANY", type="primary"):
                if not name_in.strip(): st.error("Nazwa jest wymagana")
                else:
                    payload = {
                        "name": name_in, "description": desc_in, "room_id": room_in['id'],
                        "planned_start_date": str(start_in), "planned_end_date": str(end_in)
                    }
                    if edit_option == "➕ NOWE ZADANIE":
                        # Nowe zadanie na koniec kolejki
                        payload["position_in_queue"] = len(tasks_ord) + 1
                        supabase.table("tasks").insert(payload).execute()
                    else:
                        supabase.table("tasks").update(payload).eq("id", t_to_edit['id']).execute()
                    st.success("Zapisano!")
                    st.rerun()

    with tab_comm:
        st.title("💬 Centrum Komunikacji")
        sel_chat = st.session_state.get("selected_chat_crew", "GLOBAL")

        all_comments_grouped = get_all_comments_grouped()
        if not all_comments_grouped:
            st.info("📭 Brak komentarzy.")
        else:
            col_side, col_chat = st.columns([2, 4])
            with col_side:
                st.markdown("### 📋 Zadania")
                if st.button("🌍 Wszystkie wiadomości", width="stretch", key="crew_global"):
                    st.session_state.selected_chat_crew = "GLOBAL"
                st.divider()
                for group in all_comments_grouped:
                    count = len([c for c in group['comments'] if not c.get('is_deleted')])
                    if st.button(f"📌 {group['task_name']} ({count})", width="stretch", key=f"crew_chat_{group['task_id']}"):
                        st.session_state.selected_chat_crew = group['task_id']
            
            with col_chat:
                if sel_chat == "GLOBAL":
                    all_c = []
                    for g in all_comments_grouped: all_c.extend(g['comments'])
                    all_c.sort(key=lambda x: x.get('created_at', ''))
                    render_whatsapp_chat(all_c, "Karol", "GLOBAL", context="comm_crew_global")
                    st.info("💡 Wybierz zadanie, aby odpowiedzieć.")
                else:
                    task_c = next((g for g in all_comments_grouped if g['task_id'] == sel_chat), None)
                    if task_c:
                        render_whatsapp_chat(task_c['comments'], "Karol", sel_chat, context="comm_crew_task")
                        render_chat_input(sel_chat, "Karol", context="comm_crew_task")

    with tab_rep:
        st.subheader("📝 Zgłoś potrzebę / brak materiału")
        
        all_tasks_resp = supabase.table("tasks").select("id, name").execute()
        task_options_map = {"(brak powiązania)": None}
        for t in (all_tasks_resp.data or []):
            task_options_map[t['name']] = t['id']

        with st.form("crew_req_form", clear_on_submit=True):
            col1, col2 = st.columns([3, 1])
            title = col1.text_input("Czego brakuje? *", placeholder="np. Fuga Mapei szara 2kg")
            needed = col2.date_input("Potrzebne do:")
            linked_name = st.selectbox("Dotyczy zadania (opcjonalnie):", options=list(task_options_map.keys()))
            blocker = st.checkbox("🚨 PILNE — To wstrzymuje nasze prace! (auto-zablokuje zadanie)")
            if st.form_submit_button("Wyślij do Inwestora", type="primary"):
                if not title.strip():
                    st.error("Wpisz co jest potrzebne!")
                else:
                    linked_id = task_options_map.get(linked_name)
                    submit_crew_request_with_blocker(title, needed, blocker, linked_id)
                    if blocker and linked_id:
                        st.success(f"✅ Wysłano! Zadanie '{linked_name}' zostało oznaczone jako ZABLOKOWANE u Inwestora.")
                    else:
                        st.success("✅ Wysłano zgłoszenie!")
                    st.rerun()

        st.divider()
        st.subheader("📦 Status moich zgłoszeń")
        my_grouped = get_crew_requests_grouped()
        status_icons = {"Nowe": "🔴", "Potwierdzone": "🟡", "Dostarczone": "🟢", "Anulowane": "⬜"}
        for status, reqs in my_grouped.items():
            if not reqs: continue
            with st.expander(f"{status_icons[status]} {status} ({len(reqs)})"):
                for req in reqs:
                    st.markdown(f"**{req['title']}**")
                    if req.get("investor_note"):
                        st.info(f"📝 Inwestor: {req['investor_note']}")
                    if req.get("expected_delivery_date"):
                        st.caption(f"📅 Dostawa: {req['expected_delivery_date']}")
                    st.divider()

    st.stop()




# ==========================================
# WIDOK INWESTORA
# ==========================================
st.sidebar.markdown("### Zalogowano jako: Inwestor")
if st.sidebar.button("Wyloguj"): logout()
st.sidebar.divider()

render_activity_banner("investor")

project_meta = get_project_metadata()
if project_meta:
    st.sidebar.markdown(f"### 🏗️ {project_meta['project_name']}")
    st.sidebar.caption(f"Status: {project_meta['status']}")
else:
    st.sidebar.warning("⚠️ Charter nie utworzony")

menu = st.sidebar.radio("Nawigacja", [
    "1. Dashboard (Centrum)",
    "1a. Centrum Komunikacji",
    "2. Start remontu",
    "4. Zadania",
    "4a. Odbiór Prac",
    "5. Ekipa",
    "6. Wydatki (Finanse)",
    "7. Dziennik Projektu (Decyzje/Ryzyka)",
    "8. Ustawienia",
    "0. Charter Projektu",
])

# Pomocnicza lista pokoi
df_rooms = read_table("rooms", select="id, name")
rooms_dict = [{"id": None, "name": "Brak (Ogólne)"}]
for _, r in df_rooms.iterrows():
    rooms_dict.append({"id": r['id'], "name": r['name']})

if menu == "0. Charter Projektu":
    st.title("🏗️ CHARTER PROJEKTU")
    st.caption("Główna oś czasu i parametry projektu")

    if not project_meta:
        st.warning("⚠️ Charter nie został jeszcze utworzony")
        with st.form("charter_creation_form", clear_on_submit=False):
            st.subheader("📋 Podstawowe informacje")
            col1, col2 = st.columns(2)
            project_name = col1.text_input("Nazwa projektu *")
            investor_name = col2.text_input("Twoje imię (Inwestor) *")
            project_desc = st.text_area("Opis projektu (opcjonalnie)")
            
            st.subheader("📅 Harmonogram projektu")
            col1, col2, col3 = st.columns(3)
            start_date = col1.date_input("Data startu projektu *", value=date.today() + timedelta(days=7))
            end_date = col2.date_input("Data zakończenia projektu *", value=date.today() + timedelta(days=52))
            
            st.subheader("💰 Budżet")
            total_budget = st.number_input("Całkowity budżet projektu (zł) *", min_value=10000, step=10000, value=100000)
            
            st.subheader("👥 Zespół projektu")
            col1, col2 = st.columns(2)
            crew_lead_name = col1.text_input("Imię szefa ekipy")
            crew_contact = col2.text_input("Telefon do szefa ekipy")
            
            st.subheader("📝 Zakres prac")
            scope = st.text_area("Co będzie remontem obejmować? *", height=100)
            
            st.subheader("⚡ Warunki specjalne")
            conditions = st.text_area("Warunki specjalne (opcjonalnie)", height=80)
            
            if st.form_submit_button("🚀 UTWÓRZ CHARTER PROJEKTU", width="stretch", type="primary"):
                if not project_name or not investor_name or not scope or not start_date or not end_date:
                    st.error("❌ Uzupełnij pola oznaczone *")
                elif end_date <= start_date:
                    st.error("❌ Data zakończenia musi być PO dacie startu")
                else:
                    create_project_metadata(
                        project_name=project_name, project_description=project_desc,
                        planned_start_date=start_date, planned_end_date=end_date,
                        total_budget=total_budget, investor_name=investor_name,
                        crew_lead_name=crew_lead_name or "Nie wiadomo", crew_contact=crew_contact or "Brak",
                        scope_of_work=scope, special_conditions=conditions, status="PLANNING"
                    )
                    st.success("✅ Charter utworzony!")
                    st.rerun()
    else:
        st.subheader(f"📌 {project_meta['project_name']}")
        col1, col2, col3, col4 = st.columns(4)
        start_str = project_meta['planned_start_date']
        end_str = project_meta['planned_end_date']
        start_date_obj = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date_obj = datetime.strptime(end_str, "%Y-%m-%d").date()
        total_days = (end_date_obj - start_date_obj).days
        
        col1.metric("📅 Start", start_date_obj.strftime("%d.%m.%Y"))
        col2.metric("📅 Koniec", end_date_obj.strftime("%d.%m.%Y"))
        col3.metric("⏱️ Czas całkowity", f"{total_days} dni")
        col4.metric("💰 Budżet", f"{project_meta['total_budget']:,.0f} zł")
        
        st.divider()
        st.subheader("📊 Oś czasu projektu")
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=['Projekt'], x=[total_days], orientation='h',
            marker=dict(color='#00D9FF', line=dict(color='#006FA5', width=2)),
            text=f"{total_days} dni", textposition='inside',
            hovertemplate=f"<b>Projekt</b><br>Start: {start_date_obj.strftime('%d.%m.%Y')}<br>Koniec: {end_date_obj.strftime('%d.%m.%Y')}<extra></extra>"
        ))
        fig.update_xaxes(title_text="Dni")
        fig.update_yaxes(showticklabels=False)
        fig.update_layout(height=150, showlegend=False, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, width="stretch")
        
        st.divider()
        st.subheader("📍 Status i kontrola")
        days_info = get_project_days_info(project_meta)
        
        if project_meta['status'] == "PLANNING":
            st.warning("🟡 **Status: PLANOWANIE**")
            st.info("✅ **Checklist przed aktywacją:**\n- [ ] Materiały zamówione\n- [ ] Ekipa potwierdzona\n- [ ] Decyzje podjęte")
            if st.button("🚀 URUCHOM PROJEKT", width="stretch", type="primary"):
                update_project_metadata(project_meta['id'], status="ACTIVE", actual_start_date=date.today())
                st.rerun()
        elif project_meta['status'] == "ACTIVE":
            st.success("🟢 **Status: W TRAKCIE**")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("⏳ Dni upłynęło", days_info['elapsed_days'])
            c2.metric("📅 Dni zostało", max(0, days_info['remaining_days']))
            c3.metric("📊 Postęp", f"{days_info['progress_pct']}%")
            if days_info['remaining_days'] < 7: c4.error(f"🚨 {days_info['remaining_days']} dni!")
            else: c4.info("✅ OK")
            st.progress(days_info['progress_pct'] / 100, text=f"Realizacja: {days_info['progress_pct']}%")
            if st.button("✅ Zakończ projekt", width="stretch", type="primary"):
                update_project_metadata(project_meta['id'], status="COMPLETED", actual_end_date=date.today())
                st.rerun()
        elif project_meta['status'] == "COMPLETED":
            st.success("✅ **Status: UKOŃCZONY**")

elif menu == "1. Dashboard (Centrum)":
    st.title("🎮 COMMAND CENTER")
    st.caption(f"Centrum kontroli projektu — {date.today().strftime('%d.%m.%Y')}")

    # ==============================
    # DANE v6.0
    # ==============================
    all_tasks = supabase.table("tasks").select("*").execute().data or []
    pending_insp = get_pending_inspections()
    all_logs = supabase.table("project_logs").select("*").execute().data or []
    
    blocked_tasks = [t for t in all_tasks if t.get("is_blocked")]
    active_decisions = [l for l in all_logs if l['type'] == 'DECISION' and l['status'] != 'DONE']
    active_issues = [l for l in all_logs if l['type'] == 'ISSUE' and l['status'] != 'RESOLVED']

    # ==============================
    # SEKCJA 1: ALARMY
    # ==============================
    st.markdown("## ⚡ WYMAGAJĄ TWOJEGO DZIAŁANIA")
    c1, c2, c3, c4 = st.columns(4)
    
    def render_tile(col, label, emoji, count, sub):
        clr = "#e53e3e" if count > 0 else "#38a169"
        bg = "rgba(229,62,62,0.08)" if count > 0 else "rgba(56,161,105,0.08)"
        col.markdown(f"""
        <div style="background:{bg};border:2px solid {clr};border-radius:10px;padding:16px;text-align:center;">
            <div style="font-size:28px">{emoji}</div>
            <div style="font-size:13px;color:#888">{label}</div>
            <div style="font-size:36px;font-weight:bold;color:{clr}">{count}</div>
            <div style="font-size:11px;color:#aaa">{sub}</div>
        </div>""", unsafe_allow_html=True)

    render_tile(c1, "Do Odbioru", "🔔", len(pending_insp), "")
    render_tile(c2, "Blokery", "🔴", len(blocked_tasks), "")
    render_tile(c3, "Decyzje", "🤔", len(active_decisions), "Aktywne logi")
    render_tile(c4, "Problemy", "⚠️", len(active_issues), "Nierozwiązane")

    st.divider()
    
    # ==============================
    # SEKCJA 2: PULS PROJEKTU
    # ==============================
    st.markdown("## 📊 PULS PROJEKTU")
    if project_meta:
        days_info = get_project_days_info(project_meta)
        col_h1, col_h2 = st.columns([1, 2])
        with col_h1:
            st.metric("Postęp Całkowity", f"{days_info['progress_pct']}%")
        with col_h2:
            st.progress(days_info['progress_pct'] / 100)
            st.caption(f"Upłynęło dni: {days_info['elapsed_days']} / {days_info['total_days']}")
    
    st.divider()

    st.divider()

    # ==============================
    # SEKCJA 3: DO ODBIORU (inline)
    # ==============================
    if pending_insp:
        st.markdown(f"## 🔔 DO ODBIORU ({len(pending_insp)})")
        for insp in pending_insp:
            task_r = supabase.table("tasks").select("name,assigned_to").eq("id", insp["task_id"]).execute()
            task_info = task_r.data[0] if task_r.data else {}
            with st.container(border=True):
                h1, h2 = st.columns([4, 1])
                h1.markdown(f"### 🔔 {task_info.get('name', '?')}")
                h1.caption(f"Zgłoszono: {str(insp.get('submitted_at',''))[:10]} | Zespół: {task_info.get('assigned_to','—')}")
                h2.warning("⏳ Czeka")
                if insp.get("submission_notes"):
                    st.info(f"📝 Karol: {insp['submission_notes']}")
                render_comment_section(insp['task_id'], "investor")
                ba, bb = st.columns(2)
                if ba.button("✅ ZATWIERDŹ", key=f"cc_appr_{insp['id']}", width="stretch", type="primary"):
                    approve_inspection(insp["id"])
                    st.success("✅ Zatwierdzone! Karol widzi to na tablicy.")
                    st.rerun()
                if bb.button("❌ WYMAGA POPRAWEK", key=f"cc_rwrk_{insp['id']}", width="stretch"):
                    st.session_state[f"rework_{insp['id']}"] = True
                if st.session_state.get(f"rework_{insp['id']}"):
                    rw = st.text_area("Opisz co poprawić", key=f"rw_txt_{insp['id']}")
                    if st.button("Wyślij poprawki", key=f"rw_send_{insp['id']}"):
                        request_rework(insp["id"], rw)
                        st.session_state.pop(f"rework_{insp['id']}", None)
                        st.rerun()
        st.divider()

    # ==============================
    # SEKCJA 4: BLOKERY PRACY (inline)
    # ==============================
    if blocked_tasks:
        st.markdown(f"## 🔴 BLOKERY PRACY — Co masz zrobić? ({len(blocked_tasks)})")
        for task in blocked_tasks:
            with st.container(border=True):
                bh1, bh2 = st.columns([4, 1])
                bh1.markdown(f"### {task['name']}")
                bh1.caption(f"Powód główny: {task.get('blocker_reason', '—')}")
                bh2.error("🔴 BLOKADA")
                
                # Pobierz szczegółowe blokery z bazy
                blks = get_blockers_for_task(task['id'])
                if blks:
                    st.markdown("**Aktywne przyczyny:**")
                    for b in blks:
                        col_b1, col_b2 = st.columns([3, 1])
                        col_b1.write(f"• {b['description']}")
                        if col_b2.button("✅ ODBLOKUJ", key=f"res_{b['id']}", width="stretch"):
                            resolve_blocker(b['id'], "Rozwiązane przez Inwestora w Command Center")
                            st.rerun()
                
                render_comment_section(task['id'], "investor")
                
                # Zgłoszenia materiałowe powiązane z tym zadaniem
                linked_reqs = [r for r in (crew_grouped.get("Nowe", []) + crew_grouped.get("Potwierdzone", [])) if r.get("linked_task_id") == task["id"]]
                for req in linked_reqs:
                    st.write(f"📦 **{req['title']}** — status: {req['status']}")
                    if req["status"] == "Potwierdzone":
                        if st.button(f"📦 DOSTARCZONE — {req['title']}", key=f"cc_del_{req['id']}", type="primary"):
                            mark_crew_request_delivered(req["id"])
                            st.rerun()
        st.divider()

    # ==============================
    # SEKCJA 5: ZGŁOSZENIA EKIPY (inline)
    # ==============================
    if new_requests:
        st.markdown(f"## 🛠️ NOWE ZGŁOSZENIA EKIPY ({len(new_requests)})")
        for req in new_requests:
            with st.container(border=True):
                rh1, rh2 = st.columns([4, 1])
                label = "🚨 PILNE — " if req.get("is_blocker") else ""
                rh1.markdown(f"**{label}{req['title']}**")
                rh1.caption(f"Potrzebne do: {req.get('needed_by','—')}")
                rh2.error("🔴 NOWE")
                with st.form(f"cc_req_form_{req['id']}", clear_on_submit=True):
                    fn1, fn2 = st.columns([3, 1])
                    note_val = fn1.text_input("Twoja notatka", placeholder="np. Zamówiłem, dostawa w czwartek", key=f"cc_note_{req['id']}")
                    del_date = fn2.date_input("Dostawa", key=f"cc_ddate_{req['id']}")
                    fa, fb = st.columns(2)
                    if fa.form_submit_button("✅ POTWIERDŹ", width="stretch", type="primary"):
                        confirm_crew_request(req["id"], note_val, del_date)
                        st.rerun()
                    if fb.form_submit_button("❌ ANULUJ", width="stretch"):
                        cancel_crew_request(req["id"])
                        st.rerun()
        st.divider()

    # ==============================
    # SEKCJA 6: PLAN KAROLA (mini)
    # ==============================
    st.markdown("## 📅 PLAN KAROLA — TOP 5 ZADAŃ")
    top_tasks = supabase.table("tasks").select("name,kanban_status,planned_start_date,planned_end_date,is_blocked").order("planned_start_date").limit(5).execute().data or []
    if top_tasks:
        STATUS_EMOJI = {"BACKLOG": "⬜", "READY": "🟦", "IN_PROGRESS": "🟧", "AWAITING_INSPECTION": "🔔", "COMPLETED": "🟩"}
        for t in top_tasks:
            blk = " 🔴 ZABLOKOWANE" if t.get("is_blocked") else ""
            em = STATUS_EMOJI.get(t.get("kanban_status", "BACKLOG"), "❓")
            st.write(f"{em} **{t['name']}**{blk}")
            st.caption(f"   {t.get('planned_start_date','?')} → {t.get('planned_end_date','?')}")
    else:
        st.info("Karol jeszcze nie zaplanował zadań.")



elif menu == "1a. Centrum Komunikacji":
    st.title("💬 Centrum Komunikacji")
    sel_chat = st.session_state.get("selected_chat", "GLOBAL")

    all_comments_grouped = get_all_comments_grouped()
    if not all_comments_grouped:
        st.info("📭 Brak komentarzy.")
    else:
        col_side, col_chat = st.columns([2, 4])
        with col_side:
            st.markdown("### 📋 Zadania")
            if st.button("🌍 Wszystkie wiadomości", width="stretch", key="inv_global"):
                st.session_state.selected_chat = "GLOBAL"
            st.divider()
            for group in all_comments_grouped:
                count = len([c for c in group['comments'] if not c.get('is_deleted')])
                if st.button(f"📌 {group['task_name']} ({count})", width="stretch", key=f"inv_chat_{group['task_id']}"):
                    st.session_state.selected_chat = group['task_id']
        
        with col_chat:
            if sel_chat == "GLOBAL":
                all_c = []
                for g in all_comments_grouped: all_c.extend(g['comments'])
                all_c.sort(key=lambda x: x.get('created_at', ''))
                render_whatsapp_chat(all_c, "Inwestor", "GLOBAL", context="center_global")
                st.info("💡 Wybierz zadanie, aby odpowiedzieć.")
            else:
                task_c = next((g for g in all_comments_grouped if g['task_id'] == sel_chat), None)
                if task_c:
                    render_whatsapp_chat(task_c['comments'], "Inwestor", sel_chat, context="center_task")
                    render_chat_input(sel_chat, "Inwestor", context="center_task")

elif menu == "2. Start remontu":
    st.title("🚀 Kreator Startowy (Cloud)")
    st.write("Bezpiecznie dodaj pokoje do projektu w chmurze.")
    with st.form("kreator_form", clear_on_submit=True):
        pokoje_input = st.text_input("Jakie pomieszczenia remontujesz? (po przecinku)")
        if st.form_submit_button("Zapisz pomieszczenia"):
            pokoje = [p.strip() for p in pokoje_input.split(",") if p.strip()]
            for p in pokoje:
                try: supabase.table("rooms").insert({"name": p}).execute()
                except Exception: pass
            st.success(f"Przetworzono {len(pokoje)} pomieszczeń.")
            st.rerun()
    df_r_view = read_table("rooms")
    if not df_r_view.empty:
        st.dataframe(df_r_view[['name', 'created_at']], hide_index=True)
    else:
        st.info("Brak wprowadzonych pomieszczeń.")

elif menu == "6. Wydatki (Finanse)":
    st.title("💰 Wydatki (Supabase Sync)")
    df_exp = read_table("expenses")
    total = df_exp['amount'].sum() if not df_exp.empty else 0
    st.metric("Całkowite wydatki", f"{total:,.2f} zł")

    with st.expander("➕ Dodaj wydatek", expanded=True):
        with st.form("new_expense_simple"):
            e_desc = st.text_input("Opis (np. Płytki Castorama) *")
            e_amount = st.number_input("Kwota (zł) *", min_value=0.0)
            e_date = st.date_input("Data", value=date.today())
            if st.form_submit_button("Zapisz Wydatek"):
                if e_desc.strip() and e_amount > 0:
                    supabase.table("expenses").insert({
                        "description": e_desc, "amount": e_amount, "date": str(e_date)
                    }).execute()
                    st.rerun()
                else: st.error("Opis i kwota są wymagane.")

    st.subheader("📜 Historia Wydatków")
    if not df_exp.empty:
        st.dataframe(df_exp[['date', 'description', 'amount']], width="stretch", hide_index=True)
    else:
        st.info("Brak zarejestrowanych wydatków.")

elif menu == "4. Zadania":
    st.title("📋 PLAN KAROLA — Twoje Zadania")
    st.caption("Karol zaplanował pracę. Twoja rola: usunąć blokady i dodać uwagi.")
    tasks = get_tasks_with_dependencies()

    if not tasks:
        st.info("📭 Karol jeszcze nie zaplanował żadnych zadań")
    else:
        for task in tasks:
            task_id = task['id']
            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.markdown(f"### {task['name']}")
                with col2:
                    st.write(f"**{task['status']}**")
                with col3:
                    st.metric("Postęp", f"{task.get('progress_percent', 0)}%")
                
                c1, c2 = st.columns(2)
                c1.write(f"**Zespół:** {task.get('assigned_to', '—')}")
                c1.write(f"**Okres:** {task['planned_start_date']} - {task['planned_end_date']}")
                if task.get('description'): c2.write(f"**Instrukcja:** {task['description']}")
                
                if not task.get('all_dependencies_met', True):
                    st.error(f"⛔ Zablokowane. Zależy od innych zadań.")
                
                st.write("**🟨 Twoja notatka (widoczna dla Karola):**")
                current_note = task.get('investor_note') or ""
                new_note = st.text_area("Dodaj notatkę", value=current_note, key=f"note_{task_id}", label_visibility="collapsed")
                
                if st.button("💾 Zapisz notatkę", key=f"save_note_{task_id}"):
                    add_investor_note(task_id, new_note)
                    st.success("Zapisano notatkę!")
                    st.rerun()
                
                if task['status'] != 'Done' and st.button("✅ Oznacz jako UKOŃCZONE", key=f"complete_{task_id}"):
                    complete_task(task_id)
                    st.success("Zadanie ukończone!")
                    st.rerun()

elif menu == "4a. Odbiór Prac":
    st.title("🔔 ODBIÓR PRAC")
    st.caption("Karol zgłosił zakończenie zadań. Sprawdzi je, dodaj komentarz i zatwierdź lub zażąda poprawek.")

    pending = get_pending_inspections()

    if not pending:
        st.success("✅ Brak zadań czekających na odbiór. Wszystko zatwierdzone!")
    else:
        st.warning(f"⏳ **{len(pending)} zadań czeka na Twój odbiór!**")
        st.divider()

        for inspection in pending:
            # Pobierz dane zadania
            task_resp = supabase.table("tasks").select("*").eq("id", inspection['task_id']).execute()
            task = task_resp.data[0] if task_resp.data else {}

            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"### 🔔 {task.get('name', 'Nieznane zadanie')}")
                    st.caption(f"Zgłoszono do odbioru: {inspection.get('submitted_at', '')[:10]}")
                with col2:
                    st.metric("Status", "⏳ Do odbioru")

                st.write(f"**Zespół:** {task.get('assigned_to', '—')}")
                if task.get('description'):
                    st.write(f"**Zakres prac:** {task['description']}")
                if inspection.get('submission_notes'):
                    st.info(f"📝 **Uwagi Karola:** {inspection['submission_notes']}")

                st.divider()
                st.write("**Twoja decyzja:**")

                col_approve, col_rework = st.columns(2)
                with col_approve:
                    approve_note = st.text_input("Komentarz przy zatwierdzeniu (opcjonalnie)", key=f"approve_note_{inspection['id']}")
                    if st.button("✅ ZATWIERDŹ PRACE", key=f"approve_{inspection['id']}", width="stretch", type="primary"):
                        result = approve_inspection(inspection['id'], approve_note)
                        if result['status'] == 'ok':
                            st.success(f"✅ Zadanie \"{task.get('name')}\" zatwierdzone! Karol zobaczy to na swojej tablicy.")
                            st.rerun()

                with col_rework:
                    rework_desc = st.text_area("Opisz co wymaga poprawek *", key=f"rework_desc_{inspection['id']}", placeholder="np. Poprawić kąt nachylenia przy wannie")
                    if st.button("❌ WYMAGA POPRAWEK", key=f"rework_{inspection['id']}", width="stretch"):
                        if not rework_desc.strip():
                            st.error("Musisz opisać co wymaga poprawek!")
                        else:
                            result = request_rework(inspection['id'], rework_desc)
                            if result['status'] == 'ok':
                                st.warning(f"❌ Zadanie \"{task.get('name')}\" wróciło do Karola z opisem poprawek.")
                                st.rerun()

    st.divider()
    st.subheader("📜 Historia odbiorów")
    try:
        history = supabase.table("task_inspection").select("*").neq("inspection_status", "PENDING").order("inspected_at", desc=True).execute()
        if history.data:
            for item in history.data:
                task_r = supabase.table("tasks").select("name").eq("id", item['task_id']).execute()
                task_name = task_r.data[0]['name'] if task_r.data else "?"
                icon = "✅" if item['inspection_status'] == "APPROVED" else "❌"
                st.caption(f"{icon} **{task_name}** — {item['inspection_status']} — {str(item.get('inspected_at',''))[:10]}")
                if item.get('rework_description'):
                    st.caption(f"   ↳ Poprawki: {item['rework_description']}")
        else:
            st.info("Brak historii odbioru.")
    except Exception as e:
        st.error(f"Błąd wczytywania historii: {e}")

elif menu == "5. Ekipa":
    st.title("👷 Zapotrzebowania Ekipy")
    st.caption("Karol zgłasza czego potrzebuje. Potwierdź, że się tym zajmujesz i oznacz jako dostarczone.")

    grouped = get_crew_requests_grouped()

    nowe = grouped.get("Nowe", [])
    potwierdzone = grouped.get("Potwierdzone", [])
    dostarczone = grouped.get("Dostarczone", [])

    # --- KPI ---
    k1, k2, k3 = st.columns(3)
    k1.metric("🔴 Nowe zgłoszenia", len(nowe))
    k2.metric("🟡 W toku (potwierdzone)", len(potwierdzone))
    k3.metric("🟢 Dostarczone", len(dostarczone))
    st.divider()

    # --- NOWE ---
    if nowe:
        st.subheader(f"🔴 Do obsługi ({len(nowe)})")
        for req in nowe:
            is_blocker = req.get("is_blocker", False)
            with st.container(border=True):
                col_info, col_btns = st.columns([3, 2])
                with col_info:
                    label = "🚨 PILNE — " if is_blocker else ""
                    st.markdown(f"**{label}{req['title']}**")
                    st.caption(f"Potrzebne do: {req.get('needed_by', '—')}")
                with col_btns:
                    with st.form(f"confirm_form_{req['id']}", clear_on_submit=True):
                        note = st.text_input("Twoja notatka (opcjonalnie)", placeholder="np. Zamówiłem, dostawa czwartek", key=f"note_{req['id']}")
                        delivery = st.date_input("Szacowana dostawa", key=f"del_{req['id']}")
                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("✅ POTWIERDŹ", width="stretch", type="primary"):
                            confirm_crew_request(req['id'], note, delivery)
                            st.rerun()
                        if c2.form_submit_button("❌ ANULUJ", width="stretch"):
                            cancel_crew_request(req['id'])
                            st.rerun()
    else:
        st.success("✅ Brak nowych zgłoszeń!")

    # --- POTWIERDZONE ---
    if potwierdzone:
        st.divider()
        st.subheader(f"🟡 W toku — czekają na dostawę ({len(potwierdzone)})")
        for req in potwierdzone:
            with st.container(border=True):
                col_info, col_btn = st.columns([3, 1])
                with col_info:
                    st.markdown(f"**{req['title']}**")
                    if req.get("investor_note"):
                        st.info(f"📝 {req['investor_note']}")
                    if req.get("expected_delivery_date"):
                        st.caption(f"📅 Szacowana dostawa: {req['expected_delivery_date']}")
                with col_btn:
                    if st.button("📦 DOSTARCZONE", key=f"del_btn_{req['id']}", width="stretch", type="primary"):
                        mark_crew_request_delivered(req['id'])
                        st.rerun()

    # --- DOSTARCZONE (Historia) ---
    if dostarczone:
        with st.expander(f"📜 Historia dostarczonych ({len(dostarczone)})"):
            for req in dostarczone:
                st.caption(f"✅ {req['title']} — dostarczone {str(req.get('delivered_at',''))[:10]}")


# ==========================================
# NOWE MODUŁY SPRINT 4 (7-10)
# ==========================================

elif menu == "7. Dziennik Projektu (Decyzje/Ryzyka)":
    st.title("📒 Dziennik Projektu")
    st.write("Decyzje i problemy w jednym miejscu.")
    
    col1, col2 = st.columns(2)
    with col1:
        with st.expander("➕ Dodaj Decyzję"):
            with st.form("form_dec"):
                t = st.text_input("Tytuł decyzji *")
                d = st.date_input("Termin")
                if st.form_submit_button("Dodaj"):
                    supabase.table("project_logs").insert({"type": "DECISION", "title": t, "due_date": str(d)}).execute()
                    st.rerun()
    with col2:
        with st.expander("➕ Zgłoś Problem"):
            with st.form("form_iss"):
                t = st.text_input("Opis problemu *")
                s = st.selectbox("Ważność", ["LOW", "MEDIUM", "HIGH"])
                if st.form_submit_button("Zgłoś"):
                    supabase.table("project_logs").insert({"type": "ISSUE", "title": t, "severity": s}).execute()
                    st.rerun()

    tab_dec, tab_iss = st.tabs(["📝 Decyzje", "⚠️ Problemy"])
    with tab_dec:
        recs = supabase.table("project_logs").select("*").eq("type", "DECISION").execute().data or []
        if recs:
            df = pd.DataFrame(recs)
            # Czyścimy NaN
            df = df.where(pd.notnull(df), None)
            ed = st.data_editor(df[['id', 'title', 'status', 'due_date', 'result']], key="ed_dec", width="stretch")
            if st.button("Zapisz zmiany (Decyzje)"):
                for _, r in ed.iterrows():
                    supabase.table("project_logs").update({
                        "status": r['status'] or "OPEN", 
                        "result": r['result'] or ""
                    }).eq("id", r['id']).execute()
                st.rerun()
        else: st.info("Brak decyzji.")

    with tab_iss:
        recs = supabase.table("project_logs").select("*").eq("type", "ISSUE").execute().data or []
        if recs:
            df = pd.DataFrame(recs)
            df = df.where(pd.notnull(df), None)
            ed = st.data_editor(df[['id', 'title', 'severity', 'status']], key="ed_iss", width="stretch")
            if st.button("Zapisz zmiany (Problemy)"):
                for _, r in ed.iterrows():
                    supabase.table("project_logs").update({
                        "status": r['status'] or "OPEN", 
                        "severity": r['severity'] or "MEDIUM"
                    }).eq("id", r['id']).execute()
                st.rerun()
        else: st.info("Brak problemów.")

elif menu == "8. Ustawienia":
    st.title("⚙️ Ustawienia i Eksport")
    
    st.subheader("🏠 Zarządzanie Pomieszczeniami")
    df_r = read_table("rooms")
    if not df_r.empty:
        edited_r = st.data_editor(df_r[['id', 'name']], disabled=["id"], hide_index=True, width="stretch")
        if st.button("Zapisz zmiany w nazwach"):
            for _, row in edited_r.iterrows():
                supabase.table("rooms").update({"name": row['name']}).eq("id", row['id']).execute()
            st.rerun()
            
    st.divider()
    st.subheader("📊 Eksport Danych")
    df_exp_full = read_table("expenses")
    if not df_exp_full.empty:
        csv = df_exp_full.to_csv(index=False).encode('utf-8')
    else:
        st.info("Brak wprowadzonych wydatków.")
        
    st.divider()
    st.subheader("🔒 Bezpieczeństwo")
    st.info("Logowanie do aplikacji odbywa się poprzez kody PIN. Edycja PIN-ów jest bezpiecznie przechowywana w pliku `.streamlit/secrets.toml` na serwerze.")
