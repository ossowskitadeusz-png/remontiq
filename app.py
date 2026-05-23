import streamlit as st
import html
import pandas as pd
from datetime import date, timedelta, datetime
import hashlib
import time
from typing import List, Dict
from supabase import create_client, Client
import plotly.graph_objects as go
import random
import string
import os

APP_VERSION = "sprint27-v2.1-stable"

# ==========================================
# 1. SUPABASE CONNECTION (Chmura)
# ==========================================

from services.access_service import validate_crew_access_code, create_crew_access_code

def apply_saas_theme():
    """Wstrzykuje zaawansowany CSS dla profesjonalnego SaaS Layout."""
    st.markdown("""
    <style>
        /* 1. Reset i Stylizacja */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .stDeployButton {display:none;}
        
        /* Przywracamy przycisk boczny (Sidebar Toggle) i stylizujemy go */
        button[kind="header"] {
            z-index: 1001 !important;
            color: white !important;
            background: rgba(255,255,255,0.1) !important;
            margin-left: 5px !important;
            margin-top: 5px !important;
        }
        
        /* 2. Floating Top Bar */
        .main-header {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 65px;
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            z-index: 999;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 30px;
            color: white;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .logo-text {
            font-size: 24px;
            font-weight: 800;
            background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .project-badge {
            background: rgba(59, 130, 246, 0.1);
            color: #60a5fa;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 600;
            border: 1px solid rgba(59, 130, 246, 0.2);
            margin-left: 20px;
        }
        
        /* 3. Sidebar Styling */
        [data-testid="stSidebar"] {
            background-color: #f8fafc;
            border-right: 1px solid #e2e8f0;
            padding-top: 20px;
        }
        
        /* 4. Kontener Treści */
        .main .block-container {
            padding-top: 80px;
            max-width: 1200px;
        }
        
        /* 5. Custom Sidebar Menu */
        .stRadio [data-testid="stWidgetLabel"] {
            display: none;
        }
    </style>
    """, unsafe_allow_html=True)

def render_top_bar(project_name, user_role, user_name):
    """Renderuje pływający pasek górny."""
    if not user_name:
        user_name = "Użytkownik"
    role_emoji = "👤" if user_role == "Inwestor" else "👷"
    st.markdown(f"""
    <div class="main-header">
        <div style="display: flex; align-items: center;">
            <div class="logo-text">RemontIQ</div>
            <div class="project-badge">📍 {project_name}</div>
        </div>
        <div style="display: flex; align-items: center; gap: 20px;">
            <div style="text-align: right;">
                <div style="font-size: 13px; font-weight: 700;">{user_name}</div>
                <div style="font-size: 11px; color: #94a3b8;">{role_emoji} {user_role}</div>
            </div>
            <div style="width: 35px; height: 35px; background: #3b82f6; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold;">
                {user_name[0].upper()}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Inicjalizacja stylu
apply_saas_theme()

@st.cache_resource
def get_supabase() -> Client:
    from services.supabase_client import get_supabase_client
    return get_supabase_client()

try:
    supabase = get_supabase()
except Exception as e:
    st.error("Błąd połączenia z Supabase.")
    st.code(f"{type(e).__name__}: {str(e)}")
    st.info(
        "Sprawdź w Streamlit Cloud → Settings → Secrets, czy ustawiono "
        "SUPABASE_URL oraz SUPABASE_SERVICE_ROLE_KEY."
    )
    st.stop()

# ============================================================================
# IMPORTY SERWISÓW (Sprint 24 - Plan Remontu 2.0)
# ============================================================================

from services.phase_service import PhaseService
from services.negotiation_service import NegotiationService
from services.task_service import TaskService
from services.change_service import ChangeService
from services.timeline_service import TimelineService
from services.ordering_service import OrderingService

from components.progress_dashboard import render_project_progress_dashboard

# ZAWSZE ŚWIEŻE INSTANCJE (naprawia problem starych błędów zostających w pamięci po aktualizacji GitHuba)
task_service = TaskService(supabase)
ordering_service = OrderingService(supabase, task_service)
negotiation_service = NegotiationService(supabase, task_service=task_service)
phase_service = PhaseService(supabase)
timeline_service = TimelineService(
    supabase, 
    task_service=task_service, 
    negotiation_service=negotiation_service
)
change_service = ChangeService(supabase)

# Nadpisujemy w session_state dla kompatybilności wstecznej modułów, które tam szukają
st.session_state.task_service = task_service
st.session_state.ordering_service = ordering_service
st.session_state.negotiation_service = negotiation_service
st.session_state.phase_service = phase_service
st.session_state.timeline_service = timeline_service
st.session_state.change_service = change_service

# Importy nowych paneli (Sprint 24)
from panels.crew_panel import render_crew_panel
from panels.investor_panel import render_investor_panel
import importlib
import components.chat_component
importlib.reload(components.chat_component)
from components.chat_component import render_chat_component

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

def calculate_quality_score(tasks_accepted: int, total_tasks: int, blockers: int, delay_days: int) -> dict:
    """Algorytm Enterprise Quality Score (65/25/10)"""
    if total_tasks <= 0:
        return {"score": 0, "risk": "CRITICAL", "breakdown": {"acceptance": 0, "schedule": 0, "blockers": 0}}
    
    acc_score = (tasks_accepted / total_tasks) * 100
    sched_score = max(0, 100 - delay_days * 7)
    block_score = max(0, 100 - blockers * 20)
    
    final_score = round(0.65 * acc_score + 0.25 * sched_score + 0.10 * block_score)
    risk = "LOW" if final_score >= 85 else "MEDIUM" if final_score >= 70 else "HIGH" if final_score >= 50 else "CRITICAL"
    
    return {
        "score": final_score,
        "risk": risk,
        "breakdown": {"acceptance": round(acc_score), "schedule": round(sched_score), "blockers": round(block_score)}
    }

# --- STATUSY NEGOCJACYJNE (Handshake Workflow) ---
TASK_STATUSES = {
    "DRAFT": "📝 Szkic",
    "TO_BE_VALUED": "❓ Do wyceny (Szef Ekipy)",
    "PROPOSED_BY_CREW": "👷 Propozycja Szefa Ekipy",
    "CHANGES_REQUESTED": "✏️ Korekta Inwestora",
    "ACCEPTED_LOCKED": "🔒 Zaakceptowane",
    "ACTIVE": "🚀 W realizacji",
    "DONE": "✅ Zakończone"
}

def parse_handshake_data(description):
    """Wyciąga dane negocjacyjne z tekstu opisu w sposób odporny na błędy."""
    data = {"commercial": "PENDING", "execution": "NOT_READY", "price": 0.0, "comment": ""}
    if not description or "--- DANE NEGOCJACYJNE ---" not in description:
        return data
    try:
        header_part = description.split("--- DANE NEGOCJACYJNE ---")[1].split("------------------------")[0]
        for line in header_part.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip().upper()
                val = val.strip()
                if key == "COMMERCIAL": data["commercial"] = val
                if key == "EXECUTION": data["execution"] = val
                if key in ["CENA", "LOCKED_PRICE", "CENA_KAROLA"]: 
                    try: data["price"] = float(val)
                    except: pass
                if key == "LAST_COMMENT": data["comment"] = val
    except: pass
    return data

def validate_project_budget(project_id, new_task_price):
    """Sprawdza, czy dodanie tej kwoty mieści się w budżecie projektu."""
    try:
        p_meta = supabase.table("project_metadata").select("total_budget").eq("id", project_id).single().execute().data
        if not p_meta: return True, "Brak zdefiniowanego budżetu"
        
        budget = float(p_meta.get('total_budget', 0))
        # Sumujemy tylko ZABLOKOWANE zadania
        all_t = supabase.table("tasks").select("description").eq("project_id", project_id).execute().data or []
        locked_sum = 0
        for t in all_t:
            h = parse_handshake_data(t.get('description', ''))
            if h['commercial'] == "ACCEPTED_LOCKED":
                locked_sum += h['price']
        
        remaining = budget - locked_sum
        if new_task_price > remaining:
            return False, f"⚠️ PRZEKROCZENIE BUDŻETU! Dostępne: {remaining:,.2f} PLN, Próba: {new_task_price:,.2f} PLN"
        
        if (locked_sum + new_task_price) > (budget * 0.9):
            return True, f"🟡 Ostrzeżenie: Wykorzystasz {(locked_sum + new_task_price)/budget*100:.1f}% budżetu!"
            
        return True, "✅ OK"
    except:
        return True, "Nie udało się zweryfikować budżetu"

def process_task_handshake(task_id, action, actor_role, price=None, comment=""):
    """Obsługuje zaawansowany Handshake z walidacją reguł biznesowych."""
    try:
        t = supabase.table("tasks").select("*").eq("id", task_id).single().execute().data
        desc = t.get('description', '') or ''
        current = parse_handshake_data(desc)
        
        # ZABEZPIECZENIE: Nie pozwól zmieniać zablokowanych finansowo zadań bez aneksowania
        if current['commercial'] == "ACCEPTED_LOCKED" and action != "REJECT":
            st.error("To zadanie jest już zablokowane finansowo. Zmiany wymagają aneksowania.")
            return False

        # Maszyna stanów
        c_status, e_status, l_price = current['commercial'], current['execution'], price or current['price']
        
        if action == "SUBMIT_VALUATION":
            c_status, e_status = "PROPOSED_BY_CREW", "NOT_READY"
        elif action in ["ACCEPT", "LOCK_OFFLINE"]:
            # Walidacja budżetu przed akceptacją
            ok, msg = validate_project_budget(t['project_id'], l_price)
            if not ok:
                st.error(msg)
                return False
            c_status, e_status = "ACCEPTED_LOCKED", "TODO"
        elif action == "COUNTER_OFFER":
            c_status, e_status = "INVESTOR_COUNTERED", "NOT_READY"

        meta_tag = f"--- DANE NEGOCJACYJNE ---\nCOMMERCIAL: {c_status}\nEXECUTION: {e_status}\nLOCKED_PRICE: {l_price}\nLAST_COMMENT: {comment}\n------------------------\n\n"
        if "--- DANE NEGOCJACYJNE ---" in desc:
            desc = desc.split("------------------------")[-1].strip()
        
        update_data = {"description": meta_tag + desc, "updated_at": datetime.now().isoformat()}
        if c_status == "ACCEPTED_LOCKED": update_data["kanban_status"] = "TODO"

        supabase.table("tasks").update(update_data).eq("id", task_id).execute()
        add_activity_log(actor_role, f"HANDSHAKE_{action}", "FINANCIAL", f"Zadanie {task_id}: {l_price} PLN")
        return True
    except Exception as e:
        st.error(f"Błąd Handshake 2.1: {e}")
        return False

def enforce_project_access_invariant():
    """Wymusza autoryzację projektu po zalogowaniu. Zapobiega zmianie projektu przez ekipę."""
    role = st.session_state.get("role")
    
    if role == "crew":
        authorized_id = st.session_state.get("crew_authorized_project_id")
        current_id = st.session_state.get("current_project_id")
        verified = st.session_state.get("crew_project_access_verified")
        
        if not verified or not authorized_id:
            render_crew_login_gate()
            st.stop()
            
        if current_id != authorized_id:
            st.session_state["current_project_id"] = authorized_id
            st.warning("Dostęp ekipy jest ograniczony do remontu przypisanego kodem.")
            st.rerun()
            
    if role == "investor":
        pass

def set_current_project_id(project_id: str, source: str = ""):
    """Bezpieczny setter dla current_project_id sprawdzający uprawnienia."""
    role = st.session_state.get("role")
    
    if role == "crew":
        authorized_id = st.session_state.get("crew_authorized_project_id")
        if project_id != authorized_id:
            st.error("Brak dostępu do tego remontu.")
            st.stop()
            
    if role == "investor":
        user_id = st.session_state.get("user_id")
        if not user_id:
            st.error("Brak identyfikatora inwestora.")
            st.stop()
            
        # Sprawdzamy czy projekt należy do inwestora
        res = supabase.table("project_metadata").select("id").eq("id", project_id).eq("user_id", user_id).limit(1).execute()
        if not res.data:
            st.error("Brak dostępu do tego remontu.")
            st.stop()
            
    st.session_state["current_project_id"] = project_id

def get_project_metadata():
    try:
        if st.session_state.get("role") == "crew":
            # Ekipa ma zablokowany dostęp do jednego konkretnego projektu
            auth_id = st.session_state.get("crew_authorized_project_id")
            if not auth_id: return None
            res = supabase.table("project_metadata").select("*").eq("id", auth_id).execute()
            return res.data[0] if res.data else None
            
        elif st.session_state.get("role") == "investor":
            query = supabase.table("project_metadata").select("*")
            user_id = st.session_state.get("user_id", "00000000-0000-0000-0000-000000000001")
            
            if st.session_state.get("current_project_id"):
                query = query.eq("id", st.session_state["current_project_id"]).eq("user_id", user_id)
            else:
                query = query.eq("user_id", user_id).order("created_at", desc=True).limit(1)
                
            res = query.execute()
            
            if res.data and not st.session_state.get("current_project_id"):
                set_current_project_id(res.data[0]["id"], "get_project_metadata_fallback")
                
            return res.data[0] if res.data else None
        else:
            return None
    except Exception as e:
        st.error(f"❌ Błąd pobierania metadanych: {e}")
        return None

def create_project_metadata(**kwargs):
    """
    Tworzy nowy projekt i automatycznie przypisuje go do zalogowanego użytkownika.
    
    ✅ SECURE: Automatyczne przypisanie user_id
    ✅ AUDIT: Logowanie każdego projektu
    ✅ SAFE: Error handling z backupem danych
    """
    try:
        # ============================================================
        # KROK 1: SECURITY – Automatyczne przypisanie właściciela
        # ============================================================
        if "user_id" not in kwargs:
            if "user_id" in st.session_state:
                kwargs["user_id"] = st.session_state.user_id
            else:
                st.error("❌ Nie jesteś zalogowany.")
                return None
        
        # ============================================================
        # KROK 2: Formatowanie dat (z zachowaniem nazw pól!)
        # ============================================================
        from datetime import date
        if 'planned_start_date' in kwargs and isinstance(kwargs['planned_start_date'], date):
            kwargs['planned_start_date'] = kwargs['planned_start_date'].isoformat()
        
        if 'planned_end_date' in kwargs and isinstance(kwargs['planned_end_date'], date):
            kwargs['planned_end_date'] = kwargs['planned_end_date'].isoformat()
        
        # ============================================================
        # KROK 3: AUDIT – Logowanie
        # ============================================================
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Creating project for user {kwargs['user_id']}")
        
        # ============================================================
        # KROK 4: Wstawienie do bazy
        # ============================================================
        result = supabase.table("project_metadata").insert(kwargs).execute()
        
        if result.data and len(result.data) > 0:
            project_id = result.data[0]['id']
            logger.info(f"✅ Project created successfully: {project_id}")
            # Generowanie kodu ekipy (Gatekeeper)
            from services.access_service import create_crew_access_code
            crew_code = create_crew_access_code(project_id, supabase)
            st.session_state["last_generated_crew_code"] = crew_code
            
            return result
        else:
            st.error("❌ Projekt nie został utworzony (brak danych w odpowiedzi).")
            return None
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"❌ Error creating project: {str(e)}")
        st.error(f"❌ Błąd tworzenia projektu: {e}")
        st.info("💡 Możliwe przyczyny:\n- Brak kolumny `user_id` w tabeli\n- Wyłączone RLS\n- Brak uprawnień do wstawiania")
        return None

def update_project_metadata(project_id, **kwargs):
    try:
        if 'actual_start_date' in kwargs and isinstance(kwargs['actual_start_date'], date):
            kwargs['actual_start_date'] = kwargs['actual_start_date'].isoformat()
        if 'actual_end_date' in kwargs and isinstance(kwargs['actual_end_date'], date):
            kwargs['actual_end_date'] = kwargs['actual_end_date'].isoformat()
        return supabase.table("project_metadata").update(kwargs).eq("id", project_id).execute()
    except Exception as e:
        st.error(f"❌ Błąd aktualizacji projektu: {e}")
        return None

# ============================================
# SPRINT 15: KONSTRUKCJA KANONICZNA
# ============================================

TASK_STATUSES = {
    "TODO": "TODO",
    "IN_PROGRESS": "IN_PROGRESS",
    "AWAITING_INSPECTION": "AWAITING_INSPECTION",
    "DONE": "DONE"
}

def add_activity_log(author_name: str, action: str, task_id: str = None, project_id: str = None, details: str = ""):
    try:
        supabase.table("activity_log").insert({
            "author_name": author_name, "action": action, "task_id": task_id, "project_id": project_id, "details": details
        }).execute()
        return True
    except: return False

def start_task_timer_v2(task_id: str, crew_member_id: str):
    work_date = date.today().isoformat()
    try:
        supabase.table("tasks").update({"kanban_status": TASK_STATUSES["IN_PROGRESS"]}).eq("id", task_id).execute()
        existing = supabase.table("time_tracking").select("*").eq("task_id", task_id).eq("crew_member_id", crew_member_id).eq("work_date", work_date).execute()
        if existing.data:
            supabase.table("time_tracking").update({"start_time": datetime.now().time().isoformat()}).eq("id", existing.data[0]['id']).execute()
        else:
            supabase.table("time_tracking").insert({"task_id": task_id, "crew_member_id": crew_member_id, "work_date": work_date, "start_time": datetime.now().time().isoformat()}).execute()
        add_activity_log(st.session_state.get("user_name", "Szef Ekipy"), "task_started", task_id, details="▶️ Rozpoczęto pracę")
        return True
    except Exception as e:
        st.error(f"❌ Błąd start: {e}")
        return False

def stop_task_timer_v2(task_id: str, crew_member_id: str):
    work_date = date.today().isoformat()
    try:
        res = supabase.table("time_tracking").select("*").eq("task_id", task_id).eq("crew_member_id", crew_member_id).eq("work_date", work_date).execute()
        if res.data:
            t = res.data[0]
            start_dt = datetime.combine(date.today(), datetime.strptime(t['start_time'], "%H:%M:%S" if '.' not in t['start_time'] else "%H:%M:%S.%f").time())
            end_dt = datetime.now()
            if end_dt < start_dt: start_dt -= timedelta(days=1)
            dur = (end_dt - start_dt).total_seconds() / 3600
            supabase.table("time_tracking").update({"end_time": end_dt.time().isoformat(), "duration_hours": round(dur, 2)}).eq("id", t['id']).execute()
            add_activity_log(st.session_state.get("user_name", "Szef Ekipy"), "task_paused", task_id, details=f"⏸️ Pauza ({round(dur, 2)}h)")
            return {"success": True, "duration_hours": round(dur, 2)}
        return {"success": False}
    except Exception as e:
        st.error(f"❌ Błąd stop: {e}")
        return {"success": False}

def complete_task_v2(task_id: str, crew_member_id: str):
    try:
        stop_task_timer_v2(task_id, crew_member_id)
        supabase.table("tasks").update({"kanban_status": TASK_STATUSES["AWAITING_INSPECTION"]}).eq("id", task_id).execute()
        add_activity_log(st.session_state.get("user_name", "Szef Ekipy"), "task_completed", task_id, details="✅ Gotowe do odbioru")
        return True
    except: return False

def calculate_weekly_bonus_v2(project_id: str, crew_member_id: str):
    """Oblicza aktualną pensję i bonus dla Szefa Ekipy w bieżącym tygodniu."""
    try:
        # 1. Pobierz dane z weekly_payroll (jeśli istnieją)
        res = supabase.table("weekly_payroll").select("*").eq("project_id", project_id).eq("crew_member_id", crew_member_id).order("week_start_date", desc=True).limit(1).execute()
        
        if res.data:
            p = res.data[0]
            return {
                "base": float(p['base_weekly_salary']),
                "quality": float(p['quality_percentage']),
                "bonus_pct": float(p['quality_percentage']), # Uproszczone mapowanie
                "bonus_amt": float(p['bonus_amount'])
            }
        
        # 2. Jeśli brak wpisu, zwróć wartości domyślne (Gwarantowane 2000 PLN)
        return {
            "base": 2000.0,
            "quality": 0.0,
            "bonus_pct": 0.0,
            "bonus_amt": 0.0
        }
    except:
        return {"base": 2000.0, "quality": 0.0, "bonus_pct": 0.0, "bonus_amt": 0.0}

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

TASK_COMPLETED_STATUSES = {"DONE", "COMPLETED", "ARCHIVED"}

def get_task_progress_status(task):
    if not isinstance(task, dict):
        return ""
    return str(
        task.get("kanban_status")
        or task.get("completion_status")
        or task.get("status")
        or ""
    ).upper()

def is_task_completed_for_progress(task):
    return get_task_progress_status(task) in TASK_COMPLETED_STATUSES


def render_plan_and_progress_view(project_meta, phase_service, viewer_role="investor"):
    p_id = project_meta.get('id') if project_meta else None
    if not p_id:
        st.warning("Najpierw skonfiguruj projekt.")
        return
        
    # Tytuł i opis zależnie od roli
    if viewer_role == "investor":
        st.title("📋 Plan & Postęp Remontu")
        st.caption("Podgląd struktury prac, postępu w pomieszczeniach oraz szczegółów zadań z wycenami.")
    else:
        st.title("📋 Plan prac i postęp remontu")
        st.caption("Podgląd wykonania prac w pomieszczeniach oraz statusów zadań.")
        
    render_project_progress_dashboard(
        supabase=supabase,
        project_id=p_id,
        phase_service=phase_service,
        is_task_completed_for_progress=is_task_completed_for_progress,
        get_project_days_info=lambda: get_project_days_info(project_meta) if project_meta and project_meta.get('planned_start_date') and project_meta.get('planned_end_date') else None,
        viewer_role=viewer_role
    )


def report_blocker(task_id, description, blocker_type="OTHER"):
    """Zapisuje powód, status przed blokadą i blokuje zadanie."""
    try:
        # Pobierz dane zadania przed blokadą
        task_data = supabase.table("tasks").select("kanban_status, name").eq("id", task_id).execute().data[0]
        old_status = task_data['kanban_status']
        
        blocker_data = {
            "task_id": task_id, "blocker_type": blocker_type, "description": description,
            "reported_by": st.session_state.get("user_name", "Szef Ekipy"), "reported_at": datetime.now().isoformat(), "is_resolved": False
        }
        supabase.table("task_blockers").insert(blocker_data).execute()
        
        # Zapamiętaj status i zablokuj
        supabase.table("tasks").update({
            "is_blocked": True,
            "blocker_reason": description,
            "status_before_block": old_status
        }).eq("id", task_id).execute()
        
        log_activity(st.session_state.get("user_name", "Szef Ekipy"), "blocker_reported", task_id, f"Blokada: {description}")
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
        project_meta = get_project_metadata()
        if not project_meta: return {"total": 0, "in_progress": 0, "blocked": 0, "completed": 0, "awaiting": 0, "days_to_end": 0}
        
        response = supabase.table("tasks").select("*").eq("project_id", project_meta['id']).execute()
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

# --- WARSTWA KOMPATYBILNOŚCI STATUSÓW DLA CREW_REQUESTS ---
REQUEST_STATUS_NEW = "NEW"
REQUEST_STATUS_CONFIRMED = "CONFIRMED"
REQUEST_STATUS_DELIVERED = "DELIVERED"
REQUEST_STATUS_CANCELLED = "CANCELLED"

REQUEST_STATUS_LABELS = {
    "NEW": "Nowe ⏳",
    "Nowe": "Nowe ⏳",
    "CONFIRMED": "Potwierdzone 📦",
    "Potwierdzone": "Potwierdzone 📦",
    "DELIVERED": "Dostarczone ✅",
    "Dostarczone": "Dostarczone ✅",
    "CANCELLED": "Anulowane ❌",
    "Anulowane": "Anulowane ❌",
}

OPEN_REQUEST_STATUSES = ["NEW", "Nowe", "CONFIRMED", "Potwierdzone"]
CLOSED_REQUEST_STATUSES = ["DELIVERED", "Dostarczone", "CANCELLED", "Anulowane"]

def get_crew_requests_grouped():
    """Zwróć zgłoszenia ekipy pogrupowane po statusie."""
    try:
        response = supabase.table("crew_requests").select("*").eq("project_id", p_id_global).order("created_at", desc=True).execute()
        requests = response.data or []
        grouped = {"Nowe": [], "Potwierdzone": [], "Dostarczone": [], "Anulowane": []}
        for req in requests:
            s = str(req.get("status", "NEW")).upper()
            if s in ["NEW", "NOWE"]:
                grouped["Nowe"].append(req)
            elif s in ["CONFIRMED", "POTWIERDZONE"]:
                grouped["Potwierdzone"].append(req)
            elif s in ["DELIVERED", "DOSTARCZONE"]:
                grouped["Dostarczone"].append(req)
            elif s in ["CANCELLED", "ANULOWANE"]:
                grouped["Anulowane"].append(req)
            else:
                grouped["Nowe"].append(req)
        return grouped
    except Exception:
        return {"Nowe": [], "Potwierdzone": [], "Dostarczone": [], "Anulowane": []}

def confirm_crew_request(request_id, investor_note="", expected_delivery_date=None):
    """Inwestor potwierdza: 'Wiem, zajmuję się tym'."""
    payload = {
        "status": REQUEST_STATUS_CONFIRMED,
        "investor_note": investor_note
    }
    if expected_delivery_date:
        payload["expected_delivery_date"] = expected_delivery_date.isoformat() if hasattr(expected_delivery_date, 'isoformat') else str(expected_delivery_date)
    supabase.table("crew_requests").update(payload).eq("id", request_id).execute()
    return {"status": "ok"}

def mark_crew_request_delivered(request_id):
    """Inwestor potwierdza dostawę: 'Materiał jest na budowie'."""
    req_resp = supabase.table("crew_requests").select("id, task_id, title, is_blocker").eq("id", request_id).execute()
    if not req_resp.data:
        return {"status": "error", "message": "Zgłoszenie nie zostało znalezione."}
    
    req = req_resp.data[0]
    task_id = req.get("task_id")
    is_blocker = req.get("is_blocker")
    
    supabase.table("crew_requests").update({
        "status": REQUEST_STATUS_DELIVERED
    }).eq("id", request_id).execute()
    
    if task_id and is_blocker:
        # Sprawdź, czy są jeszcze INNE aktywne zgłoszenia blokujące dla tego samego zadania
        other_resp = supabase.table("crew_requests").select("id").eq("task_id", task_id).eq("is_blocker", True).in_("status", OPEN_REQUEST_STATUSES).neq("id", request_id).execute()
        
        if not (other_resp.data and len(other_resp.data) > 0):
            supabase.table("task_blockers").update({
                "is_resolved": True,
                "resolved_at": datetime.now().isoformat(),
                "resolution_note": "Materiał dostarczony / zgłoszenie zamknięte"
            }).eq("task_id", task_id).eq("blocker_type", "MISSING_MATERIAL").eq("is_resolved", False).execute()
            
            # Sprawdź, czy zostały jakiekolwiek nierozwiązane blokery dla tego zadania
            remaining = supabase.table("task_blockers").select("id").eq("task_id", task_id).eq("is_resolved", False).execute()
            if not (remaining.data and len(remaining.data) > 0):
                supabase.table("tasks").update({
                    "is_blocked": False,
                    "blocker_reason": None,
                    "status_before_block": None
                }).eq("id", task_id).execute()
                
    return {"status": "ok"}

def cancel_crew_request(request_id):
    """Inwestor anuluje zgłoszenie — odblokuj powiązane zadanie."""
    req_resp = supabase.table("crew_requests").select("id, task_id, title, is_blocker").eq("id", request_id).execute()
    if not req_resp.data:
        return {"status": "error", "message": "Zgłoszenie nie zostało znalezione."}
    
    req = req_resp.data[0]
    task_id = req.get("task_id")
    is_blocker = req.get("is_blocker")
    
    supabase.table("crew_requests").update({
        "status": REQUEST_STATUS_CANCELLED
    }).eq("id", request_id).execute()
    
    if task_id and is_blocker:
        # Sprawdź, czy są jeszcze INNE aktywne zgłoszenia blokujące dla tego samego zadania
        other_resp = supabase.table("crew_requests").select("id").eq("task_id", task_id).eq("is_blocker", True).in_("status", OPEN_REQUEST_STATUSES).neq("id", request_id).execute()
        
        if not (other_resp.data and len(other_resp.data) > 0):
            supabase.table("task_blockers").update({
                "is_resolved": True,
                "resolved_at": datetime.now().isoformat(),
                "resolution_note": "Zgłoszenie anulowane / zamknięte"
            }).eq("task_id", task_id).eq("blocker_type", "MISSING_MATERIAL").eq("is_resolved", False).execute()
            
            # Sprawdź, czy zostały jakiekolwiek nierozwiązane blokery dla tego zadania
            remaining = supabase.table("task_blockers").select("id").eq("task_id", task_id).eq("is_resolved", False).execute()
            if not (remaining.data and len(remaining.data) > 0):
                supabase.table("tasks").update({
                    "is_blocked": False,
                    "blocker_reason": None,
                    "status_before_block": None
                }).eq("id", task_id).execute()
                
    return {"status": "ok"}

def submit_crew_request_with_blocker(title, needed_by, is_blocker, project_id, task_id=None, reported_by="Ekipa"):
    """Zgłasza potrzebę — jeśli pilne, auto-blokuje zadanie i zapisuje jego status oraz autora."""
    if is_blocker and not task_id:
        raise ValueError("Zadanie (task_id) jest wymagane w przypadku zgłoszenia blokującego.")
        
    payload = {
        "title": title,
        "needed_by": str(needed_by),
        "is_blocker": is_blocker,
        "status": REQUEST_STATUS_NEW,
        "task_id": task_id,
        "project_id": project_id
    }
    supabase.table("crew_requests").insert(payload).execute()
    
    if task_id and is_blocker:
        t_resp = supabase.table("tasks").select("id, name, kanban_status, is_blocked, status_before_block").eq("id", task_id).execute()
        if not t_resp.data:
            return {"status": "error", "message": f"Zadanie o ID {task_id} nie zostało znalezione."}
            
        t_data = t_resp.data[0]
        old_status = t_data.get('kanban_status') or "IN_PROGRESS"
        current_is_blocked = t_data.get('is_blocked')
        current_status_before_block = t_data.get('status_before_block')
        
        new_status_before = current_status_before_block if (current_is_blocked and current_status_before_block) else old_status
        
        supabase.table("tasks").update({
            "is_blocked": True, 
            "blocker_reason": f"Brak: {title}", 
            "status_before_block": new_status_before
        }).eq("id", task_id).execute()
        
        supabase.table("task_blockers").insert({
            "task_id": task_id,
            "blocker_type": "MISSING_MATERIAL", 
            "description": f"Zgłoszono brak: {title}",
            "reported_by": reported_by,
            "is_resolved": False
        }).execute()
        
    return {"status": "ok"}


def get_request_next_action_label(status):
    """Zwraca czytelny dla obu stron status kolejnego kroku w procesie."""
    if status in ["NEW", "Nowe"]:
        return "⏳ Ruch Inwestora — czeka na reakcję i potwierdzenie"
    if status in ["CONFIRMED", "Potwierdzone"]:
        return "📦 Inwestor potwierdził — oczekiwanie na dostawę/rozwiązanie"
    if status in ["DELIVERED", "Dostarczone"]:
        return "✅ Sprawa zamknięta — dostarczone/rozwiązane"
    if status in ["CANCELLED", "Anulowane"]:
        return "❌ Anulowane przez Inwestora"
    return "ℹ️ Status wymaga sprawdzenia"


def render_crew_blockers_materials_panel():
    """Renderuje nowoczesny, funkcjonalny panel zgłoszeń blokad i zapotrzebowań materiałowych dla ekipy."""
    st.title("🚨 Blokady i Materiały")
    st.caption("Zgłaszaj braki materiałowe i blokady pracy. Inwestor otrzyma natychmiastowe powiadomienie.")
    
    with st.expander("Jak działa ten panel? (Przepływ zgłoszeń i blokad)", expanded=False):
        st.info("""
        **System automatycznego rozwiązywania blokad budowy:**
        1. **Ekipa zgłasza brak materiału lub problem organizacyjny.** Zaznaczenie czerwonego checkboxa *PILNE* powiąże zgłoszenie z wybranym zadaniem i automatycznie zablokuje je w Kanbanie dla obu stron.
        2. **Inwestor potwierdza w swoim panelu, że zajmuje się sprawą** (może podać szacowany czas dostawy/rozwiązania i napisać notatkę).
        3. **Po dostarczeniu lub rozwiązaniu Inwestor zamyka zgłoszenie.**
        4. **Zadanie zostaje automatycznie odblokowane** w Kanbanie, gdy wszystkie powiązane z nim zgłoszenia zostaną oznaczone jako dostarczone/rozwiązane!
        """)
    
    # ==================================================
    # 1. 🔴 Aktywne blokady pracy
    # ==================================================
    st.markdown("## 🔴 Aktywne blokady pracy")
    
    try:
        tasks_resp = supabase.table("tasks").select("id, name, kanban_status, is_blocked, blocker_reason, status_before_block").eq("is_blocked", True).execute()
        blocked_tasks = tasks_resp.data or []
    except Exception as e:
        st.error(f"Błąd podczas pobierania zablokowanych zadań: {e}")
        blocked_tasks = []
        
    if blocked_tasks:
        for task in blocked_tasks:
            task_id = task.get("id")
            task_name = task.get("name") or "Zadanie bez nazwy"
            kanban_status = task.get("kanban_status") or "Nieznany"
            blocker_reason = task.get("blocker_reason") or "Brak podanego powodu"
            
            # Pobierz aktywne zgłoszenia materiałowe powiązane z tym zadaniem
            try:
                reqs_resp = supabase.table("crew_requests").select("*").eq("task_id", task_id).in_("status", OPEN_REQUEST_STATUSES).execute()
                active_reqs = reqs_resp.data or []
            except Exception:
                active_reqs = []
                
            with st.container(border=True):
                st.markdown(f"### 🚧 {task_name}")
                st.error(f"**Powód wstrzymania:** {blocker_reason}")
                st.caption(f"Status zadania w Kanbanie: `{kanban_status}`")
                
                if active_reqs:
                    st.markdown("**🔗 Powiązane zgłoszenia materiałowe:**")
                    for req in active_reqs:
                        status_label = REQUEST_STATUS_LABELS.get(req.get("status"), req.get("status", "Nieznany"))
                        needed_by = req.get("needed_by") or "—"
                        next_action = get_request_next_action_label(req.get("status"))
                        st.markdown(f"• **{req.get('title')}** (Status: *{status_label}* | Potrzebne do: *{needed_by}*)")
                        st.caption(f"  ↳ *Kolejny krok: {next_action}*")
                        if req.get("investor_note"):
                            st.info(f"📝 **Notatka inwestora:** {req['investor_note']}")
                        if req.get("expected_delivery_date"):
                            st.success(f"📅 **Planowana dostawa:** {req['expected_delivery_date']}")
                else:
                    st.info("Brak aktywnych zgłoszeń materiałowych bezpośrednio powiązanych z tą blokadą.")
    else:
        st.success("✅ Brak aktywnych blokad. Można pracować dalej!")
        
    st.divider()
    
    # ==================================================
    # 2. ➕ Nowe zgłoszenie braku / problemu
    # ==================================================
    st.markdown("## ➕ Nowe zgłoszenie braku / problemu")
    
    try:
        tasks_to_link_resp = supabase.table("tasks").select("id, name, kanban_status, is_blocked").in_("kanban_status", ["TODO", "IN_PROGRESS"]).execute()
        active_tasks = tasks_to_link_resp.data or []
    except Exception:
        active_tasks = []
        
    # Sformatuj opcje dla selectboxa
    task_options = [("no_task", "Brak powiązanego zadania / ogólne zgłoszenie")]
    for t in active_tasks:
        name = t.get("name") or "Zadanie bez nazwy"
        status = t.get("kanban_status") or "TODO"
        is_b = " (ZABLOKOWANE)" if t.get("is_blocked") else ""
        task_options.append((t["id"], f"{name} [{status}]{is_b}"))
        
    with st.form("crew_request_form", clear_on_submit=True):
        title = st.text_input("Nazwa materiału / problemu *", placeholder="np. Brak kabla YDYp 3x2.5")
        needed_by = st.date_input("Kiedy jest potrzebne?", value=date.today() + timedelta(days=1))
        
        selected_task_idx = st.selectbox(
            "Powiązane zadanie",
            options=range(len(task_options)),
            format_func=lambda idx: task_options[idx][1]
        )
        selected_task_id = task_options[selected_task_idx][0]
        
        is_blocker = st.checkbox("🚨 To blokuje moją pracę teraz (PILNE)")
        
        submit_btn = st.form_submit_button("Wyślij zgłoszenie", type="primary")
        
        if submit_btn:
            if not title.strip():
                st.error("Błąd: Nazwa materiału/problemu jest wymagana.")
            elif is_blocker and selected_task_id == "no_task":
                st.error("Błąd: Aby zgłosić zgłoszenie jako PILNE (blokujące), musisz powiązać je z konkretnym zadaniem.")
            else:
                task_id_param = None if selected_task_id == "no_task" else selected_task_id
                user_name = st.session_state.get('user_name', 'Ekipa')
                try:
                    res = submit_crew_request_with_blocker(
                        title=title.strip(),
                        needed_by=needed_by,
                        is_blocker=is_blocker,
                        project_id=p_id_global,
                        task_id=task_id_param,
                        reported_by=user_name
                    )
                    if res.get("status") == "ok":
                        if is_blocker:
                            st.success("🎉 Zgłoszenie wysłane do Inwestora. Powiązane zadanie zostało oznaczone jako zablokowane do czasu dostawy/rozwiązania.")
                        else:
                            st.success("🎉 Zgłoszenie wysłane do Inwestora. Nie blokuje ono pracy w Kanbanie.")
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error(f"Błąd wysyłania zgłoszenia: {res.get('message', 'Nieznany błąd')}")
                except Exception as e:
                    st.error(f"Wystąpił błąd podczas wysyłania: {e}")
                    
    st.divider()
    
    # ==================================================
    # 3. 📜 Historia zgłoszonych spraw
    # ==================================================
    st.markdown("## 📜 Historia zgłoszonych spraw")
    
    try:
        reqs_resp = supabase.table("crew_requests").select("*").eq("project_id", p_id_global).order("created_at", desc=True).execute()
        all_reqs = reqs_resp.data or []
    except Exception as e:
        st.error(f"Błąd podczas pobierania historii zgłoszeń: {e}")
        all_reqs = []
        
    w_toku = [r for r in all_reqs if str(r.get("status", "")).upper() in ["NEW", "NOWE", "CONFIRMED", "POTWIERDZONE"]]
    dostarczone = [r for r in all_reqs if str(r.get("status", "")).upper() in ["DELIVERED", "DOSTARCZONE"]]
    anulowane = [r for r in all_reqs if str(r.get("status", "")).upper() in ["CANCELLED", "ANULOWANE"]]
    
    t1, t2, t3 = st.tabs(["⏳ W toku", "✅ Dostarczone", "❌ Anulowane"])
    
    def render_request_item(req):
        status_label = REQUEST_STATUS_LABELS.get(req.get("status"), req.get("status", "Nieznany"))
        needed_by = req.get("needed_by") or "—"
        created_at = req.get("created_at")
        created_at_str = created_at[:10] if created_at else "—"
        
        is_blocker = req.get("is_blocker", False)
        type_badge = "🚨 BLOKADA" if is_blocker else "📦 Logistyka"
        
        task_id = req.get("task_id")
        task_name_str = "Brak (ogólne)"
        if task_id:
            try:
                t_resp = supabase.table("tasks").select("name").eq("id", task_id).execute()
                if t_resp.data:
                    task_name_str = t_resp.data[0].get("name") or "Zadanie bez nazwy"
            except Exception:
                task_name_str = "Błąd pobierania nazwy zadania"
                
        with st.container(border=True):
            col_left, col_right = st.columns([3, 1])
            with col_left:
                st.markdown(f"#### {req.get('title')}")
                st.caption(f"Powiązane zadanie: **{task_name_str}**")
                st.write(f"📅 Potrzebne do: **{needed_by}** | Zgłoszono: **{created_at_str}**")
                if req.get("investor_note"):
                    st.info(f"📝 **Notatka Inwestora:** {req['investor_note']}")
                if req.get("expected_delivery_date"):
                    st.success(f"📅 **Szacowana dostawa:** {req['expected_delivery_date']}")
                next_action = get_request_next_action_label(req.get("status"))
                st.caption(f"↳ *Kolejny krok: {next_action}*")
            with col_right:
                st.markdown(f"**{status_label}**")
                if is_blocker:
                    st.error(type_badge)
                else:
                    st.info(type_badge)

    with t1:
        if w_toku:
            for req in w_toku:
                render_request_item(req)
        else:
            st.info("Brak zgłoszeń w toku.")
            
    with t2:
        if dostarczone:
            for req in dostarczone:
                render_request_item(req)
        else:
            st.info("Brak dostarczonych zgłoszeń.")
            
    with t3:
        if anulowane:
            for req in anulowane:
                render_request_item(req)
        else:
            st.info("Brak anulowanych zgłoszeń.")


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
        project_meta = get_project_metadata()
        if not project_meta: return []
        
        p_tasks = supabase.table("tasks").select("id").eq("project_id", project_meta['id']).execute().data or []
        task_ids = [t['id'] for t in p_tasks]
        if not task_ids: return []
        
        comments = supabase.table("task_comments").select("*").in_("task_id", task_ids).execute().data or []
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
    user_name = st.session_state.get("user_name") or ("Szef Ekipy" if role == "crew" else "Inwestor")
    
    with st.expander(f"💬 Chat ({len(comments)})"):
        render_whatsapp_chat(comments, user_name, task_id, context="kanban")
        render_chat_input(task_id, user_name, context="kanban")

def calculate_budget_forecast():
    """Oblicz prognozę wyczerpania budżetu."""
    try:
        meta = get_project_metadata()
        if not meta or not meta.get('planned_start_date'): return None
        
        total_budget = meta.get('total_budget', 0)
        expenses_df = read_table("expenses", filters={"project_id": meta['id'], "is_deleted": False})
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
        meta = get_project_metadata()
        if not meta: return {"score": 0, "status": "⚪ BRAK DANYCH", "metrics": {}, "details": {}}
        
        tasks = supabase.table("tasks").select("*").eq("project_id", meta['id']).execute().data or []
        if not tasks: return {"score": 0, "status": "⚪ BRAK DANYCH", "metrics": {}, "details": {}}
        
        completed_tasks = [t for t in tasks if is_task_completed_for_progress(t)]
        comp_count = len(completed_tasks)
        prog_score = (comp_count / len(tasks)) * 100
        
        # 2. HARMONOGRAM (25%)
        today = date.today()
        delays = []
        for t in tasks:
            if t.get('planned_end_date'):
                p_end = datetime.strptime(t['planned_end_date'], "%Y-%m-%d").date()
                if not is_task_completed_for_progress(t) and p_end < today:
                    delays.append((today - p_end).days)
        avg_delay = sum(delays)/len(delays) if delays else 0
        sched_score = 100 if avg_delay == 0 else (75 if avg_delay <= 3 else (50 if avg_delay <= 7 else 25))
        
        # 3. BUDŻET (25%)
        meta = get_project_metadata()
        total_b = meta.get('total_budget', 0) if meta else 0
        exp_df = read_table("expenses", filters={"project_id": meta['id'], "is_deleted": False})
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
        exp_df = read_table("expenses", filters={"project_id": meta['id'], "is_deleted": False})
        
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
        author_raw = c.get('author_name', 'Nieznany')
        is_me = (author_raw == current_user)
        author = html.escape(str(author_raw))
        bg = "#e0e0e0" if is_me else "#0084ff"
        txt = "#000" if is_me else "#fff"
        align = "flex-end" if is_me else "flex-start"
        margin = "30%" if is_me else "0"
        ts = c.get('created_at', '')[11:16]
        edit_tag = f" (edytowane {c['edit_count']}x)" if c.get('edit_count', 0) > 0 else ""
        content_esc = html.escape(str(c.get('content') or ''))
        
        st.markdown(f"""
        <div style="display: flex; justify-content: {align}; margin-bottom: 8px; margin-left: {margin};">
            <div style="background-color: {bg}; color: {txt}; padding: 12px 16px; border-radius: 18px; max-width: 85%; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="font-size: 11px; font-weight: bold; opacity: 0.8;">{author}</div>
                {content_esc}
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
                role = st.session_state.get("role", "crew")
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
    reqs = read_table("crew_requests", filters={"project_id": meta['id']})
    for _, row in reqs.iterrows():
        if row['status'] in ('Załatwione', 'Anulowane', 'Przekształcone w zadanie', 'DELIVERED', 'Dostarczone', 'CANCELLED'): continue
        score, reasons = 0, []
        needed_date = pd.to_datetime(row['needed_by']).date() if pd.notna(row['needed_by']) and row['needed_by'] else today
        days_left = (needed_date - today).days
        
        if row['is_blocker']: score += 200; reasons.append("BLOKUJE PRACĘ!")
        if days_left <= 1: score += 150; reasons.append("Na dzisiaj/jutro!")
        elif days_left <= 4: score += 100; reasons.append(f"Potrzebne za {days_left} dni")
        if score > 0: recs.append({"Typ": "🛠️ Ekipa", "Zadanie": row['title'], "Wynik": score, "Powód": " | ".join(reasons)})

    # --- 4. MATERIAŁY ---
    mats = read_table("materials", filters={"project_id": meta['id'], "is_deleted": False})
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
st.sidebar.caption(f"🚀 Wersja: {APP_VERSION}")

# ==========================================
# SPRINT 23 — HYBRID PAYMENT 50/100 (Ścieżka A+)
# ==========================================

# --- WARSTWA STATUSÓW PŁATNOŚCI (SPRINT 27) ---
PAYMENT_STATUS_SUBMITTED = "SUBMITTED"
PAYMENT_STATUS_APPROVED_BY_INVESTOR = "APPROVED_BY_INVESTOR"
PAYMENT_STATUS_PAID = "PAID"
PAYMENT_STATUS_REJECTED = "REJECTED"

PAYMENT_LEGACY_APPROVED = "APPROVED"

PAYMENT_OPEN_STATUSES = [
    PAYMENT_STATUS_SUBMITTED,
    PAYMENT_STATUS_APPROVED_BY_INVESTOR,
]

PAYMENT_CLOSED_STATUSES = [
    PAYMENT_STATUS_PAID,
    PAYMENT_LEGACY_APPROVED,
    PAYMENT_STATUS_REJECTED,
]

PAYMENT_STATUS_LABELS = {
    "SUBMITTED": "⏳ Czeka na decyzję inwestora",
    "APPROVED_BY_INVESTOR": "💰 Przelew zadeklarowany przez inwestora",
    "PAID": "✅ Rozliczone",
    "APPROVED": "✅ Rozliczone / stary status",
    "REJECTED": "❌ Odrzucone",
}

def get_payment_status_label(status):
    return PAYMENT_STATUS_LABELS.get(status, f"ℹ️ Nieznany status: {status}")

def get_payment_next_action_label(status):
    if status == PAYMENT_STATUS_SUBMITTED:
        return "Ruch Inwestora — wniosek czeka na akceptację albo odrzucenie."
    if status == PAYMENT_STATUS_APPROVED_BY_INVESTOR:
        return "Ruch Ekipy — po wpływie środków trzeba będzie potwierdzić odbiór."
    if status in [PAYMENT_STATUS_PAID, PAYMENT_LEGACY_APPROVED]:
        return "Zamknięte — rozliczenie zakończone."
    if status == PAYMENT_STATUS_REJECTED:
        return "Zamknięte — wniosek odrzucony przez Inwestora."
    return "Status wymaga sprawdzenia."

def get_payment_type_label(payment_type):
    if payment_type == "REIMBURSEMENT":
        return "🛒 Zwrot za materiały"
    if payment_type == "ADVANCE":
        return "💰 Zaliczka / wypłata 50/100"
    if payment_type == "FINAL":
        return "🏁 Rozliczenie końcowe"
    return f"💳 {payment_type or 'Wniosek finansowy'}"

def parse_pln_amount(raw_value):
    try:
        cleaned = str(raw_value).strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
        amount = float(cleaned)
        return amount, None
    except Exception:
        return None, "Wprowadź poprawną kwotę, np. 5000 albo 5000,00."

def parse_project_log_data(raw_data):
    if isinstance(raw_data, dict):
        return raw_data
    if isinstance(raw_data, str) and raw_data.strip():
        try:
            import json
            return json.loads(raw_data)
        except Exception:
            return {}
    return {}

PAYMENT_LOG_TYPE = "DECISION"

def is_payment_request_log(log):
    data = parse_project_log_data(log.get("data"))
    return bool(data.get("payment_type"))

# --- PIĄTKOWA ZALICZKA TYGODNIOWA HELPERY (SPRINT 27) ---
def get_secret_float(name, default=1000.0):
    try:
        return float(st.secrets.get(name, default))
    except Exception:
        return default

WEEKLY_CREW_ADVANCE_AMOUNT = get_secret_float("WEEKLY_CREW_ADVANCE_AMOUNT", 1000.0)

def get_current_week_key(today=None):
    from datetime import date, datetime
    if today is None:
        today = date.today()
    elif isinstance(today, datetime):
        today = today.date()
    year, week, weekday = today.isocalendar()
    return f"{year}-W{week:02d}"

def get_week_friday_date(today=None):
    from datetime import date, datetime, timedelta
    if today is None:
        today = date.today()
    elif isinstance(today, datetime):
        today = today.date()
    weekday = today.isocalendar()[2]
    friday = today + timedelta(days=(5 - weekday))
    return friday.strftime("%Y-%m-%d")

def is_weekly_advance_request(log):
    if not is_payment_request_log(log):
        return False
    data = parse_project_log_data(log.get("data"))
    return bool(data.get("weekly_advance")) or data.get("payment_subtype") == "WEEKLY_FRIDAY_ADVANCE"

def find_existing_weekly_advance(project_id, week_key):
    try:
        res = supabase.table("project_logs").select("*").eq("project_id", project_id).eq("type", PAYMENT_LOG_TYPE).execute()
        logs = res.data or []
        for log in logs:
            if not is_weekly_advance_request(log):
                continue
            data = parse_project_log_data(log.get("data"))
            if data.get("week_key") == week_key:
                if log.get("status") not in ["REJECTED", "CANCELLED"]:
                    return log
        return None
    except Exception:
        return None

def is_weekly_advance_agreement_log(log):
    if is_payment_request_log(log):
        return False
    data = parse_project_log_data(log.get("data"))
    return bool(data.get("weekly_advance_agreement")) or data.get("config_type") == "WEEKLY_ADVANCE_AGREEMENT"

def get_weekly_advance_agreement(project_id):
    try:
        res = supabase.table("project_logs")\
            .select("*")\
            .eq("project_id", project_id)\
            .eq("type", PAYMENT_LOG_TYPE)\
            .execute()
        logs = res.data or []
        agreements = []
        for log in logs:
            if not is_weekly_advance_agreement_log(log):
                continue
            if log.get("status") in ["CANCELLED", "SUPERSEDED", "REJECTED"]:
                continue
            agreements.append(log)
        
        if not agreements:
            return None
            
        def get_sort_key(log):
            data = parse_project_log_data(log.get("data"))
            return data.get("effective_from") or log.get("created_at") or ""
            
        agreements.sort(key=get_sort_key, reverse=True)
        latest = agreements[0]
        data = parse_project_log_data(latest.get("data"))
        
        return {
            "log_id": latest.get("id"),
            "agreed_weekly_amount": safe_float(data.get("agreed_weekly_amount")),
            "currency": data.get("currency") or "PLN",
            "effective_from": data.get("effective_from") or latest.get("created_at", "")[:10],
            "note": latest.get("description") or data.get("note") or "",
            "source": "PROJECT_AGREEMENT"
        }
    except Exception:
        return None

def get_weekly_advance_amount_for_project(project_id):
    agreement = get_weekly_advance_agreement(project_id)
    if agreement is not None:
        return {
            "amount": agreement["agreed_weekly_amount"],
            "source": "PROJECT_AGREEMENT",
            "agreement_log_id": agreement["log_id"],
            "currency": agreement["currency"],
            "effective_from": agreement["effective_from"],
            "note": agreement["note"]
        }
    return {
        "amount": WEEKLY_CREW_ADVANCE_AMOUNT,
        "source": "GLOBAL_FALLBACK",
        "agreement_log_id": None,
        "currency": "PLN",
        "effective_from": None,
        "note": "Domyślna kwota systemowa"
    }

def create_or_update_weekly_advance_agreement(project_id, amount, note=None, created_by_role="INVESTOR"):
    from datetime import date
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")
        
    try:
        res = supabase.table("project_logs")\
            .select("*")\
            .eq("project_id", project_id)\
            .eq("type", PAYMENT_LOG_TYPE)\
            .execute()
        logs = res.data or []
        for log in logs:
            if is_weekly_advance_agreement_log(log):
                if log.get("status") not in ["CANCELLED", "SUPERSEDED", "REJECTED"]:
                    supabase.table("project_logs")\
                        .update({"status": "SUPERSEDED"})\
                        .eq("id", log["id"])\
                        .execute()
    except Exception as e:
        pass
        
    import json
    log_data = {
        "config_type": "WEEKLY_ADVANCE_AGREEMENT",
        "weekly_advance_agreement": True,
        "agreed_weekly_amount": float(amount),
        "currency": "PLN",
        "effective_from": date.today().strftime("%Y-%m-%d"),
        "created_by_role": created_by_role,
        "note": note or "Uzgodniona piątkowa zaliczka z szefem ekipy"
    }
    
    res_insert = supabase.table("project_logs").insert({
        "project_id": project_id,
        "type": PAYMENT_LOG_TYPE,
        "status": "ACTIVE",
        "title": f"Uzgodniona piątkowa zaliczka: {money(amount)}",
        "description": note or "Uzgodniona piątkowa zaliczka z szefem ekipy",
        "data": json.dumps(log_data)
    }).execute()
    
    return res_insert.data[0] if res_insert.data else None

def build_payment_expense_description(log_id, payment_type, note):
    marker = f"[payment_request:{log_id}]"
    safe_note = (note or "").strip()
    if payment_type == "REIMBURSEMENT":
        prefix = "[MATERIAŁY] Zwrot wydatków"
    else:
        prefix = "[ROBOCIZNA] Rozliczenie / wypłata"
    if safe_note:
        return f"{prefix}: {safe_note} {marker}"
    return f"{prefix} {marker}"

def confirm_payment_received_by_crew(log_id):
    """Ekipa potwierdza fizyczne zaksięgowanie pieniędzy na koncie i system księguje wydatek."""
    try:
        # A) Pobranie wniosku
        res = supabase.table("project_logs").select("id, status, data, description, title").eq("id", log_id).execute()
        if not res.data:
            return {"status": "error", "message": "Wniosek nie został znaleziony."}
        
        req = res.data[0]
        status = req.get("status")
        
        # B) Walidacja statusu
        if status in [PAYMENT_STATUS_PAID, PAYMENT_LEGACY_APPROVED]:
            return {"status": "ok", "message": "Ten wniosek jest już rozliczony."}
        if status != PAYMENT_STATUS_APPROVED_BY_INVESTOR:
            return {"status": "error", "message": "Ten wniosek nie czeka na potwierdzenie odbioru przez Ekipę."}
        
        # C) Odczyt danych
        d = parse_project_log_data(req.get("data"))
        amount = safe_float(d.get("amount"))
        payment_type = d.get("payment_type")
        note = d.get("note") or req.get("description") or "Brak opisu"
        expense_id = d.get("expense_id")
        material_id = d.get("material_id")
        
        # D) Walidacja kwoty
        if not amount or amount <= 0:
            return {"status": "error", "message": "Brak poprawnej kwoty we wniosku — nie można zaksięgować wydatku."}
        
        # E) Idempotencja — zabezpieczenie numer 1
        if expense_id:
            supabase.table("project_logs").update({
                "status": PAYMENT_STATUS_PAID
            }).eq("id", log_id).execute()
            return {"status": "ok", "message": "Odbiór potwierdzony. Wydatek był już zaksięgowany."}
        
        # F) Idempotencja — zabezpieczenie numer 2
        description = build_payment_expense_description(log_id, payment_type, note)
        marker = f"[payment_request:{log_id}]"
        
        check_exp = supabase.table("expenses")\
            .select("id, description, amount")\
            .filter("description", "like", f"%{marker}%")\
            .execute()
        
        existing_expenses = check_exp.data or []
        if existing_expenses:
            expense_id = existing_expenses[0]["id"]
        else:
            # G) Insert do expenses
            from datetime import date
            today_str = date.today().strftime("%Y-%m-%d")
            
            ins_data = {
                "description": description,
                "amount": amount,
                "quantity": 1,
                "date": today_str
            }
            if material_id:
                ins_data["material_id"] = material_id
                
            ins_data["project_id"] = req.get("project_id")
            ins_exp = supabase.table("expenses").insert(ins_data).execute()
            
            if not ins_exp.data:
                return {"status": "error", "message": "Nie udało się zapisać wydatku w bazie danych. Spróbuj ponownie."}
            
            expense_id = ins_exp.data[0]["id"]
        
        # H) Update project_logs
        d["expense_id"] = str(expense_id)
        d["received_at"] = datetime.now().isoformat()
        d["paid_at"] = datetime.now().isoformat()
        d["expense_description"] = description
        
        import json
        supabase.table("project_logs").update({
            "status": PAYMENT_STATUS_PAID,
            "data": json.dumps(d)
        }).eq("id", log_id).execute()
        
        return {"status": "ok", "message": "Odbiór środków potwierdzony i wydatek zaksięgowany."}
    except Exception as e:
        return {"status": "error", "message": f"Wystąpił nieoczekiwany błąd: {e}"}

def approve_payment_request_by_investor(log_id, investor_note="", transfer_date=None, material_id=None):
    """Inwestor zatwierdza wniosek finansowy i deklaruje wysłanie przelewu."""
    try:
        res = supabase.table("project_logs").select("id, status, data, description, project_id").eq("id", log_id).execute()
        if not res.data:
            return {"status": "error", "message": "Wniosek nie został znaleziony."}
        
        req = res.data[0]
        if req.get("status") != PAYMENT_STATUS_SUBMITTED:
            return {"status": "error", "message": "Ten wniosek nie oczekuje już na decyzję inwestora."}
        
        raw_data = req.get("data")
        import json
        d = {}
        if isinstance(raw_data, dict):
            d = raw_data
        elif isinstance(raw_data, str):
            try:
                d = json.loads(raw_data)
            except:
                pass
        
        # Opcjonalne powiązanie z materiałem dla REIMBURSEMENT
        if d.get("payment_type") == "REIMBURSEMENT" and material_id:
            # Weryfikacja czy materiał należy do tego projektu
            try:
                mat_res = supabase.table("materials").select("id").eq("id", material_id).eq("project_id", req.get("project_id")).execute()
                if not mat_res.data:
                    return {"status": "error", "message": "Wybrany materiał jest nieprawidłowy lub nie należy do tego projektu."}
            except Exception as e:
                return {"status": "error", "message": "Błąd bazy danych (Tabela materiałów)."}
            d["material_id"] = material_id
        
        d["investor_note"] = investor_note
        if transfer_date:
            d["transfer_date"] = transfer_date.isoformat() if hasattr(transfer_date, "isoformat") else str(transfer_date)
        d["approved_by_investor_at"] = datetime.now().isoformat()
        
        supabase.table("project_logs").update({
            "status": PAYMENT_STATUS_APPROVED_BY_INVESTOR,
            "data": json.dumps(d)
        }).eq("id", log_id).execute()
        
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": f"Błąd podczas zatwierdzania: {e}"}

def reject_payment_request_by_investor(log_id, rejection_reason):
    """Inwestor odrzuca wniosek finansowy z podaniem powodu."""
    try:
        if not rejection_reason or not rejection_reason.strip():
            return {"status": "error", "message": "Powód odrzucenia jest wymagany."}
            
        res = supabase.table("project_logs").select("id, status, data, description").eq("id", log_id).execute()
        if not res.data:
            return {"status": "error", "message": "Wniosek nie został znaleziony."}
        
        req = res.data[0]
        if req.get("status") != PAYMENT_STATUS_SUBMITTED:
            return {"status": "error", "message": "Ten wniosek nie oczekuje już na decyzję inwestora."}
        
        raw_data = req.get("data")
        import json
        d = {}
        if isinstance(raw_data, dict):
            d = raw_data
        elif isinstance(raw_data, str):
            try:
                d = json.loads(raw_data)
            except:
                pass
        
        d["rejection_reason"] = rejection_reason.strip()
        d["rejected_at"] = datetime.now().isoformat()
        
        supabase.table("project_logs").update({
            "status": PAYMENT_STATUS_REJECTED,
            "data": json.dumps(d),
            "description": rejection_reason.strip()
        }).eq("id", log_id).execute()
        
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": f"Błąd podczas odrzucania: {e}"}

PAYMENT_RULES = {
    "limit_model": "HYBRID_50_100",
    "done_percent": 1.00,
    "advance_percent": 0.50,
    "blocked_percent": 0.00,
    "global_advance_cap_percent": 0.30,
    "min_payment_request_amount": 500.00,
    "strict_contractor_limit": True,
    "investor_override_allowed": True,
    "advance_eligible_execution_statuses": ["TODO", "IN_PROGRESS"],
    "final_eligible_execution_statuses": ["DONE"],
    "blocked_execution_statuses": ["BLOCKED"],
    "required_commercial_status": "ACCEPTED_LOCKED",
    "paid_statuses": ["PAID", "APPROVED"],
    "pending_statuses": ["SUBMITTED", "UNDER_REVIEW"]
}

def safe_float(value, default=0.0):
    try:
        if value is None: return default
        return float(value)
    except: return default

def money(value):
    val = safe_float(value)
    return f"{val:,.2f} PLN".replace(",", " ")

# --- LOGIKA KWALIFIKACJI ZADANIA ---
def calculate_task_payment_eligibility(task, rules=PAYMENT_RULES):
    db_price = safe_float(task.get('final_approved_price'))
    h = parse_handshake_data(task.get('description', ''))
    locked_price = h['price']
    
    # Użyj db_price, z fallbackiem na locked_price
    task_price = db_price if db_price > 0 else locked_price
    commercial_status = h['commercial']
    is_price_accepted = (commercial_status == rules["required_commercial_status"]) or (db_price > 0)

    if task_price <= 0:
        return {"eligibility_percent": 0.0, "eligible_value": 0.0, "type": "NO_PRICE", "reason": "Brak ceny."}

    if not is_price_accepted:
        return {"eligibility_percent": 0.0, "eligible_value": 0.0, "type": "NOT_LOCKED", "reason": "Cena niezaakceptowana."}

    # Wykrywanie statusu - priorytet dla statusu strukturalnego i helpera progress
    has_structured_status = any(task.get(f) is not None for f in ['kanban_status', 'completion_status', 'status'])
    status_resolved = None

    if is_task_completed_for_progress(task):
        status_resolved = "DONE"
    elif has_structured_status:
        raw_status = str(task.get('kanban_status') or task.get('completion_status') or task.get('status') or '').upper()
        if raw_status in ["TODO", "IN_PROGRESS", "AWAITING_INSPECTION", "READY", "PENDING", "NOT_STARTED"]:
            status_resolved = "IN_PROGRESS"
        elif raw_status in ["BLOCKED"]:
            status_resolved = "BLOCKED"
        else:
            status_resolved = "OTHER"
    else:
        # Legacy EXECUTION marker is used only when structured task status fields are missing.
        legacy_status = str(h.get('execution', '')).upper()
        if legacy_status in rules["final_eligible_execution_statuses"]:
            status_resolved = "DONE"
        elif legacy_status in rules["advance_eligible_execution_statuses"]:
            status_resolved = "IN_PROGRESS"
        elif legacy_status in rules["blocked_execution_statuses"]:
            status_resolved = "BLOCKED"
        else:
            status_resolved = "OTHER"

    if status_resolved == "DONE":
        return {
            "eligibility_percent": rules["done_percent"],
            "eligible_value": task_price * rules["done_percent"],
            "type": "FINAL_100",
            "reason": "Zadanie DONE (100%)"
        }
    elif status_resolved == "IN_PROGRESS":
        return {
            "eligibility_percent": rules["advance_percent"],
            "eligible_value": task_price * rules["advance_percent"],
            "type": "ADVANCE_50",
            "reason": "Zadanie Aktywne (50%)"
        }
    elif status_resolved == "BLOCKED":
        return {
            "eligibility_percent": rules["blocked_percent"],
            "eligible_value": 0.0,
            "type": "BLOCKED",
            "reason": "Zadanie zablokowane (0%)"
        }
    else:
        return {
            "eligibility_percent": 0.0,
            "eligible_value": 0.0,
            "type": "OTHER",
            "reason": "Status niekwalifikowany."
        }

# --- GŁÓWNY KALKULATOR LIMITU ---
def calculate_hybrid_payment_limit(project_id):
    try:
        budget = supabase.table("project_metadata").select("total_budget").eq("id", project_id).single().execute().data.get('total_budget', 0)
        
        all_tasks = supabase.table("tasks").select("*").eq("project_id", project_id).execute().data or []
        
        comp_val = 0.0
        adv_base = 0.0
        
        for t in all_tasks:
            el = calculate_task_payment_eligibility(t)
            if el['type'] == "FINAL_100": comp_val += el['eligible_value']
            elif el['type'] == "ADVANCE_50": adv_base += el['eligible_value']
        
        # Global Cap 30% na zaliczki
        global_cap = budget * PAYMENT_RULES["global_advance_cap_percent"]
        capped_adv = min(adv_base, global_cap) if budget > 0 else adv_base
        
        gross_limit = comp_val + capped_adv
        
        # Suma wypłat i oczekujących
        logs_raw = supabase.table("project_logs").select("*").eq("project_id", project_id).eq("type", PAYMENT_LOG_TYPE).execute().data or []
        logs = [l for l in logs_raw if is_payment_request_log(l)]
        paid_pending = 0.0
        for l in logs:
            if l.get('status') not in ['REJECTED', 'CANCELLED']:
                try:
                    import json
                    d = json.loads(l.get('data', '{}'))
                    paid_pending += safe_float(d.get('amount'))
                except: pass

        available = max(0.0, gross_limit - paid_pending)
        
        return {
            "available": round(available, 2),
            "gross_limit": round(gross_limit, 2),
            "completed_val": round(comp_val, 2),
            "advance_val": round(capped_adv, 2),
            "already_paid": round(paid_pending, 2),
            "budget": budget,
            "is_advance_capped": adv_base > global_cap and budget > 0
        }
    except Exception as e:
        return {
            "available": 0.0, 
            "gross_limit": 0.0, 
            "completed_val": 0.0, 
            "advance_val": 0.0, 
            "already_paid": 0.0,
            "budget": 0.0,
            "is_advance_capped": False,
            "error": str(e)
        }

def classify_payment_request(limit_res):
    if limit_res['completed_val'] > 0 and limit_res['advance_val'] > 0: return "MIXED"
    if limit_res['advance_val'] > 0: return "ADVANCE"
    return "FINAL"

def build_payment_limit_snapshot(limit_res):
    return {
        "model": "HYBRID_50_100",
        "available_at_request": limit_res['available'],
        "gross_limit": limit_res['gross_limit'],
        "completed_val": limit_res['completed_val'],
        "advance_val": limit_res['advance_val'],
        "already_paid": limit_res['already_paid'],
        "is_capped": limit_res.get('is_advance_capped', False)
    }

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
    st.session_state["current_project_id"] = None
    st.session_state.pop("selected_project_id", None)
    st.session_state["crew_authorized_project_id"] = None
    st.session_state["crew_project_access_verified"] = False
    st.session_state["crew_access_code_id"] = None
    st.session_state.pop("last_generated_crew_code", None)
    st.rerun()

# --- EKRAN LOGOWANIA ---
if st.session_state["role"] is None:
    st.markdown("<h1 style='text-align:center;margin-top:80px'>RemontIQ</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#a0aec0'>Wybierz swoją rolę, aby kontynuować.</p>", unsafe_allow_html=True)

    auth_config = st.secrets.get("auth", {})
    inv_pin = auth_config.get("investor_pin")
    
    if not inv_pin:
        st.error("Błąd konfiguracji logowania. Skontaktuj się z administratorem.")
        st.stop()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_inv, tab_crew = st.tabs(["👤 Jestem Inwestorem", "👷 Jestem Ekipą"])
        
        with tab_inv:
            with st.form("login_form_inv"):
                pin = st.text_input("Główny PIN Inwestora", type="password", placeholder="Wpisz PIN inwestora", key="investor_pin_input")
                if st.form_submit_button("Zaloguj jako Inwestor", width="stretch", type="primary"):
                    if pin == str(inv_pin):
                        # Zmiana z ekipy na inwestora (czyszczenie ekipy)
                        st.session_state["crew_authorized_project_id"] = None
                        st.session_state["crew_project_access_verified"] = False
                        st.session_state["crew_access_code_id"] = None
                        
                        st.session_state["role"] = "investor"
                        st.session_state["user_id"] = "00000000-0000-0000-0000-000000000001"
                        st.session_state["last_visit"] = st.session_state.get("current_visit", None)
                        st.session_state["current_visit"] = datetime.now().isoformat()
                        st.rerun()
                    else:
                        st.error("Nieprawidłowy PIN!")
                        
        with tab_crew:
            with st.form("login_form_crew"):
                st.info("Wpisz kod dostępu do remontu otrzymany od inwestora (np. EKIPA-XXXX-XXXX).")
                crew_code = st.text_input("Kod dostępu", placeholder="EKIPA-...", key="crew_code_input")
                if st.form_submit_button("Wejdź do remontu", width="stretch", type="primary"):
                    from services.supabase_client import get_supabase_client
                    from services.access_service import validate_crew_access_code
                    supabase_client = get_supabase_client()
                    
                    record = validate_crew_access_code(crew_code, supabase_client)
                    
                    if record:
                        # Aktualizacja used_at
                        supabase_client.table("project_access_codes").update({"used_at": datetime.now().isoformat()}).eq("id", record["id"]).execute()
                        
                        st.session_state["role"] = "crew"
                        # Zmiana z inwestora na ekipę (czyszczenie inwestora)
                        st.session_state.pop("selected_project_id", None)
                        
                        st.session_state["current_project_id"] = record["project_id"]
                        st.session_state["crew_authorized_project_id"] = record["project_id"]
                        st.session_state["crew_project_access_verified"] = True
                        st.session_state["crew_access_code_id"] = record["id"]
                        
                        st.session_state["last_visit"] = st.session_state.get("current_visit", None)
                        st.session_state["current_visit"] = datetime.now().isoformat()
                        st.rerun()
                    else:
                        st.error("Nieprawidłowy lub nieaktywny kod remontu.")

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
        desc_esc = html.escape(str(e.get("description", "")))
        items_html += f'<div class="activity-item">{icon} {desc_esc} <span style="color:#718096;font-size:11px">({ts})</span></div>'
    
    st.markdown(f"""
    <div class="activity-banner">
        <div style="font-weight:700;color:#90cdf4;margin-bottom:6px">
            🔔 Nowe zdarzenia ({len(events)})
        </div>
        {items_html}
    </div>""", unsafe_allow_html=True)



# ==========================================
# 🚀 SYSTEM NAWIGACJI SaaS (Multi-Role)
# ==========================================

# 0. Wymuś autoryzację i blokadę dostępu zanim cokolwiek się załaduje!
enforce_project_access_invariant()

# 1. Pobranie metadanych projektu (Wspólne)
project_meta = get_project_metadata()
if project_meta:
    if st.session_state.get('role') == "investor":
        st.session_state["user_name"] = project_meta.get("investor_name", "Inwestor")
    elif st.session_state.get('role') == "crew":
        st.session_state["user_name"] = project_meta.get("crew_lead_name", "Szef Ekipy")

proj_name = project_meta['project_name'] if project_meta else "Brak projektu"
role_name = "Inwestor" if st.session_state['role'] == "investor" else f"Ekipa ({st.session_state.get('user_name', 'Szef Ekipy')})"

# 2. Renderowanie Górnego Bara (Wspólne)
render_top_bar(proj_name, role_name, st.session_state.get('user_name', 'Użytkownik'))

def render_crew_login_gate():
    st.error("Brak uprawnień. Proszę zalogować się za pomocą poprawnego kodu dostępu do remontu.")
    with st.form("guard_crew_login_form"):
        crew_code = st.text_input("Kod dostępu", placeholder="EKIPA-...", key="guard_crew_code_input")
        if st.form_submit_button("Wejdź do remontu", width="stretch", type="primary"):
            from services.supabase_client import get_supabase_client
            from services.access_service import validate_crew_access_code
            supabase_client = get_supabase_client()
            
            record = validate_crew_access_code(crew_code, supabase_client)
            if record:
                supabase_client.table("project_access_codes").update({"used_at": datetime.now().isoformat()}).eq("id", record["id"]).execute()
                
                st.session_state.pop("selected_project_id", None)
                st.session_state["role"] = "crew"
                st.session_state["current_project_id"] = record["project_id"]
                st.session_state["crew_authorized_project_id"] = record["project_id"]
                st.session_state["crew_project_access_verified"] = True
                st.session_state["crew_access_code_id"] = record["id"]
                st.session_state["last_visit"] = st.session_state.get("current_visit", None)
                st.session_state["current_visit"] = datetime.now().isoformat()
                st.rerun()
            else:
                st.error("Nieprawidłowy lub nieaktywny kod remontu.")

# 3. Definicja Menu w Sidebarze (Zależna od Roli)
if st.session_state['role'] == "crew":
    if not st.session_state.get("crew_project_access_verified") or not st.session_state.get("current_project_id"):
        render_crew_login_gate()
        if st.sidebar.button("🚪 Wróć do logowania główniego"):
            logout()
        st.stop()
        
    st.sidebar.markdown("### 🛠️ ZARZĄDZANIE")
    
    menu = st.sidebar.radio("👷 NAWIGACJA", [
        "🚀 Plan na dzisiaj",
        "📝 Plan Remontu",
        "📋 Plan & Postęp",
        "💰 Moje Finanse",
        "🚨 Blokady i Materiały",
        "💬 Czat Budowy"
    ])
    
    st.sidebar.divider()
    
    if st.sidebar.button("🚪 Wyloguj", use_container_width=True):
        logout()
        st.rerun()
else:
    # ============================================================
    # MENU INWESTORA – 4 pozycje (czyste i intuicyjne)
    # ============================================================
    
    # Licznik nieprzeczytanych wiadomości dla badge'a czatu
    try:
        _p_meta_chat = get_project_metadata()
        _p_id_chat = _p_meta_chat.get('id') if _p_meta_chat else None
        if _p_id_chat:
            _tasks_chat = supabase.table("tasks").select("id").eq("project_id", _p_id_chat).execute().data or []
            _task_ids_chat = [t['id'] for t in _tasks_chat]
            _unread = 0
            if _task_ids_chat:
                _last_seen = st.session_state.get('chat_last_seen', '2000-01-01')
                _unread_res = supabase.table("task_comments")\
                    .select("id", count="exact")\
                    .in_("task_id", _task_ids_chat)\
                    .eq("is_deleted", False)\
                    .neq("author_role", "INVESTOR")\
                    .gt("created_at", _last_seen)\
                    .execute()
                _unread = _unread_res.count or 0
        else:
            _unread = 0
    except:
        _unread = 0

    _chat_label = f"💬 Czat {'🔴' if _unread > 0 else ''}" + (f" ({_unread}nowych)" if _unread > 0 else "")

    # Licznik oczekujących wniosków finansowych dla badge'a rozliczeń
    try:
        _p_meta_fin = get_project_metadata()
        _p_id_fin = _p_meta_fin.get('id') if _p_meta_fin else None
        if _p_id_fin:
            _logs_raw_fin = supabase.table("project_logs").select("data").eq("project_id", _p_id_fin).eq("type", PAYMENT_LOG_TYPE).eq("status", PAYMENT_STATUS_SUBMITTED).execute().data or []
            _pending_count = len([l for l in _logs_raw_fin if is_payment_request_log(l)])
        else:
            _pending_count = 0
    except:
        _pending_count = 0

    _settlements_label = f"💰 Rozliczenia" + (f" 🔴 ({_pending_count})" if _pending_count > 0 else "")

    INVESTOR_PAGES = {
        "home":   "🏠 Mój Remont",
        "plan":   "📋 Plan & Postęp",
        "budget": "💰 Budżet",
        "settlements": _settlements_label,
        "crew_view": "👷 Zapotrzebowania Ekipy",
        "chat":   _chat_label,
        "logout": "🚪 Wyloguj"
    }

    # Pulsowanie w CSS gdy są nieprzeczytane
    if _unread > 0:
        st.sidebar.markdown("""
        <style>
        [data-testid="stRadio"] label:nth-child(4) {
            animation: pulse 1.5s infinite;
            color: #f87171 !important;
            font-weight: 700;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        </style>""", unsafe_allow_html=True)

    selected_key = st.sidebar.radio(
        "Nawigacja",
        options=list(INVESTOR_PAGES.keys()),
        index=0,
        format_func=lambda x: INVESTOR_PAGES[x]
    )
    menu = selected_key

# 4. Globalna Logika Wylogowania
if menu == "logout":
    logout()
    st.rerun()

# 5. Blokada dla Ekipy (Nowy Workflow)
if st.session_state['role'] == "crew":
    p_id = project_meta.get('id') if project_meta else None
    
    if "daily_briefing_done" not in st.session_state: st.session_state.daily_briefing_done = False
    
    if not st.session_state.daily_briefing_done:
        user_name_esc = html.escape(str(st.session_state.get("user_name", "EKIPA"))).upper()
        
        st.markdown("## 🏗️ Poranna odprawa")
        st.markdown(f"**Dziś jest {datetime.now().strftime('%A, %d.%m.%Y')}**")
        st.markdown(f"Witaj, **{user_name_esc}**!")
        st.markdown("---")

        tasks_data = []
        try:
            if p_id:
                res = supabase.table("tasks").select("*").eq("project_id", p_id).execute()
                tasks_data = res.data or []
        except Exception as e:
            st.warning("Nie udało się pobrać zadań z serwera. Spróbuj odświeżyć.")

        attention_statuses = ["REJECTED", "CHANGES_REQUESTED", "BLOCKED"]
        review_statuses = ["AWAITING_INSPECTION", "READY_FOR_REVIEW", "READY_FOR_ACCEPTANCE"]
        
        needs_attention = [t for t in tasks_data if t.get("kanban_status") in attention_statuses or t.get("status") in attention_statuses]
        in_progress = [t for t in tasks_data if t.get("kanban_status") == "IN_PROGRESS" or t.get("status") == "IN_PROGRESS"]
        to_review = [t for t in tasks_data if t.get("kanban_status") in review_statuses or t.get("status") in review_statuses]

        c1, c2, c3 = st.columns(3)
        c1.metric("🚨 Wymaga uwagi", len(needs_attention))
        c2.metric("👷 W trakcie", len(in_progress))
        c3.metric("✅ Do odbioru", len(to_review))

        st.markdown("---")
        st.subheader("👷 Aktualnie w trakcie")
        if in_progress:
            for t in in_progress[:5]:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        # Assuming phase_id can be used if phase_name isn't present, but phase_name is usually handled. We will safely get it.
                        room_name = t.get("phase_name") or "Nieznane pomieszczenie"
                        st.markdown(f"**{t.get('name', 'Brak nazwy')}**")
                        st.caption(f"Pomieszczenie: {room_name}")
                    with col2:
                        if st.button("✅ Zgłoś do odbioru", key=f"finish_{t['id']}", use_container_width=True):
                            try:
                                supabase.table("tasks").update({"kanban_status": "AWAITING_INSPECTION", "updated_at": datetime.now().isoformat()}).eq("id", t['id']).execute()
                                st.success("Zgłoszono do odbioru!")
                                st.rerun()
                            except Exception as e:
                                st.warning("Nie udało się zaktualizować statusu zadania.")
        else:
            st.info("Brak zadań w trakcie.")

        st.markdown("---")
        st.subheader("🚨 Wymaga uwagi")
        if needs_attention:
            for t in needs_attention[:3]:
                with st.container(border=True):
                    room_name = t.get("phase_name") or "Nieznane pomieszczenie"
                    status = t.get("kanban_status") or t.get("status") or "BLOCKED"
                    st.markdown(f"**{t.get('name', 'Brak nazwy')}**")
                    st.caption(f"Pomieszczenie: {room_name} | Status: {status}")
        else:
            st.success("Brak pilnych spraw. Można działać dalej.")

        st.markdown("---")
        if st.button("🚀 Przejdź do pełnego planu", use_container_width=True, type="primary"):
            st.session_state.daily_briefing_done = True
            st.rerun()
        st.stop()
    
    # Obsługa przycisków funkcyjnych
    if menu == "📝 Plan Remontu":
        render_crew_panel(supabase, phase_service, negotiation_service, change_service, task_service, ordering_service)
        st.stop()
        
    elif menu == "📋 Plan & Postęp":
        render_plan_and_progress_view(project_meta, phase_service, viewer_role="crew")
        st.stop()
        
    elif menu == "💰 Moje Finanse":
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 30px; border-radius: 20px; color: white; margin-bottom: 25px;">
            <h1 style="margin:0; font-size: 32px;">💰 Moje Finanse</h1>
            <p style="opacity: 0.7; margin: 5px 0 0 0;">Centrum rozliczeń i wycen kontraktu</p>
        </div>
        """, unsafe_allow_html=True)
        
        tab_settlement, tab_weekly, tab_history = st.tabs([
            "💸 ROZLICZENIE OKRESOWE (MODEL 50/100)",
            "🗓️ UMÓWIONA PIĄTKOWA ZALICZKA",
            "📜 STATUS I HISTORIA WNIOSKÓW"
        ])
        
        with tab_settlement:
            st.subheader("Wniosek o wypłatę (Model Hybrydowy 50/100)")
            
            # --- KALKULACJA LIMITU (Sprint 23 — Ścieżka A+) ---
            fin = calculate_hybrid_payment_limit(p_id)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Za ukończone (100%)", money(fin['completed_val']))
            c2.metric("Zaliczki (50%)", money(fin['advance_val']), 
                      help="Zaliczka ograniczona do 30% budżetu projektu" if fin.get('is_advance_capped') else None)
            c3.metric("Pobrano / Oczekuje", money(fin['already_paid']))
            
            st.markdown(f"""
            <div style="background:rgba(56,161,105,0.08); border:1px solid #38a169; padding:20px; border-radius:15px; text-align:center; margin:20px 0;">
                <div style="font-size:14px; color:#888; text-transform:uppercase; letter-spacing:1px;">Dostępne do wypłaty teraz</div>
                <div style="font-size:42px; font-weight:bold; color:#38a169;">{money(fin['available'])}</div>
            </div>
            """, unsafe_allow_html=True)

            if fin.get('is_advance_capped'):
                st.warning(f"⚠️ Zastosowano globalny limit zaliczek (30% budżetu). Część zaliczkowa została ograniczona.")

            col_payout, col_reimb = st.columns(2)
            
            with col_payout:
                with st.form("payment_request_form_A_plus", clear_on_submit=True):
                    st.write("### 📤 Nowy wniosek")
                    raw_req_amount = st.text_input("Kwota wniosku (PLN)", value="0,00")
                    req_note = st.text_area("Uzasadnienie / Cel wypłaty", placeholder="Np. Zakup materiałów, rozliczenie etapu...")
                    
                    if st.form_submit_button("Wyślij wniosek do Inwestora", type="primary"):
                        req_amount, err = parse_pln_amount(raw_req_amount)
                        if err:
                            st.error(f"❌ {err}")
                        elif req_amount <= 0:
                            st.error("❌ Kwota wniosku musi być większa niż 0.")
                        else:
                            fresh_fin = calculate_hybrid_payment_limit(p_id)
                            if req_amount > fresh_fin['available']:
                                st.error(f"❌ Kwota przekracza aktualny dostępny limit ({money(fresh_fin['available'])}).")
                            elif req_amount < PAYMENT_RULES["min_payment_request_amount"] and req_amount < fresh_fin['available']:
                                st.error(f"❌ Minimalna kwota wniosku to {money(PAYMENT_RULES['min_payment_request_amount'])}.")
                            else:
                                import json
                                payment_type = classify_payment_request(fresh_fin)
                                snapshot = build_payment_limit_snapshot(fresh_fin)
                                
                                u_id = st.session_state.get('user_id')
                                log_data = {
                                    "amount": req_amount,
                                    "note": req_note,
                                    "payment_type": payment_type,
                                    "limit_snapshot": snapshot,
                                    "timestamp": datetime.now().isoformat(),
                                    "created_by_id": u_id,
                                    "reported_by": st.session_state.get("user_name", "Ekipa")
                                }
                                
                                supabase.table("project_logs").insert({
                                    "project_id": p_id,
                                    "type": PAYMENT_LOG_TYPE,
                                    "title": f"Wniosek ({payment_type}): {money(req_amount)}",
                                    "description": req_note,
                                    "data": json.dumps(log_data),
                                    "status": PAYMENT_STATUS_SUBMITTED
                                }).execute()
                                
                                add_activity_log(
                                    st.session_state.get("user_name", "Ekipa"), 
                                    "FINANCIAL", 
                                    p_id, 
                                    f"Złożono wniosek {payment_type} na kwotę {money(req_amount)}"
                                )
                                
                                st.success("✅ Wniosek wysłany do Inwestora. Status możesz śledzić w zakładce historii.")
                                time.sleep(1.5)
                                st.rerun()

            with col_reimb:
                with st.form("material_reimbursement_form", clear_on_submit=True):
                    st.write("### 🛒 Zwrot za materiały")
                    st.caption("Użyj tego formularza, jeśli kupiłeś materiały za własne pieniądze.")
                    raw_reimb_amount = st.text_input("Kwota z paragonu/faktury (PLN)", value="0,00")
                    reimb_note = st.text_input("Na co wydano? (krótki opis)")
                    
                    if st.form_submit_button("Zgłoś wydatek do zwrotu", type="primary"):
                        reimb_amount, err = parse_pln_amount(raw_reimb_amount)
                        if err:
                            st.error(f"❌ {err}")
                        elif reimb_amount <= 0:
                            st.error("❌ Kwota musi być większa niż 0.")
                        elif not reimb_note.strip():
                            st.error("❌ Podaj na co wydano pieniądze (krótki opis).")
                        else:
                            import json
                            u_id = st.session_state.get('user_id')
                            log_data = {
                                "amount": reimb_amount,
                                "note": reimb_note.strip(),
                                "payment_type": "REIMBURSEMENT",
                                "timestamp": datetime.now().isoformat(),
                                "created_by_id": u_id,
                                "reported_by": st.session_state.get("user_name", "Ekipa")
                            }
                            supabase.table("project_logs").insert({
                                "project_id": p_id,
                                "type": PAYMENT_LOG_TYPE,
                                "title": f"Zwrot za materiały: {money(reimb_amount)}",
                                "description": reimb_note.strip(),
                                "data": json.dumps(log_data),
                                "status": PAYMENT_STATUS_SUBMITTED
                            }).execute()
                            
                            add_activity_log(
                                st.session_state.get("user_name", "Ekipa"), 
                                "FINANCIAL", 
                                p_id, 
                                f"Zgłoszono zwrot za materiały: {money(reimb_amount)}"
                            )
                            
                            st.success("✅ Wniosek o zwrot wysłany do Inwestora. Status możesz śledzić w historii.")
                            time.sleep(1.5)
                            st.rerun()

            st.caption("ℹ️ Model Hybrydowy 50/100: 100% DONE | 50% TODO/IN_PROGRESS | 0% BLOCKED | Global Cap 30%.")

        with tab_weekly:
            # --- PIĄTKOWA ZALICZKA TYGODNIOWA ---
            st.write("### 🗓️ Umówiona piątkowa zaliczka")
            
            agreement_info = get_weekly_advance_amount_for_project(p_id)
            configured_weekly_amount = agreement_info["amount"]
            agreement_source = agreement_info["source"]
            agreement_log_id = agreement_info["agreement_log_id"]
            
            if agreement_source == "GLOBAL_FALLBACK":
                st.info("💡 Dla tego remontu nie ustawiono jeszcze indywidualnej umowy. Używana jest domyślna kwota systemowa.")
            else:
                st.success(f"🤝 Ustalona indywidualnie kwota dla tego remontu: **{money(configured_weekly_amount)}** (Zapisana przez Inwestora)")
            
            current_week = get_current_week_key()
            friday_date = get_week_friday_date()
            existing_adv = find_existing_weekly_advance(p_id, current_week)
            
            available = fin.get("available", 0.0)
            min_amount = PAYMENT_RULES["min_payment_request_amount"]
            
            # Oblicz suggested amount
            if available >= configured_weekly_amount:
                suggested_amount = configured_weekly_amount
                limit_warning = None
            else:
                suggested_amount = available
                limit_warning = "Obecny limit 50/100 jest niższy niż umówiona zaliczka. Możesz złożyć wniosek tylko do wysokości dostępnego limitu."
            
            # Pokaż status kartę
            with st.container(border=True):
                # Pokaż metryki
                st.write("**Bieżący Tydzień:** Rozliczenie piątkowe")
                col_met1, col_met2, col_met3 = st.columns(3)
                col_met1.write(f"💵 **Umówiona kwota:** {money(configured_weekly_amount)}")
                if agreement_source == "PROJECT_AGREEMENT":
                    col_met1.caption("🤝 Ustalona indywidualnie")
                else:
                    col_met1.caption("💡 Domyślna kwota systemowa")
                col_met2.write(f"📊 **Dostępny limit 50/100:** {money(available)}")
                col_met3.write(f"📅 **Planowany przelew:** {friday_date}")
                
                # Ustalenie statusu i renderowanie przycisków
                if not existing_adv:
                    # Status A: Nie złożono jeszcze wniosku
                    st.warning("⚠️ **Status zaliczki w tym tygodniu:** Nie złożono jeszcze wniosku")
                    
                    if limit_warning:
                        st.warning(limit_warning)
                        
                    if suggested_amount < min_amount:
                        st.error("❌ Obecny limit 50/100 jest niższy niż minimalna kwota wniosku. Poczekaj na postęp prac lub rozliczenie zadań.")
                        st.button("🗓️ Potwierdzam i składam wniosek o piątkową zaliczkę", disabled=True, use_container_width=True)
                    else:
                        with st.form("weekly_advance_form_new", clear_on_submit=True):
                            st.write(f"Kwota sugerowana: **{money(suggested_amount)}** (kliknij poniżej, aby zatwierdzić)")
                            amount_val = st.number_input("Zgłaszana kwota zaliczki (PLN)", value=float(suggested_amount), min_value=float(min_amount), max_value=float(suggested_amount), step=100.0)
                            if st.form_submit_button("🗓️ Potwierdzam i składam wniosek o piątkową zaliczkę", type="primary", use_container_width=True):
                                fresh_fin = calculate_hybrid_payment_limit(p_id)
                                fresh_available = fresh_fin.get("available", 0.0)
                                if amount_val > fresh_available:
                                    st.error(f"❌ Kwota przekracza aktualny dostępny limit ({money(fresh_available)}).")
                                elif amount_val < min_amount:
                                    st.error(f"❌ Kwota jest niższa niż minimalna ({money(min_amount)}).")
                                else:
                                    import json
                                    u_id = st.session_state.get('user_id')
                                    fresh_snapshot = build_payment_limit_snapshot(fresh_fin)
                                    
                                    log_data = {
                                        "amount": amount_val,
                                        "note": "Piątkowa zaliczka tygodniowa",
                                        "payment_type": "ADVANCE",
                                        "payment_subtype": "WEEKLY_FRIDAY_ADVANCE",
                                        "weekly_advance": True,
                                        "week_key": current_week,
                                        "scheduled_payment_date": friday_date,
                                        "limit_snapshot": fresh_snapshot,
                                        "timestamp": datetime.now().isoformat(),
                                        "created_by_id": u_id,
                                        "reported_by": st.session_state.get("user_name", "Ekipa"),
                                        "agreed_weekly_amount": configured_weekly_amount,
                                        "agreement_log_id": agreement_log_id,
                                        "agreement_source": agreement_source,
                                        "confirmed_by_crew": True,
                                        "confirmed_by_crew_at": datetime.now().isoformat()
                                    }
                                    
                                    supabase.table("project_logs").insert({
                                        "project_id": p_id,
                                        "type": PAYMENT_LOG_TYPE,
                                        "title": f"Piątkowa zaliczka: {money(amount_val)}",
                                        "description": "Piątkowa zaliczka tygodniowa",
                                        "data": json.dumps(log_data),
                                        "status": PAYMENT_STATUS_SUBMITTED
                                    }).execute()
                                    
                                    add_activity_log(
                                        st.session_state.get("user_name", "Ekipa"),
                                        "FINANCIAL",
                                        p_id,
                                        f"Złożono wniosek o piątkową zaliczkę za tydzień {current_week} na kwotę {money(amount_val)}"
                                    )
                                    
                                    st.success("✅ Wniosek o piątkową zaliczkę wysłany do Inwestora!")
                                    time.sleep(1.5)
                                    st.rerun()
                else:
                    existing_data = parse_project_log_data(existing_adv.get("data"))
                    existing_amount = safe_float(existing_data.get("amount"))
                    existing_status = existing_adv.get("status")
                    
                    st.write(f"📋 **Szczegóły wniosku w tym tygodniu:**")
                    st.write(f"- **Kwota wnioskowana:** {money(existing_amount)}")
                    
                    if existing_status == PAYMENT_STATUS_SUBMITTED:
                        # Status B: Wniosek wysłany do Inwestora
                        st.info("⏳ **Status zaliczki w tym tygodniu:** Wniosek wysłany do Inwestora")
                        st.info("Wniosek o piątkową zaliczkę został wysłany do Inwestora i oczekuje na zatwierdzenie.")
                    
                    elif existing_status == PAYMENT_STATUS_APPROVED_BY_INVESTOR:
                        # Status C: Inwestor zadeklarował przelew
                        st.success("🟢 **Status zaliczki w tym tygodniu:** Inwestor zadeklarował przelew")
                        st.markdown("**Inwestor zadeklarował przelew.**")
                        if st.button("📥 Potwierdzam odbiór piątkowej zaliczki", key=f"confirm_weekly_rec_{existing_adv['id']}", type="primary", use_container_width=True):
                            res = confirm_payment_received_by_crew(existing_adv['id'])
                            if res['status'] == 'ok':
                                add_activity_log(st.session_state.get("user_name", "Ekipa"), "FINANCIAL", p_id, f"Potwierdzono odbiór piątkowej zaliczki: {money(existing_amount)}")
                                st.success("✅ Zaliczka rozliczona poprawnie!")
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error(f"❌ {res['message']}")
                                
                    elif existing_status == PAYMENT_STATUS_PAID:
                        # Status D: Zaliczka rozliczona
                        st.success("✅ **Status zaliczki w tym tygodniu:** Zaliczka rozliczona")
                        paid_at_str = existing_data.get("paid_at", existing_adv.get("created_at", ""))[:10]
                        st.write(f"Zaliczka za ten tydzień została rozliczona (Data: **{paid_at_str}**).")
                        
                    elif existing_status == PAYMENT_STATUS_REJECTED:
                        # Status E: Wniosek odrzucony
                        st.error("❌ **Status zaliczki w tym tygodniu:** Wniosek odrzucony")
                        rej_reason = existing_data.get("rejection_reason") or existing_adv.get("description") or "Brak podanego powodu"
                        st.caption(f"**Powód odrzucenia:** {rej_reason}")
                        
                        # Można złożyć nowy wniosek, bo odrzucony nie blokuje!
                        st.divider()
                        st.write("Możesz złożyć nowy wniosek dla tego tygodnia:")
                        if limit_warning:
                            st.warning(limit_warning)
                        if suggested_amount < min_amount:
                            st.error("❌ Obecny limit 50/100 jest niższy niż minimalna kwota wniosku. Poczekaj na postęp prac.")
                        else:
                            with st.form("weekly_advance_form_retry", clear_on_submit=True):
                                amount_val = st.number_input("Zgłaszana kwota zaliczki (PLN)", value=float(suggested_amount), min_value=float(min_amount), max_value=float(suggested_amount), step=100.0)
                                if st.form_submit_button("🗓️ Potwierdzam i składam wniosek o piątkową zaliczkę", type="primary", use_container_width=True):
                                    fresh_fin = calculate_hybrid_payment_limit(p_id)
                                    fresh_available = fresh_fin.get("available", 0.0)
                                    if amount_val > fresh_available:
                                        st.error(f"❌ Kwota przekracza limit ({money(fresh_available)}).")
                                    elif amount_val < min_amount:
                                        st.error(f"❌ Kwota jest niższa niż minimalna ({money(min_amount)}).")
                                    else:
                                        import json
                                        u_id = st.session_state.get('user_id')
                                        fresh_snapshot = build_payment_limit_snapshot(fresh_fin)
                                        
                                        log_data = {
                                            "amount": amount_val,
                                            "note": "Piątkowa zaliczka tygodniowa (Ponowne zgłoszenie)",
                                            "payment_type": "ADVANCE",
                                            "payment_subtype": "WEEKLY_FRIDAY_ADVANCE",
                                            "weekly_advance": True,
                                            "week_key": current_week,
                                            "scheduled_payment_date": friday_date,
                                            "limit_snapshot": fresh_snapshot,
                                            "timestamp": datetime.now().isoformat(),
                                            "created_by_id": u_id,
                                            "reported_by": st.session_state.get("user_name", "Ekipa"),
                                            "agreed_weekly_amount": configured_weekly_amount,
                                            "agreement_log_id": agreement_log_id,
                                            "agreement_source": agreement_source,
                                            "confirmed_by_crew": True,
                                            "confirmed_by_crew_at": datetime.now().isoformat()
                                        }
                                        
                                        supabase.table("project_logs").insert({
                                            "project_id": p_id,
                                            "type": PAYMENT_LOG_TYPE,
                                            "title": f"Piątkowa zaliczka: {money(amount_val)}",
                                            "description": "Piątkowa zaliczka tygodniowa",
                                            "data": json.dumps(log_data),
                                            "status": PAYMENT_STATUS_SUBMITTED
                                        }).execute()
                                        
                                        st.success("✅ Wysłano nową zaliczkę!")
                                        time.sleep(1.5)
                                        st.rerun()

            # --- HISTORIA PIĄTKOWYCH ZALICZEK ---
            st.divider()
            st.write("#### 📜 Historia piątkowych zaliczek")
            try:
                hist_resp = supabase.table("project_logs").select("*").eq("project_id", p_id).eq("type", PAYMENT_LOG_TYPE).execute()
                hist_logs = hist_resp.data or []
                weekly_logs = [log for log in hist_logs if is_weekly_advance_request(log)]
                # Sort by created_at desc
                weekly_logs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                
                if not weekly_logs:
                    st.caption("Brak wcześniejszych rozliczeń tygodniowych.")
                else:
                    for wl in weekly_logs[:8]:
                        wl_data = parse_project_log_data(wl.get("data"))
                        wl_amount = safe_float(wl_data.get("amount"))
                        wl_status = wl.get("status")
                        wl_friday = wl_data.get("scheduled_payment_date") or wl.get("created_at", "")[:10]
                        wl_week = wl_data.get("week_key") or "—"
                        
                        status_style = "✅ Rozliczona" if wl_status == PAYMENT_STATUS_PAID else get_payment_status_label(wl_status)
                        
                        agreed_amount = wl_data.get("agreed_weekly_amount")
                        source_str = ""
                        if agreed_amount:
                            src = wl_data.get("agreement_source") or "GLOBAL_FALLBACK"
                            src_label = "Indywidualna" if src == "PROJECT_AGREEMENT" else "Domyślna"
                            source_str = f" (Umowa: {money(agreed_amount)} [{src_label}])"
                        
                        st.markdown(f"- **Tydzień {wl_week}** (Przelew: `{wl_friday}`): **{money(wl_amount)}**{source_str} | Status: *{status_style}*")
            except Exception as e:
                st.caption(f"Nie udało się załadować historii: {e}")

        with tab_history:
            st.markdown("## 📜 Status i historia wniosków")
            
            try:
                logs_resp = supabase.table("project_logs")\
                    .select("id, title, description, status, data, created_at, type, is_deleted")\
                    .eq("project_id", p_id)\
                    .eq("type", PAYMENT_LOG_TYPE)\
                    .execute()
                
                reqs_history = logs_resp.data or []
                reqs_history = [r for r in reqs_history if not r.get("is_deleted") and is_payment_request_log(r)]
                reqs_history.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            except Exception as e:
                st.error(f"⚠️ Błąd pobierania historii wniosków: {e}")
                reqs_history = []
                
            aktywne_requests = []
            zamkniete_requests = []
            odrzucone_requests = []
            
            for r in reqs_history:
                status = r.get("status", PAYMENT_STATUS_SUBMITTED)
                if status in PAYMENT_OPEN_STATUSES:
                    aktywne_requests.append(r)
                elif status in [PAYMENT_STATUS_PAID, PAYMENT_LEGACY_APPROVED]:
                    zamkniete_requests.append(r)
                elif status == PAYMENT_STATUS_REJECTED:
                    odrzucone_requests.append(r)
                else:
                    aktywne_requests.append(r)
                    
            def render_crew_payment_item(req, key_prefix="crew_payment"):
                raw_data = req.get("data")
                import json
                d = {}
                if isinstance(raw_data, dict):
                    d = raw_data
                elif isinstance(raw_data, str):
                    try:
                        d = json.loads(raw_data)
                    except:
                        pass
                
                amount = safe_float(d.get("amount", 0.0))
                p_type = d.get("payment_type", "UNKNOWN")
                note = d.get("note") or req.get("description") or "Brak opisu"
                created_at = req.get("created_at", "")[:16].replace("T", " ")
                status = req.get("status", PAYMENT_STATUS_SUBMITTED)
                
                with st.container(border=True):
                    col_det, col_stat = st.columns([3, 1])
                    
                    with col_det:
                        st.markdown(f"### {money(amount)}")
                        st.markdown(f"**Typ:** {get_payment_type_label(p_type)}")
                        st.markdown(f"📝 **Opis:** {note}")
                        st.caption(f"📅 Zgłoszono: {created_at}")
                        
                        if d.get("investor_note"):
                            st.info(f"💬 **Notatka Inwestora:** {d.get('investor_note')}")
                        if d.get("rejection_reason") or (status == PAYMENT_STATUS_REJECTED and req.get("description")):
                            reason = d.get("rejection_reason") or req.get("description")
                            st.error(f"❌ **Powób odrzucenia:** {reason}")
                        if d.get("transfer_date"):
                            st.info(f"📅 **Data przelewu:** {d.get('transfer_date')}")
                        if d.get("expense_id"):
                            st.markdown("✅ **Zaksięgowano w kosztach remontu**")
                            
                    with col_stat:
                        st.markdown(f"**Status:**")
                        st.markdown(f"#### {get_payment_status_label(status)}")
                        st.markdown("**Kolejny krok:**")
                        st.caption(get_payment_next_action_label(status))
                        
                if status == PAYMENT_STATUS_APPROVED_BY_INVESTOR:
                    st.info("💡 **Przelew został zadeklarowany przez Inwestora.** Gdy środki dotrą na konto bankowe, potwierdź odbiór poniższym przyciskiem.")
                    if st.button("📥 Potwierdzam odbiór środków", key=f"{key_prefix}_confirm_received_{req['id']}", use_container_width=True, type="primary"):
                        res = confirm_payment_received_by_crew(req['id'])
                        if res["status"] == "ok":
                            st.success(f"✅ {res['message']}")
                            time.sleep(1.5)
                            st.rerun()
                        else:
                            st.error(f"❌ {res['message']}")
                        
            if not reqs_history:
                st.info("Nie masz jeszcze żadnych wniosków finansowych.")
            else:
                t_act, t_sett, t_rej, t_all = st.tabs([
                    f"⏳ Aktywne ({len(aktywne_requests)})", 
                    f"✅ Rozliczone ({len(zamkniete_requests)})", 
                    f"❌ Odrzucone ({len(odrzucone_requests)})", 
                    f"📋 Wszystkie ({len(reqs_history)})"
                ])
                
                with t_act:
                    if aktywne_requests:
                        for r in aktywne_requests:
                            render_crew_payment_item(r, key_prefix="crew_active")
                    else:
                        st.info("Brak aktywnych wniosków.")
                        
                with t_sett:
                    if zamkniete_requests:
                        for r in zamkniete_requests:
                            render_crew_payment_item(r, key_prefix="crew_settled")
                    else:
                        st.info("Brak rozliczonych wniosków.")
                        
                with t_rej:
                    if odrzucone_requests:
                        for r in odrzucone_requests:
                            render_crew_payment_item(r, key_prefix="crew_rejected")
                    else:
                        st.info("Brak odrzuconych wniosków.")
                        
                with t_all:
                    for r in reqs_history:
                        render_crew_payment_item(r, key_prefix="crew_all")
            
        st.stop()

    # (Opcja 🏗️ Plan Remontu 2.0 została przeniesiona do głównego przycisku)

    elif menu == "🚀 Plan na dzisiaj":
        from panels.crew_execution_panel import render_crew_execution_panel
        render_crew_execution_panel(supabase, task_service)
        st.stop()
        
    elif menu == "🚨 Blokady i Materiały":
        render_crew_blockers_materials_panel()
        st.stop()

    elif menu == "💬 Czat Budowy" or menu == "chat":
        try:
            # MAPOWANIE SESJI PIN
            if "role" in st.session_state:
                p_meta = get_project_metadata()
                if st.session_state["role"] == "investor":
                    st.session_state["user_role"] = "INVESTOR"
                    st.session_state["user_id"] = "00000000-0000-0000-0000-000000000001"
                    st.session_state["user_name"] = p_meta.get("investor_name", "Inwestor") if p_meta else "Inwestor"
                elif st.session_state["role"] == "crew":
                    st.session_state["user_role"] = "CREW_LEAD"
                    st.session_state["user_id"] = "00000000-0000-0000-0000-000000000002"
                    st.session_state["user_name"] = p_meta.get("crew_lead_name", "Szef Ekipy") if p_meta else "Szef Ekipy"

            render_chat_component(
                supabase=supabase,
                user_id=st.session_state.get("user_id"),
                user_role=st.session_state.get("user_role"),
                project_id=p_id
            )
        except Exception as e:
            st.error(f"❌ Błąd komponentu Czatu: {e}")
        st.stop()


# --- DALSZA LOGIKA DLA INWESTORA ---
render_activity_banner("investor")

# Pomocnicza lista pokoi (Dla formularzy)
p_meta_global = get_project_metadata()
if st.session_state.get("role") == "crew":
    p_id_global = st.session_state.get("crew_authorized_project_id")
    if p_id_global != st.session_state.get("current_project_id"):
        st.error("Błąd spójności dostępu. Wyloguj się.")
        st.stop()
else:
    p_id_global = p_meta_global.get('id') if p_meta_global else None

if p_id_global:
    rooms_req = supabase.table("rooms").select("id, name").eq("project_id", p_id_global).execute()
    df_rooms = pd.DataFrame(rooms_req.data) if rooms_req.data else pd.DataFrame()
else:
    df_rooms = pd.DataFrame(columns=["id", "name"])
rooms_dict = [{"id": None, "name": "Brak (Ogólne)"}]
for _, r in df_rooms.iterrows():
    rooms_dict.append({"id": r['id'], "name": r['name']})

# ============================================================
# ROUTING INWESTORA
# ============================================================
if menu == "home" or menu == "investor_2_0":
    # KREATOR STARTOWY – gdy brak projektu
    if not project_meta:
        st.markdown("""
        <div style="text-align:center; padding: 40px 20px 20px 20px;">
            <div style="font-size: 80px;">🏗️</div>
            <h1 style="font-size: 2.2rem; margin: 10px 0;">Witaj w RemontIQ!</h1>
            <p style="color: #94a3b8; font-size: 1.1rem;">Zanim zaczniemy, skonfigurujmy Twój projekt, by spersonalizować komunikację z Ekipą.</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("wizard_start", clear_on_submit=False):
            st.markdown("### 📋 Jak nazywa się Twój remont?")
            w_name = st.text_input("", placeholder="np. Mieszkanie na Wilanowie", label_visibility="collapsed")
            
            col_names1, col_names2 = st.columns(2)
            with col_names1:
                st.markdown("### 👤 Jak masz na imię?")
                w_investor_name = st.text_input("Imię Inwestora", placeholder="np. Michał", label_visibility="collapsed")
            with col_names2:
                st.markdown("### 👷 Jak ma na imię Szef Ekipy?")
                w_crew_name = st.text_input("Szef Ekipy", placeholder="np. Szef Ekipy (lub nazwa firmy)", label_visibility="collapsed")

            col_bud, col_date = st.columns(2)
            with col_bud:
                st.markdown("### 💰 Całkowity budżet (PLN)")
                w_budget = st.number_input("Budżet", min_value=10000, max_value=5000000, step=5000, value=100000, label_visibility="collapsed")
            with col_date:
                st.markdown("### 📅 Planowany start")
                w_start = st.date_input("Start", value=date.today(), label_visibility="collapsed")

            st.markdown("")
            if st.form_submit_button("🚀 ZACZYNAM REMONT →", use_container_width=True, type="primary"):
                if not w_name.strip() or not w_investor_name.strip() or not w_crew_name.strip():
                    st.error("Proszę wypełnić wszystkie pola (Nazwa remontu, Twoje imię, Imię Szefa Ekipy).")
                else:
                    # Ustaw user_id dla systemu PIN (wymagane przez create_project_metadata)
                    if "user_id" not in st.session_state:
                        st.session_state["user_id"] = "00000000-0000-0000-0000-000000000001"
                        st.session_state["user_role"] = "INVESTOR"
                        st.session_state["user_name"] = w_investor_name.strip()
                    
                    w_end = w_start + timedelta(days=90)
                    res = create_project_metadata(
                        project_name=w_name.strip(),
                        project_description="",
                        planned_start_date=w_start,
                        planned_end_date=w_end,
                        total_budget=w_budget,
                        investor_name=w_investor_name.strip(),
                        crew_lead_name=w_crew_name.strip(),
                        crew_contact="",
                        scope_of_work="",
                        special_conditions="",
                        status="PLANNING"
                    )
                    if res:
                        st.session_state['wizard_step'] = 'rooms'
                        st.rerun()
                    else:
                        st.error("Błąd zapisu projektu.")
        st.stop()

    # KREATOR POMIESZCZEŃ – krok 2 po utworzeniu projektu
    if st.session_state.get('wizard_step') == 'rooms':
        project_meta = get_project_metadata()
        p_id = project_meta['id'] if project_meta else None

        st.markdown("""
        <div style="text-align:center; padding: 20px;">
            <div style="font-size: 60px;">🏠</div>
            <h2>Jakie pomieszczenia remontujesz?</h2>
            <p style="color: #94a3b8;">Kliknij te, które wchodzą w skład Twojego remontu.</p>
        </div>
        """, unsafe_allow_html=True)

        ROOM_OPTIONS = [
            ("🛁 Łazienka", "Łazienka"), ("🚽 WC / Toaleta", "WC"),
            ("🍳 Kuchnia", "Kuchnia"), ("🛋️ Salon", "Salon"),
            ("🛏️ Sypialnia", "Sypialnia"), ("🏠 Przedpokój", "Przedpokój"),
            ("📚 Gabinet", "Gabinet"), ("🏚️ Strych", "Strych"),
            ("🏗️ Piwnica", "Piwnica"), ("🪟 Balkon/Taras", "Balkon"),
        ]

        if 'wizard_rooms' not in st.session_state:
            st.session_state['wizard_rooms'] = set()

        cols = st.columns(5)
        for i, (label, name) in enumerate(ROOM_OPTIONS):
            with cols[i % 5]:
                is_selected = name in st.session_state['wizard_rooms']
                btn_style = "primary" if is_selected else "secondary"
                if st.button(label, key=f"wr_{i}", use_container_width=True, type=btn_style):
                    if name in st.session_state['wizard_rooms']:
                        st.session_state['wizard_rooms'].discard(name)
                    else:
                        st.session_state['wizard_rooms'].add(name)
                    st.rerun()

        st.markdown("")
        custom_room = st.text_input("➕ Inne pomieszczenie (wpisz nazwę i naciśnij Enter)", key="custom_room_w")
        if custom_room and st.button("Dodaj", key="add_custom_w"):
            st.session_state['wizard_rooms'].add(custom_room.strip())
            st.rerun()

        selected_rooms = st.session_state.get('wizard_rooms', set())
        if selected_rooms:
            st.success(f"✅ Wybrano: {', '.join(selected_rooms)}")
        else:
            st.info("Wybierz przynajmniej jedno pomieszczenie.")

        crew_lead = project_meta.get('crew_lead_name', 'Ekipa') if project_meta else 'Ekipa'
        if st.button(f"✅ GOTOWE – Wyślij do wyceny ({crew_lead}) →", use_container_width=True, type="primary", disabled=not selected_rooms):
            if p_id and selected_rooms:
                for room_name in selected_rooms:
                    try:
                        supabase.table("rooms").insert({"name": room_name, "project_id": p_id}).execute()
                    except:
                        pass
                st.session_state.pop('wizard_step', None)
                st.session_state.pop('wizard_rooms', None)
                st.success(f"🎉 Projekt skonfigurowany! {crew_lead} może teraz budować plan remontu.")
                st.rerun()
        st.stop()

    # GŁÓWNY DASHBOARD INWESTORA
    if _pending_count > 0:
        st.warning(f"🚨 **Masz aktywne wnioski finansowe do obsługi ({_pending_count}).** Przejdź do zakładki: **💰 Rozliczenia** w menu bocznym, aby podjąć decyzję.")
    render_investor_panel(supabase, phase_service, negotiation_service, change_service, task_service, timeline_service, ordering_service)

elif menu == "chat":
    # Oznacz jako przeczytane
    st.session_state['chat_last_seen'] = datetime.now().isoformat()
    st.session_state["user_role"] = "INVESTOR"
    st.session_state["user_id"] = "00000000-0000-0000-0000-000000000001"
    p_meta = get_project_metadata()
    st.session_state["user_name"] = p_meta.get("investor_name", "Inwestor") if p_meta else "Inwestor"
    render_chat_component(
        supabase=supabase,
        user_id=st.session_state["user_id"],
        user_role=st.session_state["user_role"],
        project_id=p_id_global
    )

elif menu == "plan":
    render_plan_and_progress_view(project_meta, phase_service, viewer_role="investor")

elif menu == "charter":
    st.title("🏗️ Informacje o Projekcie")
    if project_meta:
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
        days_info = get_project_days_info(project_meta)
        if project_meta['status'] == "PLANNING":
            st.warning("🟡 **Status: PLANOWANIE**")
            if st.button("🚀 URUCHOM PROJEKT", use_container_width=True, type="primary"):
                update_project_metadata(project_meta['id'], status="ACTIVE", actual_start_date=date.today())
                st.rerun()
        elif project_meta['status'] == "ACTIVE":
            st.success("🟢 **Status: W TRAKCIE**")
            c1, c2, c3 = st.columns(3)
            c1.metric("⏳ Dni upłynęło", days_info['elapsed_days'])
            c2.metric("📅 Dni zostało", max(0, days_info['remaining_days']))
            c3.metric("⏱️ Upływ czasu", f"{days_info['progress_pct']}%")
            st.progress(days_info['progress_pct'] / 100)
        elif project_meta['status'] == "COMPLETED":
            st.success("✅ **Status: UKOŃCZONY**")
    else:
        st.info("Brak projektu. Wróć do 🏠 Mój Remont, aby go skonfigurować.")

elif menu == "dashboard_view":
    pass


    # ==============================
    # DANE
    # ==============================
    all_tasks_data = supabase.table("tasks").select("*").eq("project_id", p_id_global).execute().data or [] if p_id_global else []
    pending_insp = get_pending_inspections()
    crew_grouped = get_crew_requests_grouped()
    new_requests = crew_grouped.get("Nowe", [])
    blocked_tasks = [t for t in all_tasks_data if t.get("is_blocked")]
    awaiting_insp = [t for t in all_tasks_data if t.get("kanban_status") == "AWAITING_INSPECTION"]

    try:
        decisions_data = supabase.table("decisions").select("*").eq("status", "Do podjęcia").execute().data or []
        urgent_decisions = [d for d in decisions_data if d.get("due_date") and (date.fromisoformat(d["due_date"]) - date.today()).days <= 7]
    except Exception:
        urgent_decisions = []

    try:
        risks_data = supabase.table("issues").select("*").not_.in_("status", ["Rozwiązane", "Zignorowane"]).execute().data or []
        critical_risks = [r for r in risks_data if r.get("severity") == "Krytyczne"]
    except Exception:
        risks_data, critical_risks = [], []

    # ==============================
    # SEKCJA 1: ALARMY
    # ==============================
    st.markdown("## ⚡ WYMAGAJĄ TWOJEGO DZIAŁANIA")

    def alarm_color(n): return "#e53e3e" if n > 0 else "#38a169"
    def alarm_bg(n): return "rgba(229,62,62,0.08)" if n > 0 else "rgba(56,161,105,0.08)"

    c1, c2, c3, c4 = st.columns(4)
    for col, label, emoji, count, sub in [
        (c1, "Do Odbioru", "🔔", len(pending_insp), ""),
        (c2, "Blokery", "🔴", len(blocked_tasks), ""),
        (c3, "Decyzje", "🤔", len(urgent_decisions), "deadline ≤7 dni"),
        (c4, "Ryzyka", "⚠️", len(risks_data), f"{len(critical_risks)} kryt."),
    ]:
        col.markdown(f"""
        <div style="background:{alarm_bg(count)};border:2px solid {alarm_color(count)};border-radius:10px;padding:16px;text-align:center;">
            <div style="font-size:28px">{emoji}</div>
            <div style="font-size:13px;color:#888">{label}</div>
            <div style="font-size:36px;font-weight:bold;color:{alarm_color(count)}">{count}</div>
            <div style="font-size:11px;color:#aaa">{sub}</div>
        </div>""", unsafe_allow_html=True)

    st.divider()

    # ==============================
    # SEKCJA 2: PULS PROJEKTU
    # ==============================
    st.markdown("## 📊 PULS PROJEKTU")
    
    # --- HEALTH SCORE WIDGET (Sprint 10) ---
    h = calculate_health_score()
    col_h1, col_h2 = st.columns([1, 3])
    with col_h1:
        st.markdown(f"""
            <div style="text-align:center; padding:15px; border-radius:10px; background:#1a1f2e; border:1px solid #2d3748">
                <h3 style="margin:0; color:#a0aec0">HEALTH</h3>
                <h1 style="margin:0; font-size:40px">{h['score']}%</h1>
                <p style="margin:0">{h['status']}</p>
            </div>
        """, unsafe_allow_html=True)
    with col_h2:
        m = h['metrics']
        d = h['details']
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏗️ Postęp prac", f"{m['progress']}%", f"{d['completed']}/{d['total']}")
        c2.metric("Terminy", f"{m['schedule']}%", f"-{d['delay']}d")
        c3.metric("Budżet", f"{m['budget']}%", f"{d['pct']}%")
        c4.metric("Blokery", f"{m['blockers']}%", f"{d['blockers']} szt")
    
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
                    st.info(f"📝 Szef Ekipy: {insp['submission_notes']}")
                render_comment_section(insp['task_id'], "investor")
                ba, bb = st.columns(2)
                if ba.button("✅ ZATWIERDŹ", key=f"cc_appr_{insp['id']}", width="stretch", type="primary"):
                    approve_inspection(insp["id"])
                    st.success("✅ Zatwierdzone! Szef Ekipy widzi to na tablicy.")
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
                linked_reqs = [r for r in (crew_grouped.get("Nowe", []) + crew_grouped.get("Potwierdzone", [])) if r.get("task_id") == task["id"]]
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
    # SEKCJA 6: BIEŻĄCY PLAN EKIPY (mini)
    # ==============================
    st.markdown("## 📅 PLAN PRAC EKIPY — TOP 5 ZADAŃ")
    top_tasks = supabase.table("tasks").select("name,kanban_status,planned_start_date,planned_end_date,is_blocked").order("planned_start_date").limit(5).execute().data or []
    if top_tasks:
        STATUS_EMOJI = {"BACKLOG": "⬜", "READY": "🟦", "IN_PROGRESS": "🟧", "AWAITING_INSPECTION": "🔔", "COMPLETED": "🟩"}
        for t in top_tasks:
            blk = " 🔴 ZABLOKOWANE" if t.get("is_blocked") else ""
            em = STATUS_EMOJI.get(t.get("kanban_status", "BACKLOG"), "❓")
            st.write(f"{em} **{t['name']}**{blk}")
            st.caption(f"   {t.get('planned_start_date','?')} → {t.get('planned_end_date','?')}")
    else:
        st.info("Szef Ekipy jeszcze nie zaplanował zadań.")



elif menu == "communication":
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

elif menu == "start":
    st.title("🚀 Kreator Startowy (Cloud)")
    st.write("Bezpiecznie dodaj pokoje do projektu w chmurze.")
    
    p_meta = get_project_metadata()
    p_id = p_meta.get('id') if p_meta else None
    
    with st.form("kreator_form", clear_on_submit=True):
        pokoje_input = st.text_input("Jakie pomieszczenia remontujesz? (po przecinku)")
        if st.form_submit_button("Zapisz pomieszczenia"):
            if not p_id:
                st.error("Brak aktywnego projektu. Nie można dodać pomieszczeń.")
            else:
                pokoje = [p.strip() for p in pokoje_input.split(",") if p.strip()]
                for p in pokoje:
                    try: 
                        supabase.table("rooms").insert({"name": p, "project_id": p_id}).execute()
                        phase_service.create_phase(project_id=p_id, phase_name=p)
                    except Exception: pass
                st.success(f"Przetworzono {len(pokoje)} pomieszczeń.")
                st.rerun()
                
    if p_id:
        r_req = supabase.table("rooms").select("name, created_at").eq("project_id", p_id).execute()
        df_r_view = pd.DataFrame(r_req.data) if r_req.data else pd.DataFrame()
        if not df_r_view.empty:
            st.dataframe(df_r_view[['name', 'created_at']], hide_index=True)
        else:
            st.info("Brak wprowadzonych pomieszczeń.")
    else:
        st.info("Wybierz projekt, by zobaczyć pomieszczenia.")

elif menu == "budget":
    st.title("💰 Wydatki (Supabase Sync)")
    df_exp = read_table("expenses", filters={"project_id": p_id_global, "is_deleted": False})
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
                        "project_id": p_id_global,
                        "description": e_desc, "amount": e_amount, "date": str(e_date),
                        "is_deleted": False
                    }).execute()
                    st.rerun()
                else: st.error("Opis i kwota są wymagane.")

    st.subheader("📜 Historia Wydatków")
    if not df_exp.empty:
        st.dataframe(df_exp[['date', 'description', 'amount']], width="stretch", hide_index=True)
    else:
        st.info("Brak zarejestrowanych wydatków.")

elif menu == "tasks":
    st.title("📋 PLAN REMONTU — Twój Harmonogram")
    st.caption("Poniżej znajduje się struktura prac ułożona przez Szefa Ekipy, z podziałem na pokoje.")
    
    p_id = project_meta.get('id') if project_meta else None
    if not p_id:
        st.warning("Najpierw utwórz Charter Projektu, aby Szef Ekipy miał gdzie pracować.")
        st.stop()
        
    phases = phase_service.get_phases(p_id)
    if not phases:
        st.info("📭 Szef Ekipy nie dodał jeszcze żadnych pomieszczeń do swojego planu. Upewnij się, że ma je do wyboru w Twoim słowniku.")
    else:
        # POBIERANIE WSZYSTKICH ZADAŃ RAZ (Rozwiązanie N+1)
        phase_ids = [p.get("id") for p in phases if p.get("id")]
        all_tasks = []
        if phase_ids:
            try:
                all_tasks_req = supabase.table("tasks").select("*").in_("phase_id", phase_ids).execute()
                all_tasks = all_tasks_req.data or []
            except Exception:
                all_tasks = []
            
        # Grupowanie w Pythonie po phase_id
        tasks_by_phase_id = {}
        for t in all_tasks:
            pid = t.get("phase_id")
            if pid:
                tasks_by_phase_id.setdefault(pid, []).append(t)

        for p in phases:
            with st.container(border=True):
                # Pobieramy zadania dla danego pokoju ze słownika w pamięci
                room_tasks = tasks_by_phase_id.get(p.get("id"), [])
                
                # Detekcja ryczałtu całkowitego na pomieszczenie
                is_lump_sum_room = any("[LUMP_SUM_ROOM]" in (t.get('description') or '') for t in room_tasks)
                
                if is_lump_sum_room:
                    st.markdown(f"### 📦 Pokój: {p['phase_name']} 🔒 `RYCZAŁT CAŁKOWITY`")
                else:
                    st.markdown(f"### 🚪 Pokój: {p['phase_name']}")
                    
                if not room_tasks:
                    st.caption("Szef Ekipy nie przypisał tu jeszcze żadnej wyceny ani zadania.")
                else:
                    for t in room_tasks:
                        desc = t.get('description') or ''
                        # Czyścimy wizualnie tagi i handshake
                        clean_desc = desc.split("------------------------")[0].strip() if "------------------------" in desc else desc
                        clean_desc = clean_desc.replace("[LUMP_SUM_ROOM]", "").strip()
                        
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.markdown(f"**{t.get('name', 'Brak nazwy')}**")
                            if clean_desc: st.caption(clean_desc)
                        with col2:
                            status_label = t.get('kanban_status') or t.get('status', 'Nieznany')
                            st.write(f"Status: **{status_label}**")
                        with col3:
                            price = t.get('final_approved_price') or 0
                            h_data = parse_handshake_data(desc) if "------------------------" in desc else None
                            proposed_price = h_data['price'] if h_data else 0
                            
                            if price > 0:
                                st.metric("Cena (Zablokowana)", f"{price:,.2f} zł")
                            elif proposed_price > 0:
                                st.metric("Oferta (Niezatwierdzona)", f"{proposed_price:,.2f} zł")
                                st.caption("Kieruj się do Centrum Dowodzenia")
                            else:
                                st.caption("Brak wyceny")
                    st.divider()

elif menu == "inspections":
    st.title("🔔 ODBIÓR PRAC")
    st.caption("Szef Ekipy zgłosił zakończenie zadań. Sprawdzi je, dodaj komentarz i zatwierdź lub zażąda poprawek.")

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
                    st.info(f"📝 **Uwagi Szefa Ekipy:** {inspection['submission_notes']}")

                st.divider()
                st.write("**Twoja decyzja:**")

                col_approve, col_rework = st.columns(2)
                with col_approve:
                    approve_note = st.text_input("Komentarz przy zatwierdzeniu (opcjonalnie)", key=f"approve_note_{inspection['id']}")
                    if st.button("✅ ZATWIERDŹ PRACE", key=f"approve_{inspection['id']}", width="stretch", type="primary"):
                        result = approve_inspection(inspection['id'], approve_note)
                        if result['status'] == 'ok':
                            st.success(f"✅ Zadanie \"{task.get('name')}\" zatwierdzone! Szef Ekipy zobaczy to na swojej tablicy.")
                            st.rerun()

                with col_rework:
                    rework_desc = st.text_area("Opisz co wymaga poprawek *", key=f"rework_desc_{inspection['id']}", placeholder="np. Poprawić kąt nachylenia przy wannie")
                    if st.button("❌ WYMAGA POPRAWEK", key=f"rework_{inspection['id']}", width="stretch"):
                        if not rework_desc.strip():
                            st.error("Musisz opisać co wymaga poprawek!")
                        else:
                            result = request_rework(inspection['id'], rework_desc)
                            if result['status'] == 'ok':
                                st.warning(f"❌ Zadanie \"{task.get('name')}\" wróciło do Szefa Ekipy z opisem poprawek.")
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

elif menu == "crew_view":
    st.title("👷 Zapotrzebowania Ekipy")
    st.caption("Ekipa zgłasza swoje zapotrzebowania oraz napotkane problemy. Potwierdź chęć pomocy lub oznacz sprawy jako dostarczone / rozwiązane.")

    grouped = get_crew_requests_grouped()

    nowe = grouped.get("Nowe", [])
    potwierdzone = grouped.get("Potwierdzone", [])
    dostarczone = grouped.get("Dostarczone", [])

    # --- KPI ---
    k1, k2, k3 = st.columns(3)
    k1.metric("🔴 Nowe zgłoszenia", len(nowe))
    k2.metric("🟡 W toku (podjęte działanie)", len(potwierdzone))
    k3.metric("🟢 Dostarczone / rozwiązane", len(dostarczone))
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
                        if c1.form_submit_button("✅ Potwierdzam — zajmuję się tym", width="stretch", type="primary"):
                            confirm_crew_request(req['id'], note, delivery)
                            st.rerun()
                        if c2.form_submit_button("❌ Anuluj zgłoszenie", width="stretch"):
                            cancel_crew_request(req['id'])
                            st.rerun()
                    st.caption("ℹ️ *Potwierdzenie da znać ekipie, że pracujesz nad sprawą. Anulowanie zamknie zgłoszenie i odblokuje powiązane zadanie (jeśli nie ma innych blokad).*")
    else:
        st.success("✅ Brak nowych zgłoszeń!")

    # --- POTWIERDZONE ---
    if potwierdzone:
        st.divider()
        st.subheader(f"🟡 W toku — w trakcie dostawy lub rozwiązywania ({len(potwierdzone)})")
        for req in potwierdzone:
            with st.container(border=True):
                col_info, col_btn = st.columns([3, 1.5])
                with col_info:
                    st.markdown(f"**{req['title']}**")
                    if req.get("investor_note"):
                        st.info(f"📝 {req['investor_note']}")
                    if req.get("expected_delivery_date"):
                        st.caption(f"📅 Szacowana dostawa: {req['expected_delivery_date']}")
                with col_btn:
                    if st.button("📦 Dostarczone / rozwiązane", key=f"del_btn_{req['id']}", width="stretch", type="primary"):
                        mark_crew_request_delivered(req['id'])
                        st.rerun()
                    st.caption("ℹ️ *Kliknięcie automatycznie odblokuje zadanie w Kanbanie, jeśli nie ma innych aktywnych blokad.*")

    # --- DOSTARCZONE (Historia) ---
    if dostarczone:
        with st.expander(f"📜 Historia dostarczonych / rozwiązanych ({len(dostarczone)})"):
            for req in dostarczone:
                st.caption(f"✅ {req['title']} — Dostarczone / rozwiązane")


# ==========================================
# NOWE MODUŁY SPRINT 4 (7-10)
# ==========================================

elif menu == "journal":
    st.title("📒 Dziennik Projektu")
    st.write("Centralne miejsce zarządzania decyzjami i problemami.")
    
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
        recs_raw = supabase.table("project_logs").select("*").eq("type", "DECISION").execute().data or []
        recs = [r for r in recs_raw if not is_payment_request_log(r)]
        if recs:
            df = pd.DataFrame(recs)
            ed = st.data_editor(df[['id', 'title', 'status', 'due_date', 'result']], key="ed_dec", width="stretch")
            if st.button("Zapisz zmiany (Decyzje)"):
                for _, r in ed.iterrows():
                    # Czyścimy dane z NaN (puste pola w Pandas)
                    clean_status = r['status'] if pd.notnull(r['status']) else "OPEN"
                    clean_result = r['result'] if pd.notnull(r['result']) else ""
                    
                    supabase.table("project_logs").update({
                        "status": clean_status, 
                        "result": clean_result
                    }).eq("id", r['id']).execute()
                st.success("Zapisano decyzje!")
                st.rerun()
        else: st.info("Brak decyzji.")

    with tab_iss:
        recs = supabase.table("project_logs").select("*").eq("type", "ISSUE").execute().data or []
        if recs:
            df = pd.DataFrame(recs)
            ed = st.data_editor(df[['id', 'title', 'severity', 'status']], key="ed_iss", width="stretch")
            if st.button("Zapisz zmiany (Problemy)"):
                for _, r in ed.iterrows():
                    # Czyścimy dane z NaN
                    clean_status = r['status'] if pd.notnull(r['status']) else "OPEN"
                    clean_sev = r['severity'] if pd.notnull(r['severity']) else "MEDIUM"
                    
                    supabase.table("project_logs").update({
                        "status": clean_status, 
                        "severity": clean_sev
                    }).eq("id", r['id']).execute()
                st.success("Zapisano problemy!")
                st.rerun()
        else: st.info("Brak problemów.")
            
        st.divider()
        st.subheader("Przekształć w zadanie (Genialny Workflow)")
        st.caption("Masz problem, który chcesz zamienić na zadanie do wykonania? Połączmy je.")

elif menu == "settlements":
    st.title("💰 Centrum Rozliczeń Finansowych")
    st.caption("Zatwierdzaj wypłaty dla ekipy na podstawie modelu 50/100 i postępów prac.")
    
    # --- DANE FINANSOWE & PROGNOZY ---
    limit_res = calculate_hybrid_payment_limit(project_meta['id'])
    
    # Render professional financial status panel
    with st.container(border=True):
        st.write("### 📊 Status Finansowy Projektu")
        st.caption("Podsumowanie limitów wypłat w oparciu o postęp prac i model rozliczeniowy 50/100.")
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Dostępny limit wypłat", money(limit_res.get("available", 0.0)))
        c2.metric("💳 Wypłacone / Oczekujące", money(limit_res.get("already_paid", 0.0)))
        c3.metric("🏠 Budżet projektu", money(limit_res.get("budget", 0.0)))
        
    # --- INDYWIDUALNA UMOWA PIĄTKOWEJ ZALICZKI ---
    with st.container(border=True):
        st.write("### 🗓️ Umówiona piątkowa zaliczka Ekipy")
        st.caption("Ustal stałą stawkę tygodniowych zaliczek dla szefa ekipy na ten remont. Zmiana umowy zastąpi poprzednią stawkę.")
        
        agreement_info = get_weekly_advance_amount_for_project(project_meta['id'])
        current_amount = agreement_info["amount"]
        agreement_source = agreement_info["source"]
        agreement_effective = agreement_info["effective_from"]
        agreement_note = agreement_info["note"]
        
        col_ag1, col_ag2 = st.columns(2)
        with col_ag1:
            st.markdown(f"**Aktualna stawka:** {money(current_amount)}")
            if agreement_source == "PROJECT_AGREEMENT":
                st.success("🤝 Ustalona indywidualnie dla tego remontu")
                if agreement_effective:
                    st.caption(f"📅 Obowiązuje od: **{agreement_effective}**")
            else:
                st.info("💡 Domyślna kwota systemowa (brak indywidualnej umowy)")
                
        with col_ag2:
            if agreement_note:
                st.markdown(f"**Ustalenia / Notatka:**\n*{agreement_note}*")
            else:
                st.markdown("**Notatka:** Brak notatki")
                
        st.markdown("#### ⚙️ Zmień warunki umowy")
        with st.form("update_weekly_agreement_form", clear_on_submit=True):
            col_in1, col_in2 = st.columns(2)
            new_amount = col_in1.number_input("Nowa kwota zaliczki tygodniowej (PLN)", value=float(current_amount), min_value=100.0, step=100.0)
            new_note = col_in2.text_input("Uzasadnienie / Notatka ustaleń", value=agreement_note or "")
            if st.form_submit_button("💾 Zapisz umówioną zaliczkę dla tego remontu", type="primary", use_container_width=True):
                if new_amount <= 0:
                    st.error("Kwota zaliczki musi być większa od zera.")
                else:
                    create_or_update_weekly_advance_agreement(project_meta['id'], new_amount, new_note, created_by_role="INVESTOR")
                    add_activity_log(
                        st.session_state.get("user_name", "Inwestor"),
                        "FINANCIAL",
                        project_meta['id'],
                        f"Zmieniono umowę o piątkową zaliczkę na kwotę {money(new_amount)}"
                    )
                    st.success("✅ Nowa umowa została pomyślnie zapisana!")
                    time.sleep(1.5)
                    st.rerun()
                    
        # Opcjonalna historia zmian umowy
        try:
            res_all = supabase.table("project_logs")\
                .select("*")\
                .eq("project_id", project_meta['id'])\
                .eq("type", PAYMENT_LOG_TYPE)\
                .execute()
            all_logs = res_all.data or []
            ag_logs = [log for log in all_logs if is_weekly_advance_agreement_log(log)]
            ag_logs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            if ag_logs:
                st.markdown("#### 📜 Historia zmian umowy zaliczkowej")
                for al in ag_logs[:5]:
                    al_data = parse_project_log_data(al.get("data"))
                    al_amount = safe_float(al_data.get("agreed_weekly_amount"))
                    al_status = al.get("status")
                    al_date = al_data.get("effective_from") or al.get("created_at", "")[:10]
                    al_note = al.get("description") or al_data.get("note") or ""
                    
                    status_badge = "✅ AKTYWNA" if al_status == "ACTIVE" else "⏳ ZASTĄPIONA"
                    st.markdown(f"- **{money(al_amount)}** ({status_badge}) | Od: `{al_date}` | *{al_note}*")
        except Exception:
            pass

    # --- DEBUG PANEL (Zasada 1 - Tylko jeśli włączony w Secrets) ---
    show_finance_debug = False
    try:
        show_finance_debug = bool(st.secrets.get("SHOW_FINANCE_DEBUG", False))
    except Exception:
        pass
        
    if show_finance_debug:
        with st.expander("🛠️ DEBUG: Szczegóły Kalkulatora 50/100 (Tylko dla Inwestora)"):
            st.json(limit_res)
    
    # Pobieramy wnioski o płatność
    try:
        p_id = project_meta.get('id')
        reqs_raw = supabase.table("project_logs").select("*").eq("project_id", p_id).eq("type", PAYMENT_LOG_TYPE).order("created_at", desc=True).execute().data or []
        reqs_all = [r for r in reqs_raw if is_payment_request_log(r)]
        pending_requests = [r for r in reqs_all if r.get('status') == PAYMENT_STATUS_SUBMITTED]
        declared_requests = [r for r in reqs_all if r.get('status') == PAYMENT_STATUS_APPROVED_BY_INVESTOR]
        history_requests = [r for r in reqs_all if r.get('status') not in PAYMENT_OPEN_STATUSES]
    except Exception as e:
        st.error(f"⚠️ Błąd dostępu do bazy: {e}")
        pending_requests, declared_requests, history_requests = [], [], []
    
    # A) Wnioski oczekujące na decyzję (SUBMITTED)
    if not pending_requests:
        st.success("✅ Wszystkie wnioski oczekujące zostały przetworzone.")
    else:
        st.write(f"### Oczekujące wnioski ({len(pending_requests)})")
        for req in pending_requests:
            import json
            try:
                d = json.loads(req.get('data', '{}'))
                snapshot = d.get('limit_snapshot', {})
                req_amount = safe_float(d.get('amount'))
                req_type = d.get('payment_type', 'UNKNOWN')
                req_note = d.get('note', '')
            except:
                snapshot, req_amount, req_type, req_note = {}, 0.0, 'UNKNOWN', req.get('description', '')

            with st.container(border=True):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.subheader(f"Wniosek: {money(req_amount)}")
                    st.markdown(f"**Typ:** {get_payment_type_label(req_type)}")
                    if d.get("weekly_advance") or d.get("payment_subtype") == "WEEKLY_FRIDAY_ADVANCE":
                        st.info(f"🗓️ **Piątkowa zaliczka** | Tydzień: `{d.get('week_key', '—')}` | Planowany przelew: `{d.get('scheduled_payment_date', '—')}`")
                    st.write(f"📅 Data zgłoszenia: {req['created_at'][:10]} | Autor: **Szef Ekipy**")
                    if req_note: st.info(f"📝 Uzasadnienie: {req_note}")
                    
                    st.markdown(f"**Status:** {get_payment_status_label(req.get('status'))}")
                    st.caption(f"**Kolejny krok:** {get_payment_next_action_label(req.get('status'))}")
                    
                    if snapshot:
                        with st.expander("📊 SZCZEGÓŁY LIMITU 50/100 (Snapshot)"):
                            sc1, sc2 = st.columns(2)
                            sc1.write(f"**Ukończone (100%):** {money(snapshot.get('completed_val'))}")
                            sc1.write(f"**Zaliczki (50%):** {money(snapshot.get('advance_val'))}")
                            sc2.write(f"**Limit Brutto:** {money(snapshot.get('gross_limit'))}")
                            sc2.write(f"**Już pobrano:** {money(snapshot.get('already_paid'))}")
                            if snapshot.get('is_capped'): st.warning("Zastosowano Cap 30% budżetu.")
                
                with col2:
                    st.write("### Decyzja")
                    
                    inv_note = st.text_input("Notatka dla Ekipy (opcjonalnie)", key=f"inv_note_{req['id']}")
                    trans_date = st.date_input("Planowana data przelewu", value=date.today(), key=f"trans_d_{req['id']}")
                    
                    selected_material_id = None
                    if req_type == 'REIMBURSEMENT':
                        st.write("---")
                        st.caption("Powiąż ten zwrot z materiałem / pozycją budżetową (opcjonalne)")
                        mats = []
                        try:
                            mats_res = supabase.table("materials").select("id, name").eq("project_id", p_id).execute()
                            mats = mats_res.data or []
                        except Exception as e:
                            pass # Tabela 'materials' może jeszcze nie istnieć w bazie
                        
                        options = [{"id": None, "name": "Nie przypisuj"}] + mats
                        
                        def format_mat_option(opt):
                            return opt["name"]
                            
                        selected_opt = st.selectbox(
                            "Wybierz materiał",
                            options=options,
                            format_func=format_mat_option,
                            key=f"mat_sel_{req['id']}",
                            label_visibility="collapsed"
                        )
                        selected_material_id = selected_opt["id"]
                        st.caption("Powiązanie jest opcjonalne. Jeśli paragon dotyczy kilku różnych materiałów, zostaw bez przypisania albo poproś o osobne zgłoszenia.")
                    
                    if st.button("✅ Zatwierdź i zadeklaruj przelew", key=f"app_req_A_{req['id']}", use_container_width=True, type="primary"):
                        res = approve_payment_request_by_investor(req['id'], inv_note, trans_date, material_id=selected_material_id)
                        if res['status'] == 'ok':
                            add_activity_log("Inwestor", "FINANCIAL", p_id, f"Zatwierdzono wniosek {req_type}: {money(req_amount)}")
                            st.success("✅ Zatwierdzono! Ekipa została powiadomiona o przelewie.")
                            time.sleep(1.5)
                            st.rerun()
                        else:
                            st.error(f"❌ {res['message']}")
                    
                    st.write("---")
                    with st.expander("❌ Odrzuć wniosek"):
                        rej_reason = st.text_input("Powód odrzucenia (wymagany)", key=f"rej_reason_{req['id']}")
                        if st.button("Potwierdź odrzucenie", key=f"rej_conf_{req['id']}", use_container_width=True):
                            if not rej_reason.strip():
                                st.error("❌ Musisz podać powód odrzucenia.")
                            else:
                                res = reject_payment_request_by_investor(req['id'], rej_reason)
                                if res['status'] == 'ok':
                                    add_activity_log("Inwestor", "FINANCIAL", p_id, f"Odrzucono wniosek {req_type}: {money(req_amount)}. Powód: {rej_reason}")
                                    st.warning("⚠️ Wniosek odrzucony.")
                                    time.sleep(1.5)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {res['message']}")

    # B) Wnioski zatwierdzone przez Inwestora (APPROVED_BY_INVESTOR) — oczekujące na Ekipę
    if declared_requests:
        st.write("---")
        st.write(f"### 💰 Zadeklarowane przelewy — Oczekiwanie na ruch Ekipy ({len(declared_requests)})")
        for req in declared_requests:
            import json
            try:
                d = json.loads(req.get('data', '{}'))
                req_amount = safe_float(d.get('amount'))
                req_type = d.get('payment_type', 'UNKNOWN')
                req_note = d.get('note', '')
                inv_note = d.get('investor_note', '')
                trans_date = d.get('transfer_date', '')
            except:
                req_amount, req_type, req_note, inv_note, trans_date = 0.0, 'UNKNOWN', req.get('description', ''), '', ''

            with st.container(border=True):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.subheader(f"Wniosek: {money(req_amount)}")
                    st.markdown(f"**Typ:** {get_payment_type_label(req_type)}")
                    if d.get("weekly_advance") or d.get("payment_subtype") == "WEEKLY_FRIDAY_ADVANCE":
                        st.info(f"🗓️ **Piątkowa zaliczka** | Tydzień: `{d.get('week_key', '—')}` | Planowany przelew: `{d.get('scheduled_payment_date', '—')}`")
                    st.write(f"📅 Data zgłoszenia: {req['created_at'][:10]} | Autor: **Szef Ekipy**")
                    if req_note: st.info(f"📝 Uzasadnienie Ekipy: {req_note}")
                    if inv_note: st.success(f"💬 Twoja notatka: {inv_note}")
                    if trans_date: st.write(f"📅 Zadeklarowana data przelewu: **{trans_date}**")
                
                with col2:
                    st.markdown(f"**Status:** {get_payment_status_label(req.get('status'))}")
                    st.caption(f"**Kolejny krok:** {get_payment_next_action_label(req.get('status'))}")

    # C) Archiwum rozliczeń (PAID, APPROVED, REJECTED)
    if history_requests:
        st.write("---")
        with st.expander(f"📜 Historia rozliczeń ({len(history_requests)})", expanded=False):
            for h in history_requests:
                status = h.get('status', 'APPROVED')
                
                raw_data = h.get('data')
                import json
                d = {}
                if isinstance(raw_data, dict):
                    d = raw_data
                elif isinstance(raw_data, str):
                    try:
                        d = json.loads(raw_data)
                    except:
                        pass
                
                amount = safe_float(d.get('amount')) if d else 0.0
                p_type = d.get('payment_type', 'UNKNOWN') if d else 'UNKNOWN'
                note = d.get('note') or h.get('description') or 'Brak opisu'
                
                status_label = get_payment_status_label(status)
                
                with st.container(border=True):
                    sc1, sc2 = st.columns([3, 1])
                    with sc1:
                        st.markdown(f"#### {money(amount)} — {get_payment_type_label(p_type)}")
                        st.write(f"📅 Data: {h['created_at'][:10]} | Opis: {note}")
                        if d and (d.get("weekly_advance") or d.get("payment_subtype") == "WEEKLY_FRIDAY_ADVANCE"):
                            st.info(f"🗓️ **Piątkowa zaliczka** | Tydzień: `{d.get('week_key', '—')}` | Planowany przelew: `{d.get('scheduled_payment_date', '—')}`")
                        if d.get('investor_note'):
                            st.caption(f"Komentarz Inwestora: {d.get('investor_note')}")
                        if d.get('rejection_reason') or (status == PAYMENT_STATUS_REJECTED and h.get('description')):
                            reason = d.get('rejection_reason') or h.get('description')
                            st.caption(f"Powód odrzucenia: {reason}")
                    with sc2:
                        st.write(f"Status: **{status_label}**")

elif menu == "negotiations":
    st.title("🤝 Centrum Negocjacji i Handshake")
    st.write("Tu negocjujesz wyceny i blokujesz budżet robót pod pełną kontrolą.")
    
    # Pobieramy metadane projektu dla walidacji budżetu
    p_meta = get_project_metadata()
    total_budget = p_meta.get('total_budget', 0) if p_meta else 0

    try:
        all_tasks = supabase.table("tasks").select("*").eq("project_id", p_meta['id']).execute().data or [] if p_meta else []
        tasks = [t for t in all_tasks if "--- DANE NEGOCJACYJNE ---" in (t.get('description') or '')]
        # Wykluczamy zablokowane
        tasks = [t for t in tasks if "COMMERCIAL: ACCEPTED_LOCKED" not in (t.get('description') or '')]
    except:
        tasks = []
        
    if not tasks:
        st.info("✅ Wszystkie wyceny zostały zatwierdzone. Brak oczekujących ofert.")
    else:
        # Obliczamy obecne zużycie budżetu
        locked_sum = sum([parse_handshake_data(t['description'])['price'] for t in all_tasks if "COMMERCIAL: ACCEPTED_LOCKED" in (t.get('description') or '')])
        remaining_b = total_budget - locked_sum
        
        st.metric("Pozostały Budżet Projektu", f"{remaining_b:,.2f} PLN", f"Limit: {total_budget:,.2f}")
        st.progress(min(1.0, locked_sum / total_budget) if total_budget > 0 else 0)

        for t in tasks:
            with st.container(border=True):
                h = parse_handshake_data(t['description'])
                c_status, e_status, crew_p, last_msg = h['commercial'], h['execution'], h['price'], h['comment']

                c1, c2, c3 = st.columns([2, 1, 1])
                with c1:
                    st.subheader(f"📍 {t.get('name', 'Bez nazwy')}")
                    st.write(f"Status Finansowy: **{c_status}**")
                    clean_desc = t['description'].split("------------------------")[-1].strip() if "------------------------" in t['description'] else t['description']
                    st.write(f"Zakres: {clean_desc}")
                    if last_msg: st.caption(f"💬 Ostatni komentarz: {last_msg}")
                
                with c2:
                    st.metric("Oferta (PLN)", f"{crew_p:,.2f}")
                    # Sprawdzamy czy to zadanie mieści się w reszcie budżetu
                    can_acc, budget_msg = validate_project_budget(t['project_id'], crew_p)
                    if not can_acc: st.error(budget_msg)
                    elif "🟡" in budget_msg: st.warning(budget_msg)
                
                with c3:
                    st.write("📈 **Wpływ na budżet**")
                    new_rem = remaining_b - crew_p
                    st.write(f"Zostanie: **{new_rem:,.2f} PLN**")

                st.divider()
                col_a, col_b, col_c = st.columns(3)
                
                if col_a.button(f"✅ ZAAKCEPTUJ", key=f"acc_{t['id']}", type="primary", disabled=not can_acc):
                    if process_task_handshake(t['id'], "ACCEPT", "investor", price=crew_p, comment="Zaakceptowano ofertę Szefa Ekipy"):
                        st.success("Zatwierdzono i zablokowano!")
                        st.rerun()
                
                new_p = col_b.number_input("Kontroferta", value=float(crew_p), step=100.0, key=f"newp_{t['id']}")
                msg = st.text_input("Uzasadnienie", key=f"msg_{t['id']}")
                if col_b.button("↩️ WYŚLIJ KONTROFERTĘ", key=f"cnt_{t['id']}"):
                    if process_task_handshake(t['id'], "COUNTER_OFFER", "investor", price=new_p, comment=msg):
                        st.success("Wysłano do Szefa Ekipy.")
                        st.rerun()
                
                with col_c:
                    confirm_off = st.checkbox("Uzgodnione poza tel.", key=f"chk_{t['id']}")
                    if st.button("🔒 ZABLOKUJ CENĘ", key=f"lockoff_{t['id']}", disabled=not confirm_off or not can_acc):
                        if process_task_handshake(t['id'], "LOCK_OFFLINE", "investor", price=new_p, comment="Uzgodniono poza systemem"):
                            st.success("Zablokowano.")
                            st.rerun()

elif menu == "settings":
    st.title("🏠 Pomieszczenia do remontu")
    
    p_meta = get_project_metadata()
    p_id = p_meta.get('id') if p_meta else None
    
    if not p_id:
        st.warning("⚠️ Brak wybranego projektu w sesji! Wybierz projekt, by konfigurować pokoje.")
        st.stop()
        
    st.subheader("🏠 Podziel mieszkanie na poszczególne pomieszczenia")
    st.write("Wpisz tu pokoje, z których Szef Ekipy będzie mógł budować swój harmonogram.")
    
    with st.form("add_room_form", clear_on_submit=True):
        col1, col2 = st.columns([3, 1])
        new_room_name = col1.text_input("Nazwa nowego pomieszczenia (np. Sypialnia, Łazienka)")
        if col2.form_submit_button("➕ Dodaj do remontu", use_container_width=True):
            if new_room_name:
                try:
                    supabase.table("rooms").insert({"name": new_room_name, "project_id": p_id}).execute()
                    st.success(f"Dodano pokój: {new_room_name}")
                    st.rerun()
                except Exception as e:
                    if "duplicate key value" in str(e).lower() or "unique constraint" in str(e).lower() or "PGRST116" in str(e) or "23505" in str(e):
                        st.warning(f"⚠️ Pokój '{new_room_name}' już znajduje się w słowniku!")
                    else:
                        st.error(f"Nie udało się dodać pokoju. Błąd: {str(e)}")
            else:
                st.error("Podaj nazwę pokoju.")
                
    st.write("### Edycja istniejących pomieszczeń")
    
    # Bezpieczne pobranie tylko pokoi dla TEGO konkretnego projektu
    rooms_data = supabase.table("rooms").select("*").eq("project_id", p_id).execute().data
    # Budujemy słownik id->old_name PRZED renderowaniem edytora
    old_names_by_id = {r['id']: r['name'] for r in rooms_data} if rooms_data else {}
    df_r = pd.DataFrame(rooms_data) if rooms_data else pd.DataFrame()
    
    if not df_r.empty:
        edited_r = st.data_editor(df_r[['id', 'name']], disabled=["id"], hide_index=True, width="stretch")
        if st.button("💾 Zapisz zmiany w nazwach", type="primary"):
            updated = 0
            for _, row in edited_r.iterrows():
                room_id = row['id']
                new_name = row['name']
                old_name = old_names_by_id.get(room_id, '')
                # 1. Zawsze zapisz nową nazwę w rooms
                supabase.table("rooms").update({"name": new_name}).eq("id", room_id).execute()
                # 2. SYNCHRONIZACJA z project_phases (jeśli nazwa się zmieniła)
                if old_name and old_name != new_name:
                    supabase.table("project_phases")\
                        .update({"phase_name": new_name})\
                        .eq("project_id", p_id)\
                        .eq("phase_name", old_name)\
                        .execute()
                    updated += 1
            st.success(f"✅ Nazwy zapisane! Zaktualizowano {updated} pomieszczeń również w planie Szefa Ekipy.")
            st.rerun()
    else:
        st.info("Słownik jest pusty. Dodaj pierwszy pokój powyżej.")
            
    st.divider()
    st.subheader("📊 Eksport Danych Księgowych")
    st.caption("Pobierz całą historię finansową do pliku CSV (Otworzysz go w Excelu).")
    df_exp_full = read_table("expenses", filters={"project_id": p_id, "is_deleted": False})
    if not df_exp_full.empty:
        csv = df_exp_full.to_csv(index=False).encode('utf-8')
        st.download_button("Pobierz historię wydatków (CSV)", data=csv, file_name="remontiq_wydatki.csv", mime="text/csv")
    else:
        st.info("Brak wprowadzonych wydatków.")
        
    st.divider()
    st.subheader("🔒 Bezpieczeństwo")
    st.info("Logowanie do aplikacji odbywa się poprzez kody PIN. Edycja PIN-ów jest bezpiecznie przechowywana w pliku `.streamlit/secrets.toml` na serwerze.")
