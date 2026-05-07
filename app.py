import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
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
    query = query.eq('is_deleted', False)
    if order_by:
        query = query.order(order_by[0], desc=order_by[1])
    res = query.execute()
    return pd.DataFrame(res.data)

def get_project_metadata():
    res = supabase.table("project_metadata").select("*").order("created_at", desc=True).limit(1).execute()
    return res.data[0] if res.data else None

def create_project_metadata(**kwargs):
    kwargs['created_by'] = "investor_user"
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

if "role" not in st.session_state:
    st.session_state["role"] = None

def logout():
    st.session_state["role"] = None
    st.rerun()

# --- EKRAN LOGOWANIA ---
if st.session_state["role"] is None:
    st.markdown("<h1 style='text-align: center;'>Witamy w Remont IQ</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Podaj PIN dostępu do aplikacji.</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            pin = st.text_input("PIN", type="password", placeholder="Wpisz 4-cyfrowy PIN")
            if st.form_submit_button("Zaloguj", use_container_width=True):
                inv_pin = st.secrets.get("auth", {}).get("investor_pin", "9999")
                crw_pin = st.secrets.get("auth", {}).get("crew_pin", "1234")
                if pin == str(inv_pin):
                    st.session_state["role"] = "investor"
                    st.rerun()
                elif pin == str(crw_pin):
                    st.session_state["role"] = "crew"
                    st.rerun()
                else:
                    st.error("Nieprawidłowy PIN!")
    st.stop()


# ==========================================
# WIDOK EKIPY BUDOWLANEJ
# ==========================================
if st.session_state["role"] == "crew":
    c1, c2 = st.columns([4, 1])
    c1.title("👷 Dashboard Ekipy")
    if c2.button("Wyloguj"): logout()
    
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
    
    # RAPORT DNIA EKIPY (Wrzucany do Dziennika Inwestora)
    with st.expander("📝 Dodaj Raport z prac (Dziennik)", expanded=True):
        with st.form("crew_log_form", clear_on_submit=True):
            log_txt = st.text_area("Co zostało dzisiaj zrobione? Jakieś opóźnienia?")
            if st.form_submit_button("Wyślij Raport do Inwestora"):
                if log_txt.strip():
                    supabase.table("daily_logs").insert({
                        "content": log_txt.strip(), 
                        "author_role": "crew", 
                        "source": "crew_report",
                        "date": str(date.today())
                    }).execute()
                    st.success("Wysłano raport do Dziennika Inwestora!")
                else:
                    st.error("Wpisz treść raportu.")

    st.subheader("1. Zgłoś zapotrzebowanie / Zablokowanie")
    with st.form("crew_req_form", clear_on_submit=True):
        col1, col2 = st.columns([3, 1])
        title = col1.text_input("Czego brakuje? (np. Fuga Mapei 110, pędzle)")
        needed = col2.date_input("Na kiedy potrzebne?")
        blocker = st.checkbox("Pilne: To wstrzymuje nasze prace!")
        if st.form_submit_button("Wyślij do Inwestora"):
            if not title.strip(): st.error("Musisz wpisać nazwę!")
            else:
                supabase.table("crew_requests").insert({"title": title, "needed_by": str(needed), "is_blocker": blocker}).execute()
                st.success("Wysłano prośbę do Inwestora!")
                st.rerun()
                
    st.divider()
    st.subheader("2. Materiały dostępne na miejscu")
    res_v = supabase.table("crew_materials_view").select("name, location, quantity_received, unit").execute()
    df_m = pd.DataFrame(res_v.data)
    if df_m.empty: st.info("Brak materiałów oznaczonych jako gotowe na budowie.")
    else:
        df_m.rename(columns={"name": "Materiał", "location": "Gdzie leży?", "quantity_received": "Ilość", "unit": "Jedn."}, inplace=True)
        st.dataframe(df_m, use_container_width=True, hide_index=True)
    st.stop() 


# ==========================================
# WIDOK INWESTORA
# ==========================================
st.sidebar.markdown("### 👤 Zalogowano jako: Inwestor")
if st.sidebar.button("Wyloguj"): logout()
st.sidebar.divider()

project_meta = get_project_metadata()
if project_meta:
    st.sidebar.markdown(f"### 🏗️ {project_meta['project_name']}")
    st.sidebar.caption(f"Status: {project_meta['status']}")
else:
    st.sidebar.warning("⚠️ Charter nie utworzony")

menu = st.sidebar.radio("Nawigacja", [
    "0. Charter Projektu",
    "1. Dashboard (Centrum)", 
    "2. Start remontu", 
    "3. Materiały i sprzęty", 
    "4. Zadania", 
    "5. Ekipa", 
    "6. Wydatki (Finanse)",
    "7. Decyzje", 
    "8. Ryzyka", 
    "9. Dziennik", 
    "10. Ustawienia"
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
            
            if st.form_submit_button("🚀 UTWÓRZ CHARTER PROJEKTU", use_container_width=True, type="primary"):
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
        st.plotly_chart(fig, use_container_width=True)
        
        st.divider()
        st.subheader("📍 Status i kontrola")
        days_info = get_project_days_info(project_meta)
        
        if project_meta['status'] == "PLANNING":
            st.warning("🟡 **Status: PLANOWANIE**")
            st.info("✅ **Checklist przed aktywacją:**\n- [ ] Materiały zamówione\n- [ ] Ekipa potwierdzona\n- [ ] Decyzje podjęte")
            if st.button("🚀 URUCHOM PROJEKT", use_container_width=True, type="primary"):
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
            if st.button("✅ Zakończ projekt", use_container_width=True, type="primary"):
                update_project_metadata(project_meta['id'], status="COMPLETED", actual_end_date=date.today())
                st.rerun()
        elif project_meta['status'] == "COMPLETED":
            st.success("✅ **Status: UKOŃCZONY**")

elif menu == "1. Dashboard (Centrum)":
    st.title("📌 Remont IQ Cloud - Dzisiaj")
    st.subheader("🏠 Inwestycja Mostek 2")
    st.markdown("---")
    if not project_meta or project_meta['status'] != "ACTIVE":
        st.warning("⚠️ Projekt wciąż w fazie PLANOWANIA. Po aktywacji (w Module 0) zobaczysz tutaj analizę i ostrzeżenia.")
    else:
        st.subheader("🔥 Najważniejsze teraz (Top 5)")
        recs = calculate_smart_recommendations()
        if recs.empty: st.success("Brak pożarów! Wygląda na to, że masz wszystko pod kontrolą.")
        else:
            for idx, row in recs.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([1, 4, 3])
                    c1.markdown(f"**{row['Typ']}**")
                    c2.markdown(f"**{row['Zadanie']}**")
                    c3.markdown(f"⚠️ {row['Powód']}")

    st.divider()
    
    st.subheader("📋 Status zadań Karola")
    tasks = get_tasks_with_dependencies()
    if tasks:
        c1, c2, c3, c4 = st.columns(4)
        backlog = len([t for t in tasks if t['status'] == 'Backlog'])
        in_progress = len([t for t in tasks if t['status'] == 'In Progress'])
        blocked = len([t for t in tasks if not t.get('all_dependencies_met', True)])
        done = len([t for t in tasks if t['status'] == 'Done'])
        c1.metric("📦 Backlog", backlog)
        c2.metric("🟧 W trakcie", in_progress)
        c3.metric("❌ Zablokowane", blocked)
        c4.metric("✅ Ukończone", done)
        
        st.write("**🚨 Przegląd zablokowanych zadań:**")
        blocked_tasks = [t for t in tasks if not t.get('all_dependencies_met', True)]
        if blocked_tasks:
            for task in blocked_tasks[:3]:
                can_start_result = can_task_start(task['id'])
                st.warning(f"⛔ **{task['name']}** — {can_start_result['reason']}")
        else:
            st.success("✅ Żadne zadania nie są zablokowane!")
    else:
        st.info("Czekamy na plan Karola...")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🛠️ Zgłoszenia od ekipy")
        reqs = read_table("crew_requests", filters={"status": "Do zrobienia"})
        if reqs.empty: st.success("Ekipa ma wszystko, czego potrzebuje.")
        else: st.dataframe(reqs[['title', 'needed_by']], hide_index=True)
    with col2:
        st.subheader("📦 Materiały na budowie")
        mats_ok = read_table("materials", filters={"available_for_crew": True})
        st.markdown("**✅ Na miejscu (Dostępne):**")
        if mats_ok.empty: st.caption("Brak materiałów")
        else: 
            for _, m in mats_ok.iterrows(): st.caption(f"- {m['name']}")

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
        st.dataframe(df_r_view[['name', 'budget', 'created_at']], hide_index=True)
    else:
        st.info("Brak wprowadzonych pomieszczeń.")

elif menu == "3. Materiały i sprzęty":
    st.title("📦 Materiały i Sprzęty")
    
    with st.expander("➕ Dodaj nowy materiał"):
        with st.form("new_mat", clear_on_submit=True):
            m_name = st.text_input("Nazwa materiału *")
            m_room = st.selectbox("Przypisz do pomieszczenia:", options=rooms_dict, format_func=lambda x: x['name'])
            c1, c2 = st.columns(2)
            m_planned = c1.number_input("Ilość planowana", min_value=0.0, step=1.0)
            m_unit = c2.selectbox("Jednostka", ["szt", "m2", "mb", "l", "kg"])
            
            c3, c4 = st.columns(2)
            m_need = c3.date_input("Potrzebny do (opcjonalnie)", value=None)
            m_lead = c4.number_input("Czas dostawy (dni)", min_value=0, step=1)
            
            if st.form_submit_button("Dodaj"):
                if m_name.strip():
                    supabase.table("materials").insert({
                        "name": m_name, "room_id": m_room['id'], "quantity_planned": m_planned, "unit": m_unit, 
                        "needed_by": str(m_need) if m_need else None, "lead_time_days": m_lead
                    }).execute()
                    st.success("Dodano materiał!")
                    st.rerun()
                else: st.error("Nazwa jest wymagana!")
                
    st.subheader("Zarządzanie Materiałami")
    df_mats = read_table("materials", select="id, name, status, location, available_for_crew, crew_confirmed, quantity_planned, quantity_received, unit, cost_actual")
    if not df_mats.empty:
        edited_mats = st.data_editor(
            df_mats, 
            disabled=["id", "name", "cost_actual", "quantity_received", "quantity_planned", "unit"], 
            use_container_width=True, hide_index=True, key="mat_editor"
        )
        if st.button("💾 Zapisz zmiany w materiałach"):
            for _, row in edited_mats.iterrows():
                supabase.table("materials").update({
                    "status": row['status'], "location": row['location'], 
                    "available_for_crew": bool(row['available_for_crew']), 
                    "crew_confirmed": bool(row['crew_confirmed'])
                }).eq("id", row['id']).execute()
            st.success("Zapisano w chmurze!")
            st.rerun()
            
        with st.expander("🗑️ Archiwizuj materiał"):
            del_id = st.selectbox("Wybierz materiał", df_mats['id'].tolist(), format_func=lambda x: df_mats[df_mats['id']==x]['name'].iloc[0])
            if st.button("Archiwizuj"):
                supabase.table("materials").update({"is_deleted": True}).eq("id", del_id).execute()
                st.success("Zarchiwizowano!")
                st.rerun()

elif menu == "6. Wydatki (Finanse)":
    st.title("💰 Wydatki (Supabase Sync)")
    df_mats_options = read_table("materials", select="id, name, unit")
    
    with st.expander("➕ Dodaj wydatek", expanded=True):
        with st.form("new_expense", clear_on_submit=True):
            e_desc = st.text_input("Opis (np. Płytki z Castoramy) *")
            c1, c2 = st.columns(2)
            e_amount = c1.number_input("Kwota (zł) *", min_value=0.0, step=10.0)
            e_date = c2.date_input("Data wydatku", value=date.today())
            
            st.markdown("---")
            if not df_mats_options.empty:
                mat_list = [{"id": None, "name": "Brak (Usługa, transport)"}]
                for _, r in df_mats_options.iterrows():
                    mat_list.append({"id": r['id'], "name": f"{r['name']} ({r['unit']})"})
                sel_mat = st.selectbox("Przypisz do materiału:", options=mat_list, format_func=lambda x: x['name'])
                e_qty = st.number_input("Ilość dostarczona na budowę?", min_value=0.0, step=1.0)
            else:
                st.info("Brak wpisanych materiałów.")
                sel_mat = {"id": None}; e_qty = 0.0
            
            if st.form_submit_button("✅ Zapisz wydatek"):
                if not e_desc.strip() or e_amount <= 0:
                    st.error("Opis i kwota > 0 są wymagane!")
                else:
                    supabase.table("expenses").insert({
                        "description": e_desc, "amount": e_amount, "quantity": e_qty,
                        "material_id": sel_mat['id'], "date": str(e_date)
                    }).execute()
                    st.success("Dodano! Chmura automatycznie przeliczyła stany Materiałów (Trigger).")
                    st.rerun()

    st.subheader("📜 Historia Wydatków")
    df_exp = read_table("expenses")
    if not df_exp.empty:
        if not df_mats_options.empty:
            df_exp = df_exp.merge(df_mats_options[['id', 'name']], left_on='material_id', right_on='id', how='left')
            df_exp.rename(columns={"name": "Material"}, inplace=True)
        else:
            df_exp['Material'] = ""
            
        view_df = df_exp[['id', 'date', 'description', 'amount', 'quantity', 'Material']].copy()
        view_df.rename(columns={"date": "Data", "description": "Opis", "amount": "Kwota", "quantity": "Ilość"}, inplace=True)
        st.dataframe(view_df, use_container_width=True, hide_index=True)
        
        with st.expander("🗑️ Anuluj wydatek (Cofnij sync)"):
            del_exp_id = st.selectbox("Wybierz wydatek", view_df['id'].tolist(), format_func=lambda x: f"[{x[:4]}] {view_df[view_df['id']==x]['Opis'].iloc[0]} - {view_df[view_df['id']==x]['Kwota'].iloc[0]} zł")
            if st.button("Anuluj wydatek"):
                supabase.table("expenses").update({"is_deleted": True}).eq("id", del_exp_id).execute()
                st.success("Zarchiwizowano. Supabase Trigger skorygował koszty i ilości w Materiałach!")
                st.rerun()
    else: st.info("Brak wydatków.")

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

elif menu == "5. Ekipa":
    st.title("👷 Zapotrzebowania Ekipy")
    df_reqs = read_table("crew_requests", select="id, title, status, needed_by, is_blocker")
    if not df_reqs.empty:
        df_reqs['is_blocker'] = df_reqs['is_blocker'].astype(bool)
        edited_reqs = st.data_editor(df_reqs, disabled=["id", "title", "needed_by"], hide_index=True, use_container_width=True)
        if st.button("💾 Zapisz"):
            for _, row in edited_reqs.iterrows():
                supabase.table("crew_requests").update({"status": row['status'], "is_blocker": bool(row['is_blocker'])}).eq("id", row['id']).execute()
            st.rerun()

# ==========================================
# NOWE MODUŁY SPRINT 4 (7-10)
# ==========================================

elif menu == "7. Decyzje":
    st.title("🤔 Decyzje")
    st.write("Śledź kluczowe decyzje, od których zależy postęp prac.")
    
    with st.expander("➕ Dodaj decyzję do podjęcia"):
        with st.form("new_dec"):
            d_title = st.text_input("Czego dotyczy decyzja? *")
            d_desc = st.text_area("Szczegóły / Opcje")
            d_room = st.selectbox("Dotyczy pokoju (Opcjonalnie):", options=rooms_dict, format_func=lambda x: x['name'])
            c1, c2 = st.columns(2)
            d_due = c1.date_input("Termin na podjęcie decyzji", value=date.today() + timedelta(days=7))
            d_impact = c2.selectbox("Wpływ na remont", ["Krytyczny", "Średni", "Niski"], index=1)
            
            if st.form_submit_button("Dodaj decyzję"):
                if d_title.strip():
                    supabase.table("decisions").insert({
                        "title": d_title, "description": d_desc, "room_id": d_room['id'],
                        "due_date": str(d_due), "impact": d_impact, "status": "Do podjęcia"
                    }).execute()
                    st.success("Zapisano decyzję!")
                    st.rerun()
                else: st.error("Tytuł jest wymagany!")
                
    df_dec = read_table("decisions", select="id, title, impact, status, due_date, decision_result")
    if not df_dec.empty:
        edited_dec = st.data_editor(df_dec, disabled=["id", "title", "due_date"], hide_index=True, use_container_width=True)
        if st.button("💾 Zapisz zmiany w decyzjach"):
            for _, row in edited_dec.iterrows():
                supabase.table("decisions").update({
                    "status": row['status'], "impact": row['impact'], "decision_result": row['decision_result']
                }).eq("id", row['id']).execute()
            st.success("Zapisano decyzje!")
            st.rerun()
    else: st.info("Brak decyzji w systemie.")

elif menu == "8. Ryzyka":
    st.title("🚨 Rejestr Problemów i Ryzyk")
    st.write("Niespodzianki. Te 'Krytyczne' lądują bezpośrednio na szczycie Dashboardu z potężnym priorytetem.")
    
    with st.expander("➕ Zgłoś Problem"):
        with st.form("new_iss"):
            i_title = st.text_input("Co się stało? (Problem) *")
            i_desc = st.text_area("Opis problemu")
            i_room = st.selectbox("Dotyczy pokoju (Opcjonalnie):", options=rooms_dict, format_func=lambda x: x['name'])
            i_sev = st.selectbox("Ważność (Priorytet)", ["Krytyczne", "Średnie", "Niskie"], index=1)
            if st.form_submit_button("Dodaj Ryzyko"):
                if i_title.strip():
                    supabase.table("issues").insert({
                        "title": i_title, "description": i_desc, "room_id": i_room['id'], "severity": i_sev, "status": "Otwarte"
                    }).execute()
                    st.success("Zgłoszono problem!")
                    st.rerun()
                else: st.error("Tytuł jest wymagany!")

    df_iss = read_table("issues", select="id, title, severity, status")
    if not df_iss.empty:
        edited_iss = st.data_editor(df_iss, disabled=["id", "title"], hide_index=True, use_container_width=True)
        if st.button("💾 Zapisz edycję"):
            for _, row in edited_iss.iterrows():
                supabase.table("issues").update({"status": row['status'], "severity": row['severity']}).eq("id", row['id']).execute()
            st.rerun()
            
        st.divider()
        st.subheader("Przekształć w zadanie (Genialny Workflow)")
        st.caption("Masz problem, który chcesz zamienić na zadanie do wykonania? Połączmy je.")
        
        # Filtrujemy tylko otwarte ryzyka
        open_iss = df_iss[~df_iss['status'].isin(['Przekształcone w zadanie', 'Rozwiązane'])]
        if not open_iss.empty:
            sel_iss_id = st.selectbox("Wybierz problem", open_iss['id'].tolist(), format_func=lambda x: open_iss[open_iss['id']==x]['title'].iloc[0])
            iss_title = open_iss[open_iss['id']==sel_iss_id]['title'].iloc[0]
            if st.button("🛠️ Utwórz Zadanie i ukryj Problem"):
                # 1. Tworzymy zadanie
                new_task = supabase.table("tasks").insert({"name": f"[Z Ryzyka] {iss_title}", "status": "Backlog"}).execute()
                # 2. Aktualizujemy problem
                supabase.table("issues").update({
                    "status": "Przekształcone w zadanie", 
                    "assigned_to_task_id": new_task.data[0]['id']
                }).eq("id", sel_iss_id).execute()
                st.success("Przeniesiono do zadań! Problem znika z pierwszego miejsca Dashboardu (brak duplikacji alertów).")
                st.rerun()
        else:
            st.info("Brak otwartych problemów do przekształcenia w zadanie.")
    else: st.info("Brak wpisanych problemów.")

elif menu == "9. Dziennik":
    st.title("📖 Dziennik Remontu")
    st.write("Chronologiczna historia i komunikaty od ekipy.")
    
    with st.form("new_log"):
        l_content = st.text_area("Treść notatki z dnia dzisiejszego:")
        if st.form_submit_button("Dodaj do dziennika"):
            if l_content.strip():
                supabase.table("daily_logs").insert({
                    "content": l_content.strip(), 
                    "author_role": "investor", 
                    "date": str(date.today())
                }).execute()
                st.success("Wpis dodany!")
                st.rerun()
            else: st.error("Wpisz treść.")
            
    st.divider()
    df_logs = read_table("daily_logs", order_by=("created_at", False)) # Sortowanie malejące
    if not df_logs.empty:
        for _, row in df_logs.iterrows():
            if row['author_role'] == 'crew':
                icon = "👷 **[EKIPA] Raport z prac**"
                bg = "success"
            else:
                icon = "👤 **[TY] Notatka**"
                bg = "info"
            
            st.markdown(f"#### {row['date']} | {icon}")
            if bg == "info":
                st.info(row['content'])
            else:
                st.success(row['content'])
            st.markdown("---")
    else: st.info("Brak wpisów w Dzienniku.")

elif menu == "10. Ustawienia":
    st.title("⚙️ Ustawienia i Eksport")
    
    st.subheader("Pomieszczenia w projekcie")
    df_r = read_table("rooms", select="id, name, budget")
    if not df_r.empty:
        edited_r = st.data_editor(df_r, disabled=["id"], hide_index=True)
        if st.button("Zapisz pomieszczenia"):
            for _, row in edited_r.iterrows():
                supabase.table("rooms").update({"name": row['name'], "budget": row['budget']}).eq("id", row['id']).execute()
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
