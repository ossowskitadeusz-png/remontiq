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
    
    # 1. Wybór projektu
    projects_res = supabase.table("project_metadata").select("id, project_name, crew_lead_name").execute()
    projects = projects_res.data or []
    if not projects:
        st.warning("Brak projektów w systemie. Poczekaj, aż Inwestor założy projekt.")
        return
        
    project_options = {p["project_name"]: p for p in projects}
    selected_project_name = st.selectbox("🏗️ Wybierz projekt do realizacji", options=project_options.keys(), key="exec_proj_select")
    selected_project_data = project_options[selected_project_name]
    selected_project_id = selected_project_data["id"]
    crew_name = selected_project_data.get("crew_lead_name") or "Ekipa"
    
    st.markdown("---")
    
    # 2. Pobierz zatwierdzone zadania (te, które przeszły Handshake i Inwestor je zatwierdził)
    # commercial_status == 'approved' oznacza zablokowaną wycenę.
    tasks_res = supabase.table("tasks").select("id, name, kanban_status, final_approved_price").eq("project_id", selected_project_id).eq("commercial_status", "approved").execute()
    tasks = tasks_res.data or []
    
    if not tasks:
        st.info("Brak zadań gotowych do realizacji. Wyceń zadania w 'Plan Remontu' i poczekaj na akceptację Inwestora.")
        return
        
    # Pogrupuj zadania według statusu wykonania
    todo = [t for t in tasks if t.get("kanban_status") == "TODO" or not t.get("kanban_status")]
    in_progress = [t for t in tasks if t.get("kanban_status") == "IN_PROGRESS"]
    done = [t for t in tasks if t.get("kanban_status") == "DONE"]
    
    st.write(f"Zadania dla: **{crew_name}**")
    
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.subheader(f"📋 Do zrobienia ({len(todo)})")
        for t in todo:
            with st.container(border=True):
                st.write(f"**{t['name']}**")
                if st.button("▶️ Rozpocznij", key=f"start_{t['id']}", use_container_width=True):
                    task_service.update_task(t['id'], {"kanban_status": "IN_PROGRESS", "state": "IN_PROGRESS"})
                    st.rerun()
                    
    with c2:
        st.subheader(f"⏳ W trakcie ({len(in_progress)})")
        for t in in_progress:
            with st.container(border=True):
                st.write(f"**{t['name']}**")
                st.caption("W realizacji...")
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("✅ Gotowe", key=f"done_{t['id']}", type="primary", use_container_width=True):
                        task_service.update_task(t['id'], {"kanban_status": "DONE", "state": "COMPLETED"})
                        st.rerun()
                with col_btn2:
                    if st.button("🔙 Cofnij", key=f"back_{t['id']}", use_container_width=True):
                        task_service.update_task(t['id'], {"kanban_status": "TODO", "state": "DRAFT"})
                        st.rerun()

    with c3:
        st.subheader(f"✅ Zakończone ({len(done)})")
        for t in done:
            with st.container(border=True):
                st.write(f"**{t['name']}**")
                st.caption("🟢 Czeka na odbiór Inwestora")
                if st.button("🔙 Przywróć", key=f"revert_{t['id']}", use_container_width=True):
                    task_service.update_task(t['id'], {"kanban_status": "IN_PROGRESS", "state": "IN_PROGRESS"})
                    st.rerun()
