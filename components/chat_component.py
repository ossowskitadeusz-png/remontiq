# components/chat_component.py
# REMONTIQ CHAT v4.1 — Widok na poziomie projektu z ręcznym odświeżaniem

import streamlit as st
import html
from services.chat_service import ChatService
from datetime import datetime

@st.fragment(run_every=5)
def render_messages_stream(chat_service, selected_project_id):
    """Auto-odświeżana historia wiadomości projektu (co 5 sekund)."""
    try:
        # Pobieramy komentarze dla wszystkich zadań w projekcie
        tasks_req = chat_service.supabase.table("tasks").select("id").eq("project_id", selected_project_id).execute()
        task_ids = [t['id'] for t in tasks_req.data] if tasks_req.data else []
        
        if not task_ids:
            st.info("Brak wiadomości. Napisz coś jako pierwszy!")
            return
            
        messages_res = chat_service.supabase.table("task_comments")\
            .select("*")\
            .in_("task_id", task_ids)\
            .order("created_at", desc=False)\
            .limit(100)\
            .execute()
        
        messages = messages_res.data or []
    except Exception as e:
        st.error(f"Błąd ładowania historii: {e}")
        return

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
                    author_esc = html.escape(str(msg.get('author_name', 'Ktoś')))
                    content_esc = html.escape(str(msg.get('content', '')))
                    st.write(f"**{icon} {author_esc}**: {content_esc}")
                    st.caption(msg.get('created_at', '')[:16])


def render_chat_component(supabase, user_id, user_role, project_id=None):
    """
    Czat Budowy v4.1 — stabilna wersja z ręcznym odświeżaniem i obsługą błędów.
    """
    chat_service = ChatService(supabase)
    
    # --- Wybór projektu ---
    try:
        # Dynamiczne pobranie projektu jeśli brak przekazanego
        if not project_id:
            proj_meta_res = supabase.table("project_metadata").select("id, project_name").order("created_at", desc=True).limit(1).execute()
            if proj_meta_res.data:
                project_id = proj_meta_res.data[0]['id']

        if project_id:
            selected_project_id = project_id
            # Pobieramy nazwę projektu do nagłówka
            proj_res = supabase.table("project_metadata").select("project_name").eq("id", project_id).execute()
            selected_project_name = proj_res.data[0]['project_name'] if proj_res.data else "Projekt"
            st.markdown(f"📁 **Aktywny Projekt:** {selected_project_name}")
        else:
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

    # Nagłówek i przycisk odświeżania w kolumnach
    c_head, c_ref = st.columns([4, 1])
    with c_head:
        st.markdown("### 💬 Czat Budowy")
        st.caption("Wiadomości dla całego projektu. Widoczne dla Inwestora i Ekipy.")
    with c_ref:
        if st.button("🔄 Odśwież", use_container_width=True):
            st.rerun()

    st.divider()
    
    # --- Historia wiadomości projektu (Auto-odświeżana) ---
    render_messages_stream(chat_service, selected_project_id)
    
    st.divider()
    
    # --- Formularz wysyłania ---
    try:
        tasks_res = supabase.table("tasks").select("id").eq("project_id", selected_project_id).limit(1).execute()
        if not tasks_res.data:
            st.warning("⚠️ Brak zadań w projekcie. Dodaj pierwsze zadanie w 'Plan Remontu', aby aktywować czat.")
            return
        project_channel_task_id = tasks_res.data[0]['id']
    except Exception as e:
        st.error(f"Błąd pobierania zadań projektu: {e}")
        return
    
    with st.form("chat_send_form_v4", clear_on_submit=True):
        new_msg = st.text_area("✏️ Twoja wiadomość:", height=80, placeholder="Napisz do ekipy / inwestora...")
        if st.form_submit_button("📤 Wyślij", type="primary", use_container_width=True):
            if new_msg.strip():
                try:
                    display_name = st.session_state.get("user_name", "Użytkownik")
                    # Oczyszczamy nazwę z ewentualnych legacy PIN labels
                    display_name = display_name.replace(" (PIN)", "").strip()
                    
                    message_payload = {
                        "task_id": project_channel_task_id,
                        "author_name": display_name,
                        "author_role": user_role,
                        "content": new_msg.strip(),
                        "created_at": datetime.now().isoformat()
                    }
                    
                    response = supabase.table("task_comments").insert(message_payload).execute()
                    if response.data:
                        st.success("Wiadomość wysłana!")
                        st.rerun()
                    else:
                        st.error("Błąd: Serwer nie zwrócił potwierdzenia zapisu wiadomości.")
                except Exception as ex:
                    st.error(f"❌ Wyjątek podczas wysyłania wiadomości: {ex}")
            else:
                st.warning("Wpisz treść wiadomości.")


def send_system_chat_alert(supabase, project_id: str, message: str):
    """
    Wysyła automatyczny alert systemowy do czatu projektu.
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
