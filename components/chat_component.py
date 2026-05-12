# components/chat_component.py

import streamlit as st
from services.chat_service import ChatService
from datetime import datetime

def render_chat_component(supabase, user_id, user_role):
    """
    REMONTIQ LIVE CHAT v2.0 - Otwarta Księga Projektu
    ✅ Widok całego projektu (Global Stream)
    ✅ Chat Bubbles (Baloniki)
    ✅ Tagowanie zadań
    """
    
    st.markdown("### 📖 Otwarta Księga Projektu")
    
    chat_service = ChatService(supabase)
    
    # ============================================================
    # 1. WYBÓR PROJEKTU (Bez zmian)
    # ============================================================
    try:
        projects = supabase.table("project_metadata").select("id, project_name").execute()
        if not projects.data:
            st.warning("❌ Brak projektów.")
            return
        project_dict = {p['project_name']: p['id'] for p in projects.data}
        selected_project_name = st.selectbox("📁 Wybierz projekt:", options=list(project_dict.keys()), key="p_sel_v2")
        selected_project_id = project_dict[selected_project_name]
    except:
        st.error("Błąd bazy danych.")
        return

    # ============================================================
    # 2. KONFIGURACJA WIDOKU (Globalny vs Zadanie)
    # ============================================================
    col_v1, col_v2 = st.columns([2, 2])
    with col_v1:
        view_mode = st.radio("Widok:", ["Cały Projekt", "Konkretne Zadanie"], horizontal=True)
    
    selected_task_id = None
    if view_mode == "Konkretne Zadanie":
        with col_v2:
            tasks = supabase.table("tasks").select("id, name").eq("project_id", selected_project_id).execute()
            if tasks.data:
                task_dict = {t['name']: t['id'] for t in tasks.data}
                selected_task_name = st.selectbox("📍 Zadanie:", options=list(task_dict.keys()))
                selected_task_id = task_dict[selected_task_name]
            else:
                st.info("Brak zadań.")

    st.divider()

    # ============================================================
    # 3. STRUMIEŃ WIADOMOŚCI (Otwarta Księga)
    # ============================================================
    try:
        if view_mode == "Cały Projekt":
            messages = chat_service.get_project_chat_history(selected_project_id)
        else:
            messages, _ = chat_service.get_chat_history(selected_task_id) if selected_task_id else ([], 0)

        if messages:
            for msg in messages:
                # Rozróżnienie stron (Inwestor vs Ekipa)
                is_me = (msg['sender_id'] == user_id)
                align = "human" if is_me else "ai" # "human" to my, "ai" to inni (uproszczenie Streamlit)
                
                # Dynamiczna nazwa i rola
                role_label = "👤 INWESTOR" if msg['sender_role'] == "INVESTOR" else "👷 EKIPA"
                sender_name = msg.get('sender_display_name', 'Użytkownik')
                
                with st.chat_message(align):
                    st.write(f"**{role_label}**: {msg['content']}")
                    # Informacja o zadaniu (jeśli widok globalny)
                    if view_mode == "Cały Projekt" and msg.get('task_id'):
                        st.caption(f"📍 Tag: Zadanie")
                    st.caption(f"{msg.get('created_at')[:16]}")
        else:
            st.info("Pusto. Rozpocznij dyskusję!")

    except Exception as e:
        st.error(f"Błąd ładowania: {e}")

    # ============================================================
    # 4. SZYBKIE WYSYŁANIE (Sticky bottom style)
    # ============================================================
    st.divider()
    
    # Jeśli jesteśmy w widoku globalnym, wiadomość może być przypisana do projektu (task_id = NULL)
    # Nasz SQL na to pozwala, więc nie musimy wymuszać zadania.
    active_task_id = selected_task_id

    with st.container():
        input_col, btn_col = st.columns([4, 1])
        with input_col:
            new_msg = st.text_input("Napisz do drugiej strony...", key="global_chat_input", placeholder="Twoja wiadomość...")
        with btn_col:
            if st.button("🚀 Wyślij", use_container_width=True, type="primary"):
                if new_msg:
                    res = chat_service.send_message(
                        project_id=selected_project_id,
                        task_id=active_task_id, # Może być None dla wiadomości ogólnych
                        content=new_msg,
                        sender_id=user_id,
                        sender_role=user_role,
                        sender_display_name=st.session_state.get("user_name", "Użytkownik"),
                        recipient_role="BOTH",
                        message_type="TEXT"
                    )
                    if res["success"]:
                        st.rerun()
                    else:
                        st.error(f"Błąd wysyłki: {res.get('error')}")
                else:
                    st.warning("Pusta wiadomość.")

    # Activity Log na dole jako rozwijana sekcja
    with st.expander("📋 Log zdarzeń systemowych (Activity Feed)", expanded=False):
        if active_task_id:
            activity, _ = chat_service.get_activity_log(active_task_id)
            for log in activity:
                st.caption(f"⚙️ {log['created_at'][:16]} | {log['content']}")
