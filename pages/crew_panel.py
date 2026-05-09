# pages/crew_panel.py
# =====================================================
# PANEL EKIPY (KAROL) - HANDSHAKE 2.0 PREMIUM UI
# =====================================================

import streamlit as st
import pandas as pd
from datetime import datetime
from services.negotiation_service import NegotiationService
from supabase import create_client

def render_crew_panel(supabase=None, phase_service=None, negotiation_service=None, change_service=None):
    """
    Premium Panel Karola - Zarządzanie pracami, wycenami i negocjacjami.
    """
    
    st.header("👷 Nawigacja Ekipy (Karol)")
    st.markdown("---")
    
    # Inicjalizacja serwisów
    if not supabase:
        supabase = create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])
    if not negotiation_service:
        negotiation_service = NegotiationService(supabase)
    
    # =====================================================
    # 1. WYBÓR PROJEKTU
    # =====================================================
    
    projects_res = supabase.table("project_metadata").select("id, project_name").execute()
    projects = projects_res.data or []
    
    if not projects:
        st.warning("Brak aktywnych projektów")
        return
    
    project_options = {p["project_name"]: p["id"] for p in projects}
    selected_project_name = st.selectbox(
        "🏗️ Wybierz plac budowy",
        options=project_options.keys(),
        key="crew_project_select"
    )
    selected_project_id = project_options[selected_project_name]
    
    # =====================================================
    # 2. DASHBOARD - STATYSTYKI KAROLA
    # =====================================================
    
    neg_stats = negotiation_service.get_negotiation_statistics(selected_project_id)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        new_tasks_count = len(supabase.table("tasks").select("id").eq("project_id", selected_project_id).eq("commercial_status", "not_started").execute().data or [])
        st.metric("📋 Do wyceny", new_tasks_count)
    with col2:
        st.metric("⏳ Czekam na Inwestora", neg_stats.get('pending', 0))
    with col3:
        st.metric("✅ Zatwierdzone", neg_stats.get('approved', 0))
    with col4:
        st.metric("💰 Zaoszczędzono", f"{neg_stats.get('savings', 0):,.0f} zł")

    st.markdown("---")
    
    # =====================================================
    # 3. TABY: WYCENY | MOJE PRACE | HISTORIA
    # =====================================================
    
    tab_quotes, tab_my_tasks, tab_history = st.tabs([
        "💰 WYCENY I NEGOCJACJE",
        "🔨 MOJE PRACE (Realizacja)",
        "📜 HISTORIA UMÓW"
    ])
    
    # =====================================================
    # TAB 1: WYCENY I NEGOCJACJE (PREMIUM)
    # =====================================================
    
    with tab_quotes:
        # SEKCJA A: KONTRPROPOZYCJE OD INWESTORA (PILNE!)
        st.subheader("💬 Kontrpropozycje od Inwestora")
        pending_for_crew = negotiation_service.get_pending_for_crew(selected_project_id)
        
        if pending_for_crew:
            st.warning(f"Masz {len(pending_for_crew)} nowych propozycji od Inwestora!")
            for neg in pending_for_crew:
                render_crew_negotiation_card(neg, negotiation_service, "counter")
        else:
            st.info("Brak nowych kontrpropozycji od Inwestora.")
            
        st.markdown("---")
        
        # SEKCJA B: NOWE ZADANIA DO WYCENY
        st.subheader("📋 Nowe zadania do wyceny")
        new_tasks = supabase.table("tasks").select("*").eq("project_id", selected_project_id).eq("commercial_status", "not_started").execute().data
        
        if not new_tasks:
            st.success("Wszystkie zadania zostały już wycenione!")
        else:
            for task in new_tasks:
                render_task_quote_card(task, negotiation_service)

        st.markdown("---")
        
        # SEKCJA C: PROPOZYCJE W TOKU (CZEKAJĄ NA INWESTORA)
        st.subheader("⏳ Wysłane (Czekają na Inwestora)")
        pending_for_investor = negotiation_service.get_pending_for_investor(selected_project_id)
        if pending_for_investor:
            for neg in pending_for_investor:
                render_crew_negotiation_card(neg, negotiation_service, "pending")
        else:
            st.caption("Brak propozycji czekających na odpowiedź Inwestora.")

    # =====================================================
    # TAB 2: REALIZACJA (🔨 MOJE PRACE)
    # =====================================================
    
    with tab_my_tasks:
        st.subheader("🔨 Zadania w trakcie realizacji")
        approved_tasks = supabase.table("tasks").select("*").eq("project_id", selected_project_id).eq("commercial_status", "approved").execute().data
        
        if not approved_tasks:
            st.info("Brak zatwierdzonych zadań do realizacji.")
        else:
            for task in approved_tasks:
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.markdown(f"### ✅ {task['name']}")
                    with c2:
                        st.metric("Cena", f"{task.get('final_approved_price', 0) or 0:,.0f} zł")

    # =====================================================
    # TAB 3: HISTORIA
    # =====================================================
    
    with tab_history:
        st.subheader("📜 Historia wszystkich negocjacji")
        all_negs = negotiation_service.get_all_negotiations_for_project(selected_project_id)
        if all_negs:
            df_history = pd.DataFrame([
                {
                    "Zadanie": n.get('tasks', {}).get('name', 'N/A'),
                    "Status": n['status'],
                    "Cena": f"{n['proposed_price']:,.0f} zł",
                    "Data": n['created_at'][:10]
                }
                for n in all_negs
            ])
            st.dataframe(df_history, use_container_width=True)

# =====================================================
# KOMPONENTY - KARTY DLA KAROLA
# =====================================================

def render_task_quote_card(task, negotiation_service):
    """Karta do wysłania pierwszej wyceny."""
    with st.container(border=True):
        st.markdown(f"### 📍 {task['name']}")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            price = st.number_input("Twoja cena (zł)", min_value=0.0, value=1000.0, key=f"p_{task['id']}")
        with col2:
            days = st.number_input("Dni robocze", min_value=1, value=1, key=f"d_{task['id']}")
        with col3:
            notes = st.text_input("Notatki", key=f"n_{task['id']}")
            
        if st.button("🚀 Wyślij wycenę", key=f"btn_{task['id']}", use_container_width=True):
            success, msg, neg_id = negotiation_service.propose_price(
                task_id=task['id'],
                proposed_by='crew',
                price=price,
                duration_days=int(days),
                notes=notes
            )
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

def render_crew_negotiation_card(neg, negotiation_service, mode):
    """Karta negocjacji widoczna dla Karola."""
    task_name = neg.get('tasks', {}).get('name', 'Zadanie')
    neg_id = neg['id']
    
    with st.container(border=True):
        st.markdown(f"### 🔨 {task_name}")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("TWOJA OFERTA", f"{neg['proposed_price']:,.0f} zł")
        with c2:
            if neg.get('response_price'):
                st.warning(f"KONTRA INWESTORA: {neg['response_price']:,.0f} zł")
            else:
                st.info("Czekasz na Inwestora")
        with c3:
            st.caption(f"Status: {neg['status']}")

        if mode == "counter":
            st.write("---")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("✅ Akceptuję", key=f"crew_acc_{neg_id}", use_container_width=True):
                    success, msg = negotiation_service.crew_accept_counter_offer(neg_id)
                    if success:
                        st.success(msg)
                        st.rerun()
            with b2:
                if st.button("🔄 Nowa oferta", key=f"crew_rev_{neg_id}", use_container_width=True):
                    st.session_state[f"crew_mode_{neg_id}"] = "revise"
                    st.rerun()
            
            if st.session_state.get(f"crew_mode_{neg_id}") == "revise":
                new_p = st.number_input("Twoja nowa cena", value=float(neg['proposed_price']), key=f"np_{neg_id}")
                if st.button("Wyślij poprawioną", key=f"send_new_{neg_id}"):
                    success, msg = negotiation_service.crew_counter_counter_offer(neg_id, new_p, int(neg.get('proposed_duration_days', 1)))
                    if success:
                        st.session_state[f"crew_mode_{neg_id}"] = None
                        st.rerun()
