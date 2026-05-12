# components/chat_component.py

import streamlit as st
from services.chat_service import ChatService
from datetime import datetime

def render_chat_component(supabase, user_id, user_role):
    """
    Komponent czatu wstrzyknięty bezpośrednio do app.py
    ✅ Działa w tym samym procesie co logowanie
    ✅ Brak izolacji sesji
    """
    
    st.subheader("💬 Czat Budowy")
    
    # Debug (można usunąć potem)
    with st.expander("🛠️ Diagnostyka sesji", expanded=False):
        st.write(f"✅ User ID: {user_id}")
        st.write(f"✅ Role: {user_role}")
    
    # ============================================================
    # Wybór projektu
    # ============================================================
    try:
        # Pobieramy projekty dostępne dla użytkownika
        # Wersja uproszczona: pobieramy wszystkie, RLS (jeśli jest) odfiltruje
        projects = supabase.table("project_metadata").select("id, project_name").execute()
        
        if not projects.data:
            st.warning("❌ Brak projektów. Stwórz projekt w panelu.")
            return
        
        project_dict = {p['project_name']: p['id'] for p in projects.data}
        selected_project_name = st.selectbox(
            "Wybierz projekt:",
            options=list(project_dict.keys()),
            key="chat_project_selector"
        )
        selected_project_id = project_dict[selected_project_name]
        
    except Exception as e:
        st.error(f"Błąd ładowania projektów: {e}")
        return
    
    # ============================================================
    # Wybór zadania
    # ============================================================
    try:
        # Uwaga: w bazie kolumna to 'name' a nie 'task_name' (sprawdziłem schemat)
        tasks = supabase.table("tasks").select("id, name").eq("project_id", selected_project_id).execute()
        
        if not tasks.data:
            st.info("Brak zadań w tym projekcie.")
            return
        
        task_dict = {t['name']: t['id'] for t in tasks.data}
        selected_task_name = st.selectbox(
            "Wybierz zadanie:",
            options=list(task_dict.keys()),
            key="chat_task_selector"
        )
        selected_task_id = task_dict[selected_task_name]
        
    except Exception as e:
        st.error(f"Błąd ładowania zadań: {e}")
        return
    
    # ============================================================
    # Tabs: Czat vs Activity Log
    # ============================================================
    tab_msg, tab_log = st.tabs(["💬 Wiadomości", "📋 Activity Log"])
    
    chat_service = ChatService(supabase)
    
    with tab_msg:
        # Historia czatu
        try:
            # get_chat_history zwraca (messages, total)
            messages, total = chat_service.get_chat_history(selected_task_id)
            
            if messages:
                for msg in messages:
                    # Sender name fallback
                    display_name = msg.get('sender_display_name') or msg.get('sender_name') or "System"
                    with st.chat_message(display_name):
                        st.write(msg['content'])
                        st.caption(f"{msg.get('timestamp', msg.get('created_at'))} | {msg['sender_role']}")
            else:
                st.info("📭 Brak wiadomości w tym zadaniu. Bądź pierwszy!")
            
        except Exception as e:
            st.error(f"Błąd ładowania czatu: {e}")
        
        # Wysyłanie wiadomości
        st.divider()
        with st.container():
            message_content = st.text_input("Napisz wiadomość...", key="chat_input_text")
            c1, c2 = st.columns([3, 1])
            with c1:
                recipient_role = st.selectbox(
                    "Widoczne dla:",
                    options=["BOTH", "INVESTOR", "CREW"],
                    index=0,
                    key="chat_recipient_opt"
                )
            with c2:
                if st.button("📤 Wyślij", use_container_width=True, type="primary"):
                    if message_content:
                        result = chat_service.send_message(
                            project_id=selected_project_id,
                            task_id=selected_task_id,
                            sender_id=user_id,
                            sender_display_name=st.session_state.get("user_name", f"User {user_id[:8]}"),
                            recipient_role=recipient_role,
                            content=message_content
                        )
                        if result["success"]:
                            st.success("✅ Wysłano!")
                            st.rerun()
                        else:
                            st.error(f"❌ {result.get('error')}")
                    else:
                        st.warning("Wiadomość nie może być pusta.")

    with tab_log:
        # Activity Log
        try:
            activity, total = chat_service.get_activity_log(selected_task_id)
            
            if activity:
                for log in activity:
                    icon = "✅" if log.get('message_type') == "STATUS_CHANGE" else "💰" if log.get('message_type') == "PRICE_UPDATE" else "📝"
                    st.info(f"{icon} {log['content']}")
                    st.caption(f"{log.get('created_at')}")
            else:
                st.info("Brak zmian w historii zadania.")
            
        except Exception as e:
            st.error(f"Błąd ładowania Activity Log: {e}")
