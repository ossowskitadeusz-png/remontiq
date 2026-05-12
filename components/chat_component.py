# components/chat_component.py

import streamlit as st
from services.chat_service import ChatService
from datetime import datetime

def render_chat_component(supabase, user_id, user_role):
    """
    REMONTIQ NATIVE CHAT v3.0
    ✅ Wykorzystuje Twoje tabele: task_comments i activity_log
    ✅ Pełna integracja z istniejącymi danymi
    """
    
    st.markdown("### 🗣️ Dyskusja Budowy")
    
    chat_service = ChatService(supabase)
    
    # 1. Wybór projektu
    try:
        projects = supabase.table("project_metadata").select("id, project_name").execute()
        if not projects.data:
            st.warning("❌ Brak projektów.")
            return
        project_dict = {p['project_name']: p['id'] for p in projects.data}
        selected_project_name = st.selectbox("📁 Projekt:", options=list(project_dict.keys()), key="p_sel_v3")
        selected_project_id = project_dict[selected_project_name]
    except:
        st.error("Błąd połączenia z bazą.")
        return

    # 2. Wybór zadania (Konieczny dla natywnych komentarzy)
    try:
        tasks = supabase.table("tasks").select("id, name").eq("project_id", selected_project_id).execute()
        if not tasks.data:
            st.info("Dodaj zadania do projektu, aby móc czatować.")
            return
        task_dict = {t['name']: t['id'] for t in tasks.data}
        selected_task_name = st.selectbox("📍 Zadanie / Wątek:", options=list(task_dict.keys()), key="t_sel_v3")
        selected_task_id = task_dict[selected_task_name]
    except:
        st.error("Błąd ładowania zadań.")
        return

    st.divider()

    tab1, tab2 = st.tabs(["💬 Czat", "📋 Historia Zmian"])
    
    with tab1:
        # Historia z task_comments
        try:
            messages, _ = chat_service.get_chat_history(selected_task_id)
            if messages:
                for msg in messages:
                    # Rozróżnienie stron (Inwestor vs Ekipa)
                    is_me = (msg['author_name'] == st.session_state.get("user_name"))
                    align = "human" if is_me else "ai"
                    
                    role_icon = "👷" if msg['author_role'] in ['crew', 'CREW_LEAD'] else "👤"
                    with st.chat_message(align):
                        st.write(f"**{role_icon} {msg['author_name']}**: {msg['content']}")
                        st.caption(f"{msg['created_at'][:16]}")
            else:
                st.info("Brak komentarzy w tym wątku. Napisz coś!")
        except Exception as e:
            st.error(f"Błąd: {e}")

        # Wysyłanie
        st.divider()
        with st.form("native_chat_form", clear_on_submit=True):
            new_msg = st.text_area("Twoja wiadomość:", height=100)
            if st.form_submit_button("📤 Wyślij", type="primary"):
                if new_msg.strip():
                    res = chat_service.send_message(
                        project_id=selected_project_id,
                        task_id=selected_task_id,
                        content=new_msg,
                        sender_id=user_id,
                        sender_role=user_role,
                        sender_display_name=st.session_state.get("user_name", "Użytkownik")
                    )
                    if res["success"]:
                        st.rerun()
                    else:
                        st.error(f"Błąd wysyłki: {res.get('error')}")
                else:
                    st.warning("Wpisz treść wiadomości.")

    with tab2:
        # Activity Log z activity_log
        try:
            logs, _ = chat_service.get_activity_log(selected_project_id, selected_task_id)
            if logs:
                for log in logs:
                    st.write(f"🔔 **{log['created_at'][:16]}**")
                    st.write(log['content'])
                    st.divider()
            else:
                st.info("Brak odnotowanych zmian systemowych.")
        except Exception as e:
            st.error(f"Błąd logów: {e}")
