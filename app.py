import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
import hashlib
import time
from typing import List, Dict
from supabase import create_client, Client
import plotly.graph_objects as go

APP_VERSION = "sprint23-50-100-deploy-fix-004"

# ==========================================
# 1. SUPABASE CONNECTION (Chmura)
# ==========================================

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
    "TO_BE_VALUED": "❓ Do wyceny (Karol)",
    "PROPOSED_BY_CREW": "👷 Propozycja Karola",
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
        p_meta = supabase.table("projects").select("total_budget").eq("id", project_id).single().execute().data
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

def get_project_metadata():
    try:
        res = supabase.table("project_metadata").select("*").order("created_at", desc=True).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"❌ Błąd pobierania metadanych: {e}")
        return None

def create_project_metadata(**kwargs):
    try:
        if 'planned_start_date' in kwargs and isinstance(kwargs['planned_start_date'], date):
            kwargs['planned_start_date'] = kwargs['planned_start_date'].isoformat()
        if 'planned_end_date' in kwargs and isinstance(kwargs['planned_end_date'], date):
            kwargs['planned_end_date'] = kwargs['planned_end_date'].isoformat()
        return supabase.table("project_metadata").insert(kwargs).execute()
    except Exception as e:
        st.error(f"❌ Błąd tworzenia projektu w Supabase: {e}")
        st.info("Prawdopodobna przyczyna: Brak kolumny w tabeli project_metadata lub brak uprawnień (RLS).")
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
        add_activity_log("Karol", "task_started", task_id, details="▶️ Rozpoczęto pracę")
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
            add_activity_log("Karol", "task_paused", task_id, details=f"⏸️ Pauza ({round(dur, 2)}h)")
            return {"success": True, "duration_hours": round(dur, 2)}
        return {"success": False}
    except Exception as e:
        st.error(f"❌ Błąd stop: {e}")
        return {"success": False}

def complete_task_v2(task_id: str, crew_member_id: str):
    try:
        stop_task_timer_v2(task_id, crew_member_id)
        supabase.table("tasks").update({"kanban_status": TASK_STATUSES["AWAITING_INSPECTION"]}).eq("id", task_id).execute()
        add_activity_log("Karol", "task_completed", task_id, details="✅ Gotowe do odbioru")
        return True
    except: return False

def calculate_weekly_bonus_v2(project_id: str, crew_member_id: str):
    """Oblicza aktualną pensję i bonus dla Karola w bieżącym tygodniu."""
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

def render_crew_dashboard(project_id: str, crew_member_id: str, crew_name: str = "Karol"):
    # 1️⃣ HEADER
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #1e293b 0%, #334155 100%); padding: 25px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.1); margin-bottom: 25px;">
        <h1 style="color: white; margin: 0; font-size: 28px;">Dzień dobry, {crew_name}! 👋</h1>
        <p style="color: #94a3b8; margin: 5px 0 0 0;">Budowa: {datetime.now().strftime("%d.%m.%Y")}</p>
    </div>
    """, unsafe_allow_html=True)

    tab_today, tab_plan = st.tabs(["👷 DZIŚ", "📅 PLAN REMONTU"])

    with tab_today:
        earnings = calculate_weekly_bonus_v2(project_id, crew_member_id)
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"""
            <div style="background: #ffffff; border-radius: 20px; padding: 25px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); color: #1e293b;">
                <div style="font-size: 14px; font-weight: 700; color: #64748b; margin-bottom: 20px; text-transform: uppercase;">💰 TWOJA PENSJA</div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 32px; font-weight: 900;">{earnings['base'] + earnings['bonus_amt']} <span style="font-size: 16px;">PLN</span></span>
                    <span style="color: #22c55e; font-weight: bold;">+ {earnings['bonus_amt']} PLN Bonusu</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div style="background: #3b82f6; border-radius: 20px; padding: 25px; height: 100%; color: white; text-align: center;">
                <div style="font-size: 24px; font-weight: 900;">+{earnings['bonus_pct']}%</div>
                <div style="font-size: 10px; opacity: 0.8;">JAKOŚĆ PRACY</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("📋 Zadania na dziś")
        tasks = supabase.table("tasks").select("*").eq("project_id", project_id).neq("kanban_status", "DONE").execute().data or []
        
        if not tasks:
            st.info("Brak zadań na liście. Przejdź do zakładki PLAN, aby dodać nowe zadania.")
        else:
            for t in tasks:
                diff = t.get('difficulty', 'MEDIUM')
                diff_clr = "#22c55e" if diff == "EASY" else "#f59e0b" if diff == "MEDIUM" else "#ef4444"
                with st.container(border=True):
                    tc1, tc2 = st.columns([3, 1])
                    tc1.markdown(f"**{t.get('name') or t.get('task_name')}**")
                    tc1.caption(f"{diff} | {t.get('phase_name', 'Ogólne')} | {t.get('estimated_hours', 0)}h")
                    
                    if t['kanban_status'] == "TODO":
                        if tc2.button("▶️ START", key=f"s_{t['id']}", use_container_width=True):
                            start_task_timer_v2(t['id'], crew_member_id)
                            st.rerun()
                    elif t['kanban_status'] == "IN_PROGRESS":
                        if tc2.button("✅ KONIEC", key=f"d_{t['id']}", use_container_width=True, type="primary"):
                            complete_task_v2(t['id'], crew_member_id)
                            st.rerun()
                        if tc2.button("⏸️ PAUZA", key=f"p_{t['id']}", use_container_width=True):
                            stop_task_timer_v2(t['id'], crew_member_id)
                            st.rerun()

    with tab_plan:
        st.markdown("### 🏗️ Buduj Plan Remontu")
        st.write("Tu dodajesz zadania, które Inwestor zobaczy w swoim Centrum Kontroli.")
        
        with st.expander("➕ DODAJ NOWE ZADANIE", expanded=True):
            with st.form("new_task_by_crew", clear_on_submit=True):
                t_name = st.text_input("Nazwa zadania (np. Gładzie w salonie)")
                t_phase = st.selectbox("Faza", ["1. Demolka", "2. Elektryka", "3. Hydraulika", "4. Ściany/Sufity", "5. Łazienka", "6. Podłogi", "7. Montaż końcowy"])
                t_diff = st.select_slider("Trudność (Wpływa na Twoją stawkę)", options=["EASY", "MEDIUM", "HARD"], value="MEDIUM")
                t_hours = st.number_input("Ile godzin to zajmie? (Estymacja)", min_value=1, value=8)
                t_desc = st.text_area("Uwagi do zadania (dla Inwestora)")
                
                if st.form_submit_button("🚀 DODAJ DO PLANU", use_container_width=True):
                    if t_name:
                        new_task = {
                            "project_id": project_id,
                            "task_name": t_name,
                            "name": t_name,
                            "description": t_desc,
                            "phase_name": t_phase,
                            "difficulty": t_diff,
                            "estimated_hours": t_hours,
                            "kanban_status": "TODO",
                            "created_by_crew": True
                        }
                        supabase.table("tasks").insert(new_task).execute()
                        st.success(f"Dodano zadanie: {t_name}")
                        st.rerun()
                    else: st.error("Podaj nazwę zadania!")

        st.markdown("---")
        st.subheader("🗺️ Przegląd wszystkich faz")
        all_tasks = supabase.table("tasks").select("*").eq("project_id", project_id).execute().data or []
        if all_tasks:
            df_plan = pd.DataFrame(all_tasks)
            for phase, group in df_plan.groupby("phase_name"):
                with st.expander(f"📍 {phase} ({len(group)} zadań)"):
                    for _, row in group.iterrows():
                        st.write(f"- {row['task_name']} ({row['difficulty']} | {row['estimated_hours']}h) - **{row['kanban_status']}**")
        else:
            st.info("Plan jest jeszcze pusty. Dodaj pierwsze zadania powyżej.")

    # 4️⃣ CENTRUM ZGŁOSZEŃ (Globalne)
    with st.sidebar:
        st.divider()
        if st.button("🚪 Wyloguj"): logout()

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
st.sidebar.caption(f"🚀 Wersja: {APP_VERSION}")

# ==========================================
# SPRINT 23 — HYBRID PAYMENT 50/100 (Ścieżka A+)
# ==========================================

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
    h = parse_handshake_data(task.get('description', ''))
    locked_price = h['price']
    commercial_status = h['commercial']
    execution_status = h['execution']

    if locked_price <= 0:
        return {"eligibility_percent": 0.0, "eligible_value": 0.0, "type": "NO_PRICE", "reason": "Brak ceny."}

    if commercial_status != rules["required_commercial_status"]:
        return {"eligibility_percent": 0.0, "eligible_value": 0.0, "type": "NOT_LOCKED", "reason": "Cena niezaakceptowana."}

    if execution_status in rules["final_eligible_execution_statuses"]:
        return {"eligibility_percent": rules["done_percent"], "eligible_value": locked_price * rules["done_percent"], "type": "FINAL_100", "reason": "Zadanie DONE (100%)"}

    if execution_status in rules["advance_eligible_execution_statuses"]:
        return {"eligibility_percent": rules["advance_percent"], "eligible_value": locked_price * rules["advance_percent"], "type": "ADVANCE_50", "reason": "Zadanie Aktywne (50%)"}

    if execution_status in rules["blocked_execution_statuses"]:
        return {"eligibility_percent": rules["blocked_percent"], "eligible_value": 0.0, "type": "BLOCKED", "reason": "Zadanie zablokowane (0%)"}

    return {"eligibility_percent": 0.0, "eligible_value": 0.0, "type": "OTHER", "reason": "Status niekwalifikowany."}

# --- GŁÓWNY KALKULATOR LIMITU ---
def calculate_hybrid_payment_limit(project_id):
    try:
        p_meta = supabase.table("projects").select("*").eq("id", project_id).single().execute().data
        budget = safe_float(p_meta.get('total_budget') or p_meta.get('budget'))
        
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
        logs = supabase.table("project_logs").select("*").eq("project_id", project_id).eq("type", "payment_request").execute().data or []
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
# 🚀 SYSTEM NAWIGACJI SaaS (Multi-Role)
# ==========================================

# 1. Pobranie metadanych projektu (Wspólne)
project_meta = get_project_metadata()
proj_name = project_meta['project_name'] if project_meta else "Brak projektu"
role_name = "Inwestor" if st.session_state['role'] == "investor" else "Ekipa (Karol)"

# 2. Renderowanie Górnego Bara (Wspólne)
render_top_bar(proj_name, role_name, st.session_state.get('user_name', 'Użytkownik'))

# 3. Definicja Menu w Sidebarze (Zależna od Roli)
if st.session_state['role'] == "crew":
    st.sidebar.markdown("### 🛠️ ZARZĄDZANIE")
    if st.sidebar.button("📝 PLAN REMONTU", use_container_width=True, type="primary"):
        st.session_state['crew_menu_active'] = "planowanie"
        st.rerun()
    
    st.sidebar.divider()
    menu = st.sidebar.radio("👷 NAWIGACJA", [
        "🚀 Plan na dzisiaj",
        "🚨 Blokady i Materiały",
        "💬 Czat Budowy"
    ])
    
    st.sidebar.divider()
    if st.sidebar.button("💰 MOJE FINANSE", use_container_width=True):
        st.session_state['crew_menu_active'] = "finanse"
        st.rerun()
    
    if st.sidebar.button("🚪 Wyloguj", use_container_width=True):
        logout()
        st.rerun()
else:
    # Definicja stron Inwestora (Klucz techniczny : Etykieta widoczna)
    INVESTOR_PAGES = {
        "dashboard": "1. 🏠 Dashboard Inwestora",
        "tasks": "2. 📋 Plan Remontu (Zadania)",
        "crew_view": "3. 👷 Widok Ekipy",
        "schedule": "4. 📅 Harmonogram",
        "budget": "5. 💰 Budżet i Wydatki",
        "crews": "6. 👷 Ekipy i Wykonawcy",
        "journal": "7. 📒 Dziennik Projektu (Decyzje/Ryzyka)",
        "settlements": "8. 📈 Wyceny i Rozliczenia",
        "negotiations": "9. 🤝 Negocjacje i Planowanie",
        "settings": "10. ⚙️ Ustawienia Projektu",
        "charter": "0. Charter Projektu",
        "logout": "🚪 Wyloguj"
    }
    
    selected_key = st.sidebar.radio(
        "Nawigacja", 
        options=list(INVESTOR_PAGES.keys()),
        format_func=lambda x: INVESTOR_PAGES[x]
    )
    menu = selected_key # Mapujemy dla kompatybilności wstecznej

# 4. Globalna Logika Wylogowania
if menu == "logout":
    logout()
    st.rerun()

# 5. Blokada dla Ekipy (Nowy Workflow)
if st.session_state['role'] == "crew":
    p_id = project_meta.get('id') if project_meta else None
    
    # --- EKRAN POWITALNY (Splash) ---
    if "splash_done" not in st.session_state: st.session_state.splash_done = False
    
    if not st.session_state.splash_done:
        st.markdown(f"""
        <div style="height: 70vh; display: flex; flex-direction: column; justify-content: center; align-items: center; background: linear-gradient(135deg, #1e293b 0%, #334155 100%); border-radius: 30px; color: white; text-align: center; padding: 40px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.3);">
            <div style="font-size: 100px; margin-bottom: 20px;">🏗️</div>
            <h1 style="font-size: 50px; font-weight: 900; margin: 0;">DZIEŃ DOBRY KAROL!</h1>
            <p style="font-size: 24px; opacity: 0.8; margin-top: 10px;">Dziś jest {datetime.now().strftime('%A, %d.%m.%Y')}</p>
            <p style="font-size: 18px; margin-top: 30px; font-style: italic;">"Dobry plan to połowa sukcesu."</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🚀 WEJDŹ NA BUDOWĘ", use_container_width=True, type="primary"):
            st.session_state.splash_done = True
            st.rerun()
        st.stop()
    
    # Obsługa przycisków funkcyjnych
    if st.session_state.get('crew_menu_active') == "planowanie":
        st.title("📅 Planowanie Remontu")
        st.info("Karol, tu układasz harmonogram i fazy.")
        if st.button("⬅️ Powrót"):
            st.session_state['crew_menu_active'] = None
            st.rerun()
        st.stop()
        
    if st.session_state.get('crew_menu_active') == "finanse":
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 30px; border-radius: 20px; color: white; margin-bottom: 25px;">
            <h1 style="margin:0; font-size: 32px;">💰 Moje Finanse</h1>
            <p style="opacity: 0.7; margin: 5px 0 0 0;">Centrum rozliczeń i wycen kontraktu</p>
        </div>
        """, unsafe_allow_html=True)
        
        tab_valuation, tab_settlement = st.tabs(["📐 WYCENA ETAPÓW", "💸 ROZLICZENIE OKRESOWE"])
        
        with tab_valuation:
            st.subheader("🛠️ Planowanie i Wycena Robót")
            
            # --- FORMULARZ DODAWANIA ZADANIA PRZEZ KAROLA ---
            with st.expander("➕ DODAJ NOWĄ ROBOTĘ / ETAP"):
                with st.form("form_crew_add_task"):
                    t_title = st.text_input("Nazwa roboty *")
                    t_desc = st.text_area("Opis techniczny")
                    col_p1, col_p2 = st.columns(2)
                    t_price = col_p1.number_input("Twoja wycena (PLN) *", min_value=0.0, step=100.0)
                    t_hours = col_p2.number_input("Szacowane godziny", min_value=1.0, step=1.0)
                    
                    if st.form_submit_button("Weryfikuj i wyślij do Inwestora"):
                        if t_title and t_price > 0:
                            # Tagi Handshake 2.1 (Zawsze w opisie dla kompatybilności)
                            full_desc = f"--- DANE NEGOCJACYJNE ---\nCOMMERCIAL: PROPOSED_BY_CREW\nEXECUTION: NOT_READY\nCENA: {t_price}\n------------------------\n\n{t_desc}"
                            
                            # Budujemy payload RLS-Compliant
                            payload = {
                                "name": t_title,
                                "description": full_desc,
                                "kanban_status": "BACKLOG",
                                "commercial_status": "PROPOSED_BY_CREW",
                                "execution_status": "NOT_READY"
                            }
                            
                            # KROK KRYTYCZNY: Dodajemy autora dla RLS
                            u_id = st.session_state.get('user_id')
                            session = supabase.auth.get_session()
                            
                            if not session:
                                st.warning("⚠️ Uwaga: Brak aktywnej sesji technicznej w Supabase (Session Valid: False).")
                                st.info("Jeśli błąd 42501 nadal występuje, wykonaj w SQL Editor: `ALTER TABLE tasks DISABLE ROW LEVEL SECURITY;` lub użyj SERVICE_ROLE_KEY.")
                            
                            if u_id:
                                payload["created_by"] = u_id
                                payload["user_id"] = u_id
                            
                            if p_id:
                                payload["project_id"] = p_id
                                payload["projekt_id"] = p_id
                            
                            try:
                                # Próba 1: Pełny payload
                                supabase.table("tasks").insert(payload).execute()
                                st.success("✅ Wysłano propozycję!")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                # Próba 2: Minimalny payload (jeśli baza nie ma nowych kolumn)
                                try:
                                    minimal_payload = {"name": t_title, "description": full_desc, "project_id": p_id}
                                    supabase.table("tasks").insert(minimal_payload).execute()
                                    st.success("✅ Wysłano (tryb uproszczony)!")
                                    st.rerun()
                                except Exception as e2:
                                    st.error(f"Krytyczny błąd RLS/Schema: {e2}")
                                    st.info("💡 Sprawdź w Supabase czy masz politykę INSERT dla roli authenticated.")
                        else:
                            st.error("Podaj nazwę i cenę!")

            st.divider()
            
            # --- LISTA ZADAŃ DO WYCENY / NEGOCJACJI ---
            st.write("### Twoje zadania i negocjacje")
            try:
                all_t = supabase.table("tasks").select("*").eq("project_id", p_id).execute().data or []
                tasks = [t for t in all_t if "--- DANE NEGOCJACYJNE ---" in (t.get('description') or '')]
                # Wykluczamy te już zablokowane (LOCKED)
                tasks = [t for t in tasks if "COMMERCIAL: ACCEPTED_LOCKED" not in (t.get('description') or '')]
            except:
                tasks = []
            
            if tasks:
                for t in tasks:
                    h = parse_handshake_data(t['description'])
                    c_status, crew_p, last_msg = h['commercial'], h['price'], h['comment']
                    
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.write(f"**{t.get('name', 'Bez nazwy')}**")
                            st.caption(f"Status Finansowy: **{c_status}**")
                            
                            if c_status == "INVESTOR_COUNTERED":
                                st.warning(f"💼 **INWESTOR PROPONUJE KOREKTĘ: {crew_p:,.2f} PLN**")
                                if last_msg: st.info(f"Uzasadnienie: {last_msg}")
                                
                                b1, b2 = st.columns(2)
                                if b1.button("🤝 Akceptuję propozycję", key=f"crew_acc_{t['id']}", type="primary"):
                                    process_task_handshake(t['id'], "LOCK_OFFLINE", "crew", price=crew_p, comment="Karol zaakceptował kontrofertę")
                                    st.success("Zaakceptowano! Zadanie trafia na tablicę.")
                                    st.rerun()
                                if b2.button("📐 Nowa wycena", key=f"crew_new_{t['id']}"):
                                    # Tu po prostu odświeżymy widok, żeby mógł wpisać nową cenę w formularzu wyżej
                                    st.info("Użyj formularza powyżej, aby wysłać nową wycenę.")
                            
                            elif c_status == "PROPOSED_BY_CREW":
                                st.info("⏳ Czekamy na ruch Inwestora...")
                                
                        with c2:
                            st.metric("Ostatnia kwota", f"{crew_p:,.2f}")
            else:
                st.info("Brak aktywnych negocjacji. Wszystko zatwierdzone lub puste.")

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

            with st.form("payment_request_form_A_plus"):
                st.write("### 📤 Nowy wniosek")
                req_amount = st.number_input("Kwota wniosku (PLN)", min_value=0.0, step=100.0, format="%.2f")
                req_note = st.text_area("Uzasadnienie / Cel wypłaty", placeholder="Np. Zakup materiałów, rozliczenie etapu...")
                
                # --- WALIDACJA TWARDA (Zasada 8) ---
                error_msg = None
                can_submit = True
                
                if req_amount > fin['available']:
                    error_msg = f"❌ Kwota przekracza limit ({money(fin['available'])})."
                    can_submit = False
                elif req_amount < PAYMENT_RULES["min_payment_request_amount"] and req_amount < fin['available'] and req_amount > 0:
                    error_msg = f"❌ Minimalna kwota to {money(PAYMENT_RULES['min_payment_request_amount'])}."
                    can_submit = False
                elif req_amount <= 0:
                    can_submit = False
                
                if error_msg: st.error(error_msg)
                
                if st.form_submit_button("Wyślij wniosek do Inwestora", type="primary", disabled=not can_submit):
                    # --- STRAŻNIK OSTATNIEJ SEKUNDY (Opcja 2 - Backend Validation) ---
                    # Przeliczamy limit jeszcze raz, tuż przed zapisem do bazy
                    fresh_fin = calculate_hybrid_payment_limit(p_id)
                    
                    if req_amount > fresh_fin['available']:
                        st.error(f"⚠️ Limit właśnie się zmienił! Aktualnie dostępne: {money(fresh_fin['available'])}. Spróbuj ponownie.")
                    else:
                        import json
                        payment_type = classify_payment_request(fresh_fin)
                        snapshot = build_payment_limit_snapshot(fresh_fin)
                        
                        log_data = {
                            "amount": req_amount,
                            "note": req_note,
                            "payment_type": payment_type,
                            "limit_snapshot": snapshot,
                            "timestamp": datetime.now().isoformat()
                        }
                        
                        # Zapisujemy jako wniosek o płatność
                        supabase.table("project_logs").insert({
                            "project_id": p_id,
                            "type": "payment_request",
                            "title": f"Wniosek ({payment_type}): {money(req_amount)}",
                            "description": req_note,
                            "data": json.dumps(log_data),
                            "status": "SUBMITTED"
                        }).execute()
                        
                        # Dodatkowy log audytowy
                        add_activity_log("Karol", "FINANCIAL", p_id, f"Złożono wniosek {payment_type} na kwotę {money(req_amount)}")
                        
                        st.success("✅ Wniosek wysłany!")
                        time.sleep(1)
                        st.rerun()

            st.divider()
            with st.form("material_reimbursement_form"):
                st.write("### 🛒 Zwrot za materiały")
                st.caption("Użyj tego formularza, jeśli kupiłeś materiały za własne pieniądze.")
                reimb_amount = st.number_input("Kwota z paragonu/faktury (PLN)", min_value=0.0, step=10.0)
                reimb_note = st.text_input("Na co wydano? (krótki opis)")
                
                if st.form_submit_button("Zgłoś wydatek do zwrotu"):
                    if reimb_amount > 0 and reimb_note:
                        import json
                        log_data = {
                            "amount": reimb_amount,
                            "note": reimb_note,
                            "payment_type": "REIMBURSEMENT",
                            "timestamp": datetime.now().isoformat()
                        }
                        supabase.table("project_logs").insert({
                            "project_id": p_id,
                            "type": "payment_request",
                            "title": f"Zwrot za materiały: {money(reimb_amount)}",
                            "description": reimb_note,
                            "data": json.dumps(log_data),
                            "status": "SUBMITTED"
                        }).execute()
                        add_activity_log("Karol", "FINANCIAL", p_id, f"Zgłoszono zwrot za materiały: {money(reimb_amount)}")
                        st.success("✅ Zgłoszono!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Podaj kwotę i opis zakupów.")

            st.divider()
            st.caption("ℹ️ Model Hybrydowy 50/100: 100% DONE | 50% TODO/IN_PROGRESS | 0% BLOCKED | Global Cap 30%.")
            

        if st.button("⬅️ Powrót do Zadania", use_container_width=True):
            st.session_state['crew_menu_active'] = None
            st.rerun()
        st.stop()

    if menu == "🚀 Plan na dzisiaj":
        render_crew_dashboard(p_id, "KAROL_ID", "Karol")
        
    elif menu == "🚨 Blokady i Materiały":
        st.title("🚨 Zgłoś problem")
    elif menu == "💬 Czat Budowy":
        st.title("💬 Czat")
    st.stop()

# --- DALSZA LOGIKA DLA INWESTORA ---
render_activity_banner("investor")

# Pomocnicza lista pokoi (Dla formularzy)
df_rooms = read_table("rooms", select="id, name")
rooms_dict = [{"id": None, "name": "Brak (Ogólne)"}]
for _, r in df_rooms.iterrows():
    rooms_dict.append({"id": r['id'], "name": r['name']})

if menu == "3. 👷 DASHBOARD EKIPY (v2.0)":
    p_meta = get_project_metadata()
    if p_meta:
        render_crew_dashboard(p_meta['id'], "KAROL_ID", "Karol") # KAROL_ID jako placeholder
    else:
        st.warning("Najpierw utwórz Charter Projektu.")

elif menu == "charter":
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
                    res = create_project_metadata(
                        project_name=project_name, project_description=project_desc,
                        planned_start_date=start_date, planned_end_date=end_date,
                        total_budget=total_budget, investor_name=investor_name,
                        crew_lead_name=crew_lead_name or "Nie wiadomo", crew_contact=crew_contact or "Brak",
                        scope_of_work=scope, special_conditions=conditions, status="PLANNING"
                    )
                    if res:
                        st.success("✅ Charter utworzony!")
                        st.rerun()
                    else:
                        st.error("❌ Nie udało się utworzyć projektu. Sprawdź komunikaty powyżej.")
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

elif menu == "dashboard":
    st.title("🎮 COMMAND CENTER")
    st.caption(f"Centrum kontroli projektu — {date.today().strftime('%d.%m.%Y')}")

    # ==============================
    # DANE
    # ==============================
    all_tasks_data = supabase.table("tasks").select("*").execute().data or []
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
        c1.metric("Postęp", f"{m['progress']}%", f"{d['completed']}/{d['total']}")
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

elif menu == "budget":
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

elif menu == "tasks":
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

elif menu == "inspections":
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

elif menu == "crew_view":
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
        recs = supabase.table("project_logs").select("*").eq("type", "DECISION").execute().data or []
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
    
    # --- DEBUG PANEL (Zasada 1) ---
    with st.expander("🛠️ DEBUG: Szczegóły Kalkulatora 50/100 (Tylko dla Inwestora)"):
        debug_fin = calculate_hybrid_payment_limit(project_meta['id'])
        st.json(debug_fin)
    
    # Pobieramy wnioski o płatność
    try:
        p_id = project_meta.get('id')
        reqs_all = supabase.table("project_logs").select("*").eq("project_id", p_id).eq("type", "payment_request").order("created_at", desc=True).execute().data or []
        pending_requests = [r for r in reqs_all if r.get('status') == 'SUBMITTED']
        history_requests = [r for r in reqs_all if r.get('status') != 'SUBMITTED']
    except Exception as e:
        st.error(f"⚠️ Błąd dostępu do bazy: {e}")
        pending_requests, history_requests = [], []
    
    if not pending_requests:
        st.success("✅ Wszystkie wnioski zostały przetworzone.")
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
                    
                    # Badge typu
                    if req_type == "ADVANCE": st.warning("💸 Typ: ZALICZKA (Prace w toku)")
                    elif req_type == "FINAL": st.success("✅ Typ: ROZLICZENIE KOŃCOWE (Prace DONE)")
                    elif req_type == "REIMBURSEMENT": st.error("🛒 Typ: ZWROT ZA MATERIAŁY (Wydatki własne)")
                    else: st.info("🔀 Typ: MIESZANY (Zaliczka + Prace DONE)")
                    
                    st.write(f"📅 Data: {req['created_at'][:10]} | Autor: **Karol**")
                    if req_note: st.info(f"📝 Uzasadnienie: {req_note}")
                    
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
                    if st.button("✅ ZATWIERDŹ", key=f"app_req_A_{req['id']}", use_container_width=True, type="primary"):
                        supabase.table("project_logs").update({"status": "APPROVED"}).eq("id", req['id']).execute()
                        add_activity_log("Inwestor", "FINANCIAL", p_id, f"ZATWIERDZONO wypłatę {req_type}: {money(req_amount)}")
                        st.success("Zatwierdzono!")
                        time.sleep(1)
                        st.rerun()
                    
                    if st.button("❌ ODRZUĆ", key=f"rej_req_A_{req['id']}", use_container_width=True):
                        reason = st.text_input("Powód odrzucenia", key=f"rej_reason_{req['id']}")
                        if st.button("Potwierdź odrzucenie", key=f"rej_conf_{req['id']}"):
                            supabase.table("project_logs").update({"status": "REJECTED", "description": reason}).eq("id", req['id']).execute()
                            add_activity_log("Inwestor", "FINANCIAL", p_id, f"ODRZUCONO wniosek: {money(req_amount)}. Powód: {reason}")
                            st.warning("Odrzucono.")
                            st.rerun()

    if history_requests:
        with st.expander(f"📜 Historia rozliczeń ({len(history_requests)})"):
            for h in history_requests:
                status_color = "green" if h['status'] == "APPROVED" else "red"
                st.write(f":{status_color}[{h['status']}] **{h['title']}** — {h['created_at'][:10]}")
                if h.get('description'): st.caption(f"Komentarz: {h['description']}")

elif menu == "negotiations":
    st.title("🤝 Centrum Negocjacji i Handshake")
    st.write("Tu negocjujesz wyceny i blokujesz budżet robót pod pełną kontrolą.")
    
    # Pobieramy metadane projektu dla walidacji budżetu
    p_meta = get_project_metadata()
    total_budget = p_meta.get('total_budget', 0) if p_meta else 0

    try:
        all_tasks = supabase.table("tasks").select("*").execute().data or []
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
                    if process_task_handshake(t['id'], "ACCEPT", "investor", price=crew_p, comment="Zaakceptowano ofertę Karola"):
                        st.success("Zatwierdzono i zablokowano!")
                        st.rerun()
                
                new_p = col_b.number_input("Kontroferta", value=float(crew_p), step=100.0, key=f"newp_{t['id']}")
                msg = st.text_input("Uzasadnienie", key=f"msg_{t['id']}")
                if col_b.button("↩️ WYŚLIJ KONTROFERTĘ", key=f"cnt_{t['id']}"):
                    if process_task_handshake(t['id'], "COUNTER_OFFER", "investor", price=new_p, comment=msg):
                        st.success("Wysłano do Karola.")
                        st.rerun()
                
                with col_c:
                    confirm_off = st.checkbox("Uzgodnione poza tel.", key=f"chk_{t['id']}")
                    if st.button("🔒 ZABLOKUJ CENĘ", key=f"lockoff_{t['id']}", disabled=not confirm_off or not can_acc):
                        if process_task_handshake(t['id'], "LOCK_OFFLINE", "investor", price=new_p, comment="Uzgodniono poza systemem"):
                            st.success("Zablokowano.")
                            st.rerun()

elif menu == "settings":
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
    st.subheader("📊 Eksport Danych Księgowych")
    st.caption("Pobierz całą historię finansową do pliku CSV (Otworzysz go w Excelu).")
    df_exp_full = read_table("expenses")
    if not df_exp_full.empty:
        csv = df_exp_full.to_csv(index=False).encode('utf-8')
        st.download_button("Pobierz historię wydatków (CSV)", data=csv, file_name="remontiq_wydatki.csv", mime="text/csv")
    else:
        st.info("Brak wprowadzonych wydatków.")
        
    st.divider()
    st.subheader("🔒 Bezpieczeństwo")
    st.info("Logowanie do aplikacji odbywa się poprzez kody PIN. Edycja PIN-ów jest bezpiecznie przechowywana w pliku `.streamlit/secrets.toml` na serwerze.")
