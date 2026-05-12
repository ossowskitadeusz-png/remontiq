# pages/chat.py
"""
Chat & Activity Feed – Production-ready (STRICT MODE)
"""

import streamlit as st
from datetime import datetime
from services.chat_service import ChatService
import logging
import time

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Chat", page_icon="💬", layout="wide")

# ============================================================================
# VALIDATION
# ============================================================================
if "supabase" not in st.session_state or "user_id" not in st.session_state:
    st.error("⚠️ Sesja wygasła. Zaloguj się ponownie na stronie głównej.")
    st.stop()

supabase = st.session_state.supabase
user_id = st.session_state.user_id
user_role = st.session_state.get("user_role", "CREW_LEAD")
user_name = st.session_state.get("user_name", "Unknown")
chat_service = ChatService(supabase)

# ============================================================================
# SIDEBAR
# ============================================================================
st.sidebar.title("💬 Chat & Activity")

# Pobierz projekty (z filtrowaniem po user_id dla bezpieczeństwa)
try:
    projects = supabase.table("project_metadata")\
        .select("id, project_name")\
        .execute().data or []
    # Uwaga: W v2.0 RLS w bazie sam odfiltruje projekty, 
    # ale tu pobieramy listę dla selektora.
except Exception as e:
    logger.error(f"Failed to fetch projects: {e}")
    st.sidebar.error("❌ Nie mogę załadować projektów.")
    st.stop()

if not projects:
    st.sidebar.warning("Nie masz żadnych projektów.")
    st.stop()

# Selektor projektu
project_options = {p["project_name"]: p["id"] for p in projects}
selected_project_name = st.sidebar.selectbox("📁 Projekt:", list(project_options.keys()))
selected_project_id = project_options[selected_project_name]

# Pobierz zadania (z error handling)
try:
    tasks = supabase.table("tasks")\
        .select("id, name, state")\
        .eq("project_id", selected_project_id)\
        .order("sort_order")\
        .execute().data or []
except Exception as e:
    logger.error(f"Failed to fetch tasks: {e}")
    st.sidebar.error("❌ Nie mogę załadować zadań.")
    st.stop()

if not tasks:
    st.sidebar.warning("Brak zadań w projekcie.")
    st.stop()

# Selektor zadania
task_options = {f"{t['name']} ({t['state']})": t["id"] for t in tasks}
selected_task_name = st.sidebar.selectbox("✅ Zadanie:", list(task_options.keys()))
selected_task_id = task_options[selected_task_name]

st.sidebar.info(f"👤 {user_name} ({user_role})")

# ============================================================================
# MAIN CONTENT
# ============================================================================
tab1, tab2 = st.tabs(["💬 Chat", "📋 Activity Log"])

# ============================================================================
# TAB 1: CHAT
# ============================================================================
with tab1:
    st.header(f"💬 {selected_task_name}")
    
    # Przycisk odświeżania (Manual control)
    col1, col2, col3 = st.columns([3, 1, 1])
    with col2:
        if st.button("🔄 Odśwież", key="refresh_chat", use_container_width=True):
            st.rerun()
    with col3:
        auto_refresh = st.checkbox("⚡ Auto", value=False, key="auto_refresh_chat")
    
    # Load messages with error handling
    try:
        messages, total = chat_service.get_chat_history(selected_task_id, limit=50)
    except Exception as e:
        logger.error(f"Failed to load chat history: {e}")
        st.error(f"❌ Błąd ładowania czatu.")
        messages, total = [], 0
    
    # Display messages
    if messages:
        st.write(f"**📊 Razem: {total} wiadomości**")
        for msg in messages:
            badge = "🔵 Inwestor" if msg["sender_role"] == "INVESTOR" else "🟢 Ekipa" if msg["sender_role"] == "CREW_LEAD" else "⚪ System"
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.write(f"**{badge}** _{msg.get('sender_name', 'Unknown')}_")
                    st.write(msg["content"])
                with c2:
                    st.caption(datetime.fromisoformat(msg["timestamp"]).strftime("%H:%M"))
    else:
        st.info("📭 Brak wiadomości. Bądź pierwszy!")
    
    # Send message form
    st.divider()
    st.subheader("✍️ Nowa wiadomość")
    message_content = st.text_area("Wiadomość:", placeholder="Napisz coś...", height=80, key="msg_input")
    
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        recipient = st.selectbox("Dla:", ["BOTH", "INVESTOR", "CREW"], index=0)
    with c3:
        if st.button("📤 Wyślij", use_container_width=True):
            if message_content.strip():
                result = chat_service.send_message(
                    project_id=selected_project_id,
                    task_id=selected_task_id,
                    content=message_content,
                    sender_id=user_id,
                    sender_role=user_role,
                    sender_display_name=user_name,
                    recipient_role=recipient
                )
                if result["success"]:
                    st.success("✅ Wysłano!")
                    st.rerun()
                else:
                    st.error(f"❌ {result.get('error')}")
            else:
                st.warning("⚠️ Wiadomość nie może być pusta.")

# ============================================================================
# TAB 2: ACTIVITY LOG
# ============================================================================
with tab2:
    st.header(f"📋 Activity Log: {selected_task_name}")
    try:
        events, total = chat_service.get_activity_log(selected_task_id, limit=50)
    except Exception as e:
        logger.error(f"Failed to load activity log: {e}")
        st.error("❌ Błąd ładowania logu zdarzeń.")
        events, total = [], 0
    
    if events:
        st.write(f"**📊 Razem: {total} zdarzeń**")
        for event in events:
            icon = "✅" if event.get("message_type") == "STATUS_CHANGE" else "💰" if event.get("message_type") == "PRICE_UPDATE" else "📝"
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.write(f"**{icon} {event.get('message_type')}**")
                    st.write(event["content"])
                with c2:
                    st.caption(datetime.fromisoformat(event["created_at"]).strftime("%H:%M\n%d.%m"))
    else:
        st.info("📭 Brak zdarzeń.")

# ============================================================================
# AUTO-REFRESH LOGIC
# ============================================================================
if auto_refresh:
    time.sleep(3)
    st.rerun()

st.divider()
st.caption("💬 RemontIQ Chat v1.0 | STRICT MODE ✅")
