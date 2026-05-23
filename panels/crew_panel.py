import streamlit as st
import pandas as pd
from datetime import datetime
from services.negotiation_service import NegotiationService
from services.phase_service import PhaseService

def render_crew_dashboard(supabase, phase_service, negotiation_service, task_service):
    """
    Jednoekranowy Kokpit Budowy (Mobile-First) dla Ekipy.
    Brak sidebaru, brak zakładek.
    """
    # 1. AUTORYZOWANY PROJEKT (HARD-LOCK)
    selected_project_id = st.session_state.get("crew_authorized_project_id")
    if not selected_project_id:
        st.error("Brak przypisanego remontu. Zaloguj się poprawnym kodem.")
        return
        
    projects_res = supabase.table("project_metadata").select("id, project_name, crew_lead_name").eq("id", selected_project_id).execute()
    projects = projects_res.data or []
    if not projects:
        st.warning("Projekt, do którego próbujesz się dostać, nie istnieje.")
        return
    
    selected_project_data = projects[0]
    crew_boss_name = selected_project_data.get("crew_lead_name") or "Ekipy"
    project_name = selected_project_data["project_name"]

    # Wyloguj na samej górze
    c1, c2 = st.columns([4, 1])
    with c1:
        st.markdown(f"## 🏗️ {project_name}")
        st.caption(f"Zalogowano jako: {crew_boss_name}")
    with c2:
        if st.button("🚪 Wyloguj", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    st.markdown("---")

    # ==========================================
    # GŁÓWNE AKCJE (Szybkie przyciski ratunkowe)
    # ==========================================
    st.subheader("⚡ Szybkie Zgłoszenia")
    b1, b2, b3 = st.columns(3)
    
    with b1:
        if st.button("🟥 Zgłoś Problem", use_container_width=True):
            st.session_state["crew_quick_action"] = "problem"
            st.rerun()
    with b2:
        if st.button("🟨 Brak materiału", use_container_width=True):
            st.session_state["crew_quick_action"] = "material"
            st.rerun()
    with b3:
        if st.button("🟦 Dodaj Zdjęcie/Czat", use_container_width=True):
            st.session_state["crew_quick_action"] = "chat"
            st.rerun()

    # Obsługa formularzy szybkich akcji
    qa = st.session_state.get("crew_quick_action")
    if qa:
        with st.container(border=True):
            if qa == "problem":
                st.markdown("### 🟥 Zgłoś Problem")
                prob_desc = st.text_area("Co wstrzymuje prace?")
                if st.button("Wyślij zgłoszenie", type="primary"):
                    if prob_desc:
                        st.success("Wysłano alert do Inwestora!")
                        st.session_state["crew_quick_action"] = None
                        st.rerun()
            elif qa == "material":
                st.markdown("### 🟨 Brakuje Materiału")
                mat_name = st.text_input("Nazwa materiału")
                if st.button("Zgłoś brak", type="primary"):
                    if mat_name:
                        st.success("Zgłoszono zapotrzebowanie do Inwestora!")
                        st.session_state["crew_quick_action"] = None
                        st.rerun()
            elif qa == "chat":
                st.markdown("### 🟦 Czat Budowy")
                msg = st.text_input("Wiadomość do inwestora")
                if st.button("Wyślij wiadomość", type="primary"):
                    if msg:
                        st.success("Wysłano!")
                        st.session_state["crew_quick_action"] = None
                        st.rerun()
            if st.button("Anuluj", key="cancel_qa"):
                st.session_state["crew_quick_action"] = None
                st.rerun()
                
    st.markdown("---")

    # ==========================================
    # LISTA ZADAŃ DO REALIZACJI (Wertykalna)
    # ==========================================
    st.subheader("📋 Twoje zadania")
    
    tasks_res = supabase.table("tasks").select("id, name, kanban_status, commercial_status, phase_id").eq("project_id", selected_project_id).eq("commercial_status", "approved").execute()
    tasks = tasks_res.data or []
    
    phases_res = supabase.table("project_phases").select("id, phase_name").eq("project_id", selected_project_id).execute()
    phases_map = {p["id"]: p["phase_name"] for p in phases_res.data or []}

    active_tasks = [t for t in tasks if t.get("kanban_status") in ["TODO", "IN_PROGRESS", None]]
    
    if not active_tasks:
        st.success("Brak aktywnych zadań do zrealizowania. Wszystko zrobione!")
    else:
        for t in active_tasks:
            status = t.get("kanban_status") or "TODO"
            room = phases_map.get(t.get("phase_id"), "Ogólne")
            
            with st.container(border=True):
                st.markdown(f"### {t['name']}")
                st.caption(f"🏠 {room} | Aktualny status: **{status}**")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    if status == "TODO":
                        if st.button("▶️ Start", key=f"s_{t['id']}", use_container_width=True, type="primary"):
                            task_service.update_task(t['id'], {"kanban_status": "IN_PROGRESS", "actual_start_date": datetime.now().date().isoformat()})
                            st.rerun()
                    else:
                        st.button("▶️ W trakcie", key=f"s_{t['id']}", disabled=True, use_container_width=True)
                with col2:
                    if st.button("🚨 Problem", key=f"p_{t['id']}", use_container_width=True):
                        st.session_state["crew_quick_action"] = "problem"
                        st.rerun()
                with col3:
                    if status == "IN_PROGRESS":
                        if st.button("✅ Gotowe", key=f"g_{t['id']}", use_container_width=True, type="primary"):
                            task_service.update_task(t['id'], {"kanban_status": "AWAITING_INSPECTION", "actual_end_date": datetime.now().date().isoformat()})
                            st.rerun()
                    else:
                        st.button("✅ Gotowe", key=f"g_{t['id']}", disabled=True, use_container_width=True)

    st.markdown("---")
    
    # ==========================================
    # WYCENY I KONTROFERTY (Bypass)
    # ==========================================
    pending_crew = negotiation_service.get_pending_for_crew(selected_project_id)
    new_tasks = supabase.table("tasks").select("id, name, phase_id").eq("project_id", selected_project_id).eq("commercial_status", "not_started").execute().data or []
    
    if pending_crew or new_tasks:
        with st.expander("💸 Zadania do wyceny i Negocjacje", expanded=bool(pending_crew)):
            if pending_crew:
                st.error("🚨 Oczekujące kontrpropozycje od Inwestora!")
                for neg in pending_crew:
                    task_name = neg.get('tasks', {}).get('name', 'Nieznane zadanie')
                    with st.container(border=True):
                        st.write(f"**{task_name}**")
                        st.warning(f"Inwestor proponuje: {neg['response_price']:,.0f} zł (Twoja cena: {neg['proposed_price']:,.0f} zł)")
                        if st.button("✅ Zgadzam się", key=f"acc_{neg['id']}", use_container_width=True):
                            negotiation_service.crew_accept_counter_offer(neg['id'])
                            st.rerun()
            if new_tasks:
                st.info("Nowe zadania od inwestora do wyceny:")
                for nt in new_tasks:
                    with st.container(border=True):
                        st.write(f"**{nt['name']}**")
                        p = st.number_input("Twoja cena (zł)", key=f"np_{nt['id']}", value=0.0, min_value=0.0)
                        if st.button("Wyślij wycenę", key=f"send_{nt['id']}"):
                            negotiation_service.crew_propose_price(nt['id'], p, 1, "")
                            st.rerun()
