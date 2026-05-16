# pages/crew_panel.py
# =====================================================
# PANEL EKIPY (KAROL) - HANDSHAKE 2.0 PREMIUM UI (FIXED)
# =====================================================

import streamlit as st
import pandas as pd
from datetime import datetime
from services.negotiation_service import NegotiationService
from services.phase_service import PhaseService
from supabase import create_client

def render_crew_panel(supabase=None, phase_service=None, negotiation_service=None, change_service=None, task_service=None, ordering_service=None):
    """
    Premium Panel Karola - Zarządzanie pracami, wycenami i negocjacjami.
    """
    
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.header("👷 Panel Ekipy (Karol)")
    with col_refresh:
        if st.button("🔄 Odśwież Dane", use_container_width=True):
            st.rerun()
            
    st.markdown("---")
    
    # Inicjalizacja serwisów
    if not supabase:
        supabase = create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])
    if not negotiation_service:
        negotiation_service = NegotiationService(supabase)
    if not phase_service:
        phase_service = PhaseService()
    if not task_service:
        from services.task_service import TaskService
        task_service = TaskService(supabase)
    if not ordering_service:
        from services.ordering_service import OrderingService
        ordering_service = OrderingService(supabase, task_service)
    
    # 1. WYBÓR PROJEKTU
    projects_res = supabase.table("project_metadata").select("id, project_name").execute()
    projects = projects_res.data or []
    if not projects:
        st.warning("Brak projektów w systemie")
        return
    
    project_options = {p["project_name"]: p["id"] for p in projects}
    selected_project_name = st.selectbox("🏗️ Wybierz projekt", options=project_options.keys(), key="crew_project_select")
    selected_project_id = project_options[selected_project_name]
    
    st.markdown("---")
    
    # 2. DASHBOARD - METRYKI
    all_negs = negotiation_service.get_all_negotiations_for_project(selected_project_id)
    approved_negs = [n for n in all_negs if n['status'] == 'accepted']
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        new_tasks = supabase.table("tasks").select("id").eq("project_id", selected_project_id).eq("commercial_status", "not_started").execute().data
        st.metric("📋 Do wyceny", len(new_tasks or []))
    with col2:
        pending_inv = len([n for n in all_negs if n['status'] == 'pending'])
        st.metric("⏳ Czekam na Inwestora", pending_inv)
    with col3:
        st.metric("✅ Zatwierdzone", len(approved_negs))
    with col4:
        total_val = sum(float(n.get('response_price') or n['proposed_price']) for n in approved_negs)
        st.metric("💰 Wartość umów", f"{total_val:,.0f} zł")

    st.markdown("---")
    
    # 3. TABY
    tab_planning, tab_new_proposal, tab_quotes, tab_counter, tab_accepted = st.tabs([
        "📋 Plan Remontu",
        "➕ Wyślij Nową Wycenę", 
        "📤 Wysłane Propozycje", 
        "💬 Kontrpropozycje", 
        "✅ Moje Umowy"
    ])
    
    with tab_planning:
        render_crew_planning_module(task_service, ordering_service, selected_project_id, phase_service)
    
    with tab_new_proposal:
        st.subheader("➕ Wyślij Nową Wycenę")
        render_new_proposal_form(supabase, negotiation_service, phase_service, selected_project_id, task_service)
        
    with tab_quotes:
        st.subheader("📤 Propozycje wysłane do Inwestora")
        pending_inv_negs = [n for n in all_negs if n['status'] == 'pending']
        if not pending_inv_negs:
            st.success("Wszystkie Twoje propozycje zostały rozpatrzone!")
        else:
            for idx, neg in enumerate(pending_inv_negs):
                render_crew_pending_card(neg, negotiation_service)

    with tab_counter:
        st.subheader("💬 Kontrpropozycje od Inwestora")
        pending_crew = negotiation_service.get_pending_for_crew(selected_project_id)
        if not pending_crew:
            st.info("Brak nowych kontrpropozycji")
        else:
            for idx, neg in enumerate(pending_crew):
                render_crew_counter_card(neg, negotiation_service, key_suffix=f"crew_cnt_{idx}")

    with tab_accepted:
        st.subheader("✅ Zatwierdzone Umowy")
        if not approved_negs:
            st.info("Brak zatwierdzonych umów")
        else:
            for idx, neg in enumerate(approved_negs):
                render_crew_accepted_card(neg, key_suffix=f"crew_acc_{idx}")

# =====================================================
# KOMPONENTY
# =====================================================

def render_new_proposal_form(supabase, negotiation_service, phase_service, project_id, task_service=None):
    """
    Formularz do wysłania nowej propozycji ceny - pozwala na tworzenie NOWYCH robót.
    """
    st.markdown("### 📝 Dodaj nową robotę i wyceń")
    st.caption("Tutaj dodajesz nową pozycję do planu remontu i od razu proponujesz za nią cenę.")
    
    with st.form("form_create_and_quote_task", clear_on_submit=True):
        t_name = st.text_input("Nazwa roboty (np. Podwieszany sufit lub Łazienka na gotowo) *")
        
        # Pobieranie pomieszczeń i sprawdzanie, czy nie są zablokowane RYCZAŁTEM
        phases = phase_service.get_phases(project_id)
        available_rooms = []
        for p in (phases or []):
            tasks_in_room = supabase.table("tasks").select("description").eq("phase_id", p['id']).execute().data
            if not any("[LUMP_SUM_ROOM]" in (t.get('description') or '') for t in (tasks_in_room or [])):
                available_rooms.append(p)
                
        room_options = {p['phase_name']: p['id'] for p in available_rooms} if available_rooms else {"Brak wolnych pomieszczeń": None}
        
        selected_phase_name = st.selectbox("📦 Wybierz pomieszczenie", options=list(room_options.keys()))
        selected_phase_id = room_options[selected_phase_name]
        
        is_lump_sum = st.checkbox("📦 Wyceń całe pomieszczenie (RYCZAŁT ZA CAŁOŚĆ) - zablokuje dodawanie kolejnych zadań w tym pokoju")
        t_desc = st.text_area("Opis techniczny (opcjonalnie)")
        
        col1, col2 = st.columns(2)
        proposed_price = col1.number_input("💰 Proponowana cena (zł) *", min_value=0.0, step=100.0, value=500.0)
        proposed_duration = col2.number_input("⏱️ Szacunkowy czas (dni)", min_value=1, step=1, value=1)
        
        proposed_notes = st.text_area("📝 Dodatkowe notatki dla Inwestora (opcjonalnie)")
        
        if st.form_submit_button("📤 Utwórz i Wyślij Wycenę", use_container_width=True):
            if not t_name or proposed_price <= 0:
                st.error("Podaj nazwę roboty i cenę większą niż 0!")
            else:
                try:
                    # Wstrzykujemy ukryty tag, jeśli to ryczałt
                    final_desc = f"{t_desc}\n[LUMP_SUM_ROOM]" if is_lump_sum else t_desc
                    
                    # 1. Tworzymy nowe ZADANIE (Task) korzystając z Serwisu
                    # Automatycznie dostanie stempel Handshake i statusy
                    new_task = task_service.create_task(
                        project_id=project_id,
                        phase_id=selected_phase_id,
                        name=t_name,
                        description=final_desc
                    )
                    
                    if new_task:
                        new_task_id = new_task['id']
                        
                        # 2. Odpalamy Handshake 2.0 dla nowego zadania
                        success, message, neg_id = negotiation_service.propose_price(
                            task_id=new_task_id,
                            proposed_by='crew',
                            price=proposed_price,
                            duration_days=int(proposed_duration),
                            notes=proposed_notes
                        )
                        
                        if success:
                            st.success(f"✅ Dodano robotę i wysłano wycenę!")
                            st.rerun()
                        else:
                            st.error(f"Zadanie utworzone, ale błąd negocjacji: {message}")
                    else:
                        st.error("Błąd zapisu do bazy zadań.")
                except Exception as e:
                    st.error(f"Wystąpił błąd podczas komunikacji z serwerem: {str(e)}")

def render_crew_pending_card(neg, negotiation_service):
    task_name = neg.get('tasks', {}).get('name', 'Nieznane zadanie')
    with st.container(border=True):
        st.markdown(f"### ⏳ {task_name}")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Twoja Cena", f"{neg['proposed_price']:,.0f} zł")
        with c2:
            st.metric("Czas", f"{neg['proposed_duration_days']} dni")
        with c3:
            st.caption("Czekam na Inwestora")

def render_crew_counter_card(neg, negotiation_service, key_suffix=""):
    neg_id = neg['id']
    task_name = neg.get('tasks', {}).get('name', 'Nieznane zadanie')
    
    with st.container(border=True):
        st.markdown(f"### 💬 {task_name}")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("TWOJA CENA", f"{neg['proposed_price']:,.0f} zł")
        with c2:
            st.warning(f"KONTRA INWESTORA: {neg['response_price']:,.0f} zł")
        
        if neg.get('response_notes'):
            st.info(f"💬 Inwestor: {neg['response_notes']}")
            
        b1, b2 = st.columns(2)
        with b1:
            if st.button("✅ Akceptuję", key=f"btn_acc_{neg_id}_{key_suffix}", use_container_width=True):
                success, msg = negotiation_service.crew_accept_counter_offer(neg_id)
                if success:
                    st.rerun()
        with b2:
            if st.button("🔄 Nowa oferta", key=f"btn_rev_{neg_id}_{key_suffix}", use_container_width=True):
                st.session_state[f"show_crew_form_{neg_id}"] = True
                st.rerun()
        
        if st.session_state.get(f"show_crew_form_{neg_id}", False):
            with st.form(key=f"form_crew_widget_{neg_id}"):
                p = st.number_input("Nowa cena dla Inwestora", value=float(neg['response_price'] + 100))
                if st.form_submit_button("Wyślij"):
                    success, msg = negotiation_service.crew_counter_counter_offer(neg_id, p, int(neg.get('proposed_duration_days', 1)))
                    if success:
                        st.session_state[f"show_crew_form_{neg_id}"] = False
                        st.rerun()
                if st.form_submit_button("Anuluj"):
                    st.session_state[f"show_crew_form_{neg_id}"] = False
                    st.rerun()

def render_crew_planning_module(task_service, ordering_service, project_id, phase_service):
    """
    Panel planowania Karola z możliwością zmiany kolejności zadań.
    """
    supabase = task_service.supabase
    
    # Formularz dodawania nowego Pomieszczenia
    with st.expander("🏠 Dodaj Pomieszczenie do swojego Planu"):
        with st.form("form_add_room", clear_on_submit=True):
            try:
                available_rooms_req = supabase.table("rooms").select("*").eq("project_id", project_id).execute()
                available_rooms = available_rooms_req.data or []
            except:
                available_rooms = []
            
            if not available_rooms:
                st.warning("Inwestor nie zdefiniował jeszcze żadnych pomieszczeń.")
                st.form_submit_button("Dodaj", disabled=True)
            else:
                room_names = [r.get("name", "Nieznane") for r in available_rooms]
                p_name = st.selectbox("Wybierz pomieszczenie z listy Inwestora *", options=room_names)

                col_date, col_days = st.columns(2)
                from datetime import date as _date, timedelta as _timedelta
                p_start = col_date.date_input("📅 Kiedy zaczynasz?", value=_date.today())
                p_days = col_days.number_input("⏱️ Ile dni potrzebujesz?", min_value=1, max_value=365, value=7, step=1)
                p_end = p_start + _timedelta(days=p_days)
                st.caption(f"→ Planowany koniec: **{p_end.strftime('%d.%m.%Y')}**")

                if st.form_submit_button("✅ Dodaj do Planu", type="primary"):
                    res = phase_service.create_phase(
                        project_id,
                        p_name,
                        planned_start_date=p_start.isoformat(),
                        planned_end_date=p_end.isoformat()
                    )
                    if res.get("success"):
                        st.success(f"Pomieszczenie '{p_name}' dodane!")
                        st.rerun()
                    else:
                        st.error(f"Błąd: {res.get('error')}")
    
    st.markdown("---")
    
    phases = phase_service.get_phases(project_id)
    if not phases:
        st.info("Brak pomieszczeń w planie.")
        return
        
    for p in phases:
        phase_id = p['id']
        with st.container(border=True):
            # Pobierz posortowane zadania przez OrderingService
            ordered_tasks = ordering_service.get_ordered_tasks(phase_id)
            
            # Sprawdzamy ryczałt
            is_lump_sum_room = any("[LUMP_SUM_ROOM]" in (t.get('description') or '') for t in ordered_tasks)
            
            col_room, col_del = st.columns([5, 1])
            with col_room:
                title_suffix = " 🔒 `RYCZAŁT`" if is_lump_sum_room else ""
                st.markdown(f"### 📦 {p['phase_name']}{title_suffix}")
                if is_lump_sum_room:
                    st.warning("Pomieszczenie zablokowane dla nowych zadań.")
            
            with col_del:
                if not ordered_tasks:
                    if st.button("🗑️", key=f"del_room_{phase_id}", help="Usuń puste pomieszczenie"):
                        phase_service.delete_phase(phase_id)
                        st.rerun()

            if ordered_tasks:
                for idx, task in enumerate(ordered_tasks):
                    # Nowy układ kolumn z przyciskami ruchu
                    col_num, col_info, col_move, col_price = st.columns([0.5, 3, 1, 1.5])
                    
                    with col_num:
                        st.markdown(f"<div style='padding-top:10px; opacity:0.5;'>#{idx+1}</div>", unsafe_allow_html=True)
                    
                    with col_info:
                        st.write(f"**{task['name']}**")
                        # Badge statusu
                        status = task['status'] # READY, PENDING, BLOCKED
                        if status == 'READY':
                            st.caption("🟢 **Gotowe do realizacji**")
                        elif status == 'PENDING':
                            st.caption("⚪ **Szkic / Do wyceny**")
                        elif status == 'BLOCKED':
                            st.caption("⏸️ **Czeka na poprzednie zadanie**")
                    
                    with col_move:
                        m1, m2 = st.columns(2)
                        with m1:
                            if st.button("⬆️", key=f"up_{task['id']}", disabled=(idx==0)):
                                ordering_service.move_task_up(task['id'])
                                st.rerun()
                        with m2:
                            if st.button("⬇️", key=f"down_{task['id']}", disabled=(idx==len(ordered_tasks)-1)):
                                ordering_service.move_task_down(task['id'])
                                st.rerun()
                    
                    with col_price:
                        if task['final_price']:
                            st.markdown(f"<div style='text-align:right; color:#10b981; font-weight:700;'>{task['final_price']:,.0f} zł</div>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<div style='text-align:right; opacity:0.5;'>brak ceny</div>", unsafe_allow_html=True)
            else:
                st.caption("Brak zadań. Dodaj pierwsze zadanie w tym pokoju.")

            # Przycisk dodania nowego zadania (tylko jeśli nie ryczałt)
            if not is_lump_sum_room:
                st.divider()
                with st.expander("➕ Dodaj zadanie do tego pokoju"):
                    with st.form(key=f"fast_add_task_{phase_id}"):
                        new_t_name = st.text_input("Nazwa zadania")
                        new_t_dur = st.number_input("Szacowane dni", min_value=1, value=1)
                        if st.form_submit_button("Dodaj zadanie", use_container_width=True):
                            if new_t_name:
                                task_service.create_task(
                                    project_id=project_id,
                                    phase_id=phase_id,
                                    name=new_t_name,
                                    estimated_duration_days=new_t_dur
                                )
                                st.rerun()

def render_crew_accepted_card(neg, key_suffix=""):
    task_name = neg.get('tasks', {}).get('name', 'Nieznane zadanie')
    final_price = neg.get('response_price') or neg['proposed_price']
    with st.container(border=True):
        st.markdown(f"### ✅ {task_name}")
        st.metric("Cena finalna", f"{final_price:,.0f} zł")
        st.caption(f"Status: Zaakceptowano")

if __name__ == "__main__":
    st.warning("Uruchom przez app.py")
