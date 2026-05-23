import streamlit as st
from datetime import datetime

def render_crew_execution_panel(supabase, task_service):
    """
    Panel Kanban dla Ekipy - "Plan na dzisiaj".
    Służy do fizycznego oznaczania postępu prac nad zaakceptowanymi zadaniami.
    """
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.header("🚀 Plan na dzisiaj (Tablica Kanban)")
    with col_refresh:
        if st.button("🔄 Odśwież Tablicę", use_container_width=True):
            st.rerun()

    st.markdown("---")
    
    # 1. Autoryzowany projekt
    selected_project_id = st.session_state.get("crew_authorized_project_id")
    if not selected_project_id:
        st.error("Brak przypisanego remontu. Zaloguj się poprawnym kodem.")
        return
        
    projects_res = supabase.table("project_metadata").select("id, project_name, crew_lead_name").eq("id", selected_project_id).execute()
    projects = projects_res.data or []
    if not projects:
        st.warning("Projekt do którego masz dostęp przestał istnieć.")
        return
        
    selected_project_data = projects[0]
    crew_name = selected_project_data.get("crew_lead_name") or "Ekipa"
    st.info(f"Realizujesz projekt: **{selected_project_data['project_name']}**")
    
    st.markdown("---")
    
    # 2. Pobierz zatwierdzone zadania (te, które przeszły Handshake i Inwestor je zatwierdził)
    # commercial_status == 'approved' oznacza zablokowaną wycenę.
    tasks_res = supabase.table("tasks").select("id, name, kanban_status, final_approved_price, phase_id").eq("project_id", selected_project_id).eq("commercial_status", "approved").execute()
    tasks = tasks_res.data or []
    
    # Pobierz mapę pokoi/faz dla projektu
    phases_res = supabase.table("project_phases").select("id, phase_name").eq("project_id", selected_project_id).execute()
    phases_map = {p["id"]: p["phase_name"] for p in phases_res.data or []}
    
    if not tasks:
        st.info("Brak zadań gotowych do realizacji. Wyceń zadania w 'Plan Remontu' i poczekaj na akceptację Inwestora.")
        return
        
    # Pogrupuj zadania według statusu wykonania
    todo = [t for t in tasks if t.get("kanban_status") == "TODO" or not t.get("kanban_status")]
    in_progress = [t for t in tasks if t.get("kanban_status") == "IN_PROGRESS"]
    done = [t for t in tasks if t.get("kanban_status") in ["DONE", "AWAITING_INSPECTION"]]
    
    st.write(f"Zadania dla: **{crew_name}**")
    
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.subheader(f"📋 Do zrobienia ({len(todo)})")
        for t in todo:
            with st.container(border=True):
                st.write(f"**{t['name']}**")
                st.caption(f"🏠 Pomieszczenie: **{phases_map.get(t.get('phase_id'), 'Ogólne')}**")
                with st.expander("▶️ Rozpocznij zadanie"):
                    # Ekipa deklaruje, kiedy planuje skończyć
                    end_date = st.date_input("Kiedy planujesz skończyć?", key=f"date_{t['id']}")
                    if st.button("Potwierdź start", key=f"start_{t['id']}", type="primary", use_container_width=True):
                        # Zapisujemy daty startu i planowanego końca
                        payload = {
                            "kanban_status": "IN_PROGRESS", 
                            "actual_start_date": datetime.now().date().isoformat(),
                            "planned_end_date": end_date.isoformat()
                        }
                        task_service.update_task(t['id'], payload)
                        st.rerun()
                    
    with c2:
        st.subheader(f"⏳ W trakcie ({len(in_progress)})")
        for t in in_progress:
            with st.container(border=True):
                st.write(f"**{t['name']}**")
                st.caption(f"🏠 Pomieszczenie: **{phases_map.get(t.get('phase_id'), 'Ogólne')}**")
                if t.get('planned_end_date'):
                    st.caption(f"Cel: {t['planned_end_date']}")
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("✅ Gotowe (do odbioru)", key=f"done_{t['id']}", type="primary", use_container_width=True):
                        # Zmieniamy na AWAITING_INSPECTION zamiast zwykłego DONE
                        payload = {
                            "kanban_status": "AWAITING_INSPECTION", 
                            "actual_end_date": datetime.now().date().isoformat()
                        }
                        task_service.update_task(t['id'], payload)
                        st.rerun()
                with col_btn2:
                    if st.button("🔙 Cofnij", key=f"back_{t['id']}", use_container_width=True):
                        task_service.update_task(t['id'], {"kanban_status": "TODO", "actual_start_date": None})
                        st.rerun()

    with c3:
        st.subheader(f"🔍 Do odbioru/Zakończone ({len(done)})")
        for t in done:
            with st.container(border=True):
                st.write(f"**{t['name']}**")
                st.caption(f"🏠 Pomieszczenie: **{phases_map.get(t.get('phase_id'), 'Ogólne')}**")
                if t.get("kanban_status") == "AWAITING_INSPECTION":
                    st.warning("🟡 Czeka na odbiór Inwestora")
                else:
                    st.success("✅ Odebrane przez Inwestora")
                
                if st.button("🔙 Przywróć", key=f"revert_{t['id']}", use_container_width=True):
                    task_service.update_task(t['id'], {"kanban_status": "IN_PROGRESS", "actual_end_date": None})
                    st.rerun()
