# components/chat_component.py

import streamlit as st
from services.chat_service import ChatService
from datetime import datetime

def render_chat_component(supabase, user_id, user_role):
    """
    Komponent czatu wstrzyknięty bezpośrednio do app.py
    ✅ Poprawione nazwy kolumn (name zamiast task_name)
    ✅ Poprawione parametry wysyłania (sender_role)
    """
    
    st.subheader("💬 Czat Budowy")
    
    # Debug panel
    with st.expander("🛠️ Diagnostyka sesji", expanded=False):
        st.write(f"✅ User ID: {user_id}")
        st.write(f"✅ Role: {user_role}")
    
    # ============================================================
    # Wybór projektu
    # ============================================================
    try:
        projects = supabase.table("project_metadata").select("id, project_name").execute()
        
        if not projects.data:
            st.warning("❌ Brak projektów.")
            return
        
        project_dict = {p['project_name']: p['id'] for p in projects.data}
        selected_project_name = st.selectbox("Wybierz projekt:", options=list(project_dict.keys()), key="chat_p_sel")
        selected_project_id = project_dict[selected_project_name]
        
    except Exception as e:
        st.error(f"Błąd ładowania projektów: {e}")
        return
    
    # ============================================================
    # Wybór zadania
    # ============================================================
    try:
        # FIX: Kolumna w bazie to 'name'
        tasks = supabase.table("tasks").select("id, name").eq("project_id", selected_project_id).execute()
        
        if not tasks.data:
            st.info("Brak zadań w tym projekcie.")
            return
        
        task_dict = {t['name']: t['id'] for t in tasks.data}
        selected_task_name = st.selectbox("Wybierz zadanie:", options=list(task_dict.keys()), key="chat_t_sel")
        selected_task_id = task_dict[selected_task_name]
        
    except Exception as e:
        st.error(f"Błąd ładowania zadań: {e}")
        return
    
    # ============================================================
    # Obsługa Czatu
    # ============================================================
    chat_service = ChatService(supabase)
    tab1, tab2 = st.tabs(["💬 Wiadomości", "📋 Activity Log"])
    
    with tab1:
        # Historia
        messages, total = chat_service.get_chat_history(selected_task_id)
        if messages:
            for msg in messages:
                with st.chat_message(msg.get('sender_role', 'System')):
                    st.write(msg['content'])
                    st.caption(f"{msg.get('sender_display_name', 'System')} | {msg.get('timestamp')}")
        else:
            st.info("Brak wiadomości.")

        # Wysyłanie
        st.divider()
        with st.form("chat_form_new", clear_on_submit=True):
            content = st.text_area("Twoja wiadomość:")
            recipient = st.selectbox("Dla kogo:", ["BOTH", "INVESTOR", "CREW"])
            if st.form_submit_button("📤 Wyślij"):
                if content:
                    # FIX: sender_role zamiast message_type
                    res = chat_service.send_message(
                        project_id=selected_project_id,
                        task_id=selected_task_id,
                        content=content,
                        sender_id=user_id,
                        sender_role=user_role,
                        sender_display_name=st.session_state.get("user_name", "Użytkownik"),
                        recipient_role=recipient
                    )
                    if res["success"]:
                        st.success("✅ Wysłano!")
                        st.rerun()
                    else:
                        st.error(f"Błąd: {res.get('error')}")

    with tab2:
        activity, total = chat_service.get_activity_log(selected_task_id)
        if activity:
            for log in activity:
                st.info(log['content'])
                st.caption(log['created_at'])
        else:
            st.info("Brak logów.")
