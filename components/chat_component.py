# components/chat_component.py
# REMONTIQ CHAT v4.0 — Widok na poziomie projektu

import streamlit as st
import html
from services.chat_service import ChatService
from datetime import datetime


def render_chat_component(supabase, user_id, user_role):
    """
    Czat Budowy v4.0 — wszystkie wiadomości projektu w jednym strumieniu.
    Nie wymaga wyboru zadania — działa jak kanał projektowy.
    """
    chat_service = ChatService(supabase)
    
    # --- Wybór projektu ---
    try:
        projects = supabase.table("project_metadata").select("id, project_name").execute()
        if not projects.data:
            st.warning("Brak projektów.")
            return
        project_dict = {p['project_name']: p['id'] for p in projects.data}
        selected_project_name = st.selectbox("📁 Projekt:", options=list(project_dict.keys()), key="chat_proj_v4")
        selected_project_id = project_dict[selected_project_name]
    except Exception as e:
        st.error(f"Błąd połączenia: {e}")
        return

    st.markdown("### 💬 Czat Budowy")
    st.caption("Wiadomości dla całego projektu. Widoczne dla Inwestora i Ekipy.")
    st.divider()
    
    # --- Historia wiadomości projektu ---
    messages = chat_service.get_project_chat_history(selected_project_id, limit=80)
    
    if not messages:
        st.info("Brak wiadomości. Napisz coś jako pierwszy!")
    else:
        for msg in messages:
            author_role = msg.get('author_role', '')
            is_investor = author_role in ('INVESTOR', 'investor')
            is_system = author_role == 'SYSTEM'
            
            if is_system:
                # Wiadomości systemowe — alerty na pełnej szerokości
                system_content_esc = html.escape(str(msg.get('content','')))
                st.markdown(
                    f"""<div style="background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.3);
                    border-radius:10px; padding:10px 16px; margin:8px 0; font-size:13px; color:#dc2626;">
                    🤖 <b>System</b> · {msg.get('created_at','')[:16]}<br>
                    {system_content_esc}
                    </div>""",
                    unsafe_allow_html=True
                )
            else:
                icon = "👤" if is_investor else "👷"
                align = "human" if is_investor else "ai"
                with st.chat_message(align):
                    st.write(f"**{icon} {msg.get('author_name', 'Ktoś')}**: {msg.get('content', '')}")
                    st.caption(msg.get('created_at', '')[:16])
    
    st.divider()
    
    # --- Formularz wysyłania ---
    # Żeby czat działał, potrzebujemy task_id do task_comments.
    # Używamy "wirtualnego wątku projektowego" — pierwszego zadania lub specjalnego taska.
    tasks_res = supabase.table("tasks").select("id").eq("project_id", selected_project_id).limit(1).execute()
    
    if not tasks_res.data:
        st.warning("⚠️ Brak zadań w projekcie. Dodaj pierwsze zadanie w 'Plan Remontu', aby aktywować czat.")
        return
    
    # Używamy ID pierwszego zadania jako "wirtualnego kanału projektu"
    project_channel_task_id = tasks_res.data[0]['id']
    
    with st.form("chat_send_form_v4", clear_on_submit=True):
        new_msg = st.text_area("✏️ Twoja wiadomość:", height=80, placeholder="Napisz do ekipy / inwestora...")
        if st.form_submit_button("📤 Wyślij", type="primary", use_container_width=True):
            if new_msg.strip():
                res = chat_service.send_message(
                    project_id=selected_project_id,
                    task_id=project_channel_task_id,
                    content=new_msg.strip(),
                    sender_id=user_id,
                    sender_role=user_role,
                    sender_display_name=st.session_state.get("user_name", "Użytkownik")
                )
                if res.get("success"):
                    st.rerun()
                else:
                    st.error(f"Błąd wysyłki: {res.get('error')}")
            else:
                st.warning("Wpisz treść wiadomości.")


def send_system_chat_alert(supabase, project_id: str, message: str):
    """
    Wysyła automatyczny alert systemowy do czatu projektu.
    Używane np. gdy ekipa dodaje zadanie które przeciąga projekt.
    """
    try:
        tasks_res = supabase.table("tasks").select("id").eq("project_id", project_id).limit(1).execute()
        if not tasks_res.data:
            return False
        task_id = tasks_res.data[0]['id']
        
        msg_data = {
            "task_id": task_id,
            "author_name": "System RemontIQ",
            "author_role": "SYSTEM",
            "content": message,
            "created_at": datetime.now().isoformat(),
            "is_deleted": False
        }
        supabase.table("task_comments").insert(msg_data).execute()
        return True
    except Exception as e:
        return False
