# pages/crew_panel.py
# =====================================================
# PANEL KAROLA (EKIPY) - HANDSHAKE 2.0 PREMIUM UI
# =====================================================

import streamlit as st
from datetime import datetime
from services.negotiation_service import NegotiationService
from services.phase_service import PhaseService
from supabase import create_client
import pandas as pd

def render_crew_panel(supabase=None, phase_service=None, negotiation_service=None, change_service=None):
    """
    Premium Panel Ekipy (Karola) - Propozycje, Kontrpropozycje, Historia.
    """
    
    st.header("🔨 Panel Ekipy (Karol)")
    st.markdown("---")
    
    # Inicjalizacja serwisów (fallback jeśli nie przekazane)
    if supabase is None:
        supabase = create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])
    if negotiation_service is None:
        negotiation_service = NegotiationService(supabase)
    if phase_service is None:
        phase_service = PhaseService()
    
    # =====================================================
    # 1. WYBÓR PROJEKTU
    # =====================================================
    
    projects_res = supabase.table("project_metadata").select("id, project_name").execute()
    projects = projects_res.data or []
    if not projects:
        st.warning("Brak projektów w systemie")
        return
    
    project_options = {p["project_name"]: p["id"] for p in projects}
    selected_project_name = st.selectbox(
        "📋 Wybierz projekt",
        options=project_options.keys(),
        key="crew_project_select"
    )
    selected_project_id = project_options[selected_project_name]
    
    st.markdown("---")
    
    # =====================================================
    # 2. DASHBOARD - METRYKI EKIPY
    # =====================================================
    
    all_negotiations = negotiation_service.get_all_negotiations_for_project(selected_project_id)
    
    # Liczenie różnych statusów
    crew_proposals = [n for n in all_negotiations if n['proposed_by'] == 'crew']
    pending_crew = [n for n in crew_proposals if n['status'] == 'pending']
    counter_offers = [n for n in all_negotiations if n['status'] == 'counter_offer']
    accepted_crew = [n for n in crew_proposals if n['status'] == 'accepted']
    rejected_crew = [n for n in all_negotiations if n['status'] == 'rejected']
    
    # Obliczanie sum
    total_proposed = sum(float(n['proposed_price']) for n in crew_proposals)
    total_accepted = sum(float(n['proposed_price']) for n in accepted_crew)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("💰 Zaproponowano", f"{total_proposed:,.0f} zł")
    
    with col2:
        st.metric("✅ Zaakceptowano", f"{total_accepted:,.0f} zł")
    
    with col3:
        st.metric("⏳ Czekające", f"{len(pending_crew)}")
    
    with col4:
        st.metric("💬 Kontrpropozycje", f"{len(counter_offers)}")
    
    with col5:
        st.metric("❌ Odrzucone", f"{len(rejected_crew)}")
    
    st.markdown("---")
    
    # =====================================================
    # 3. TABY
    # =====================================================
    
    tab_my_proposals, tab_counter_offers, tab_accepted, tab_statistics = st.tabs([
        "📤 Moje Propozycje",
        "💬 Kontrpropozycje",
        "✅ Zaakceptowane",
        "📊 Statystyki"
    ])
    
    # =====================================================
    # TAB 1: MOJE PROPOZYCJE
    # =====================================================
    
    with tab_my_proposals:
        st.subheader("📤 Moje Propozycje Cen")
        
        # 1. NOWE ZADANIA DO WYCENY (DODATEK)
        st.markdown("#### 📋 Nowe zadania do wyceny")
        new_tasks = supabase.table("tasks").select("*").eq("project_id", selected_project_id).eq("commercial_status", "not_started").execute().data
        if new_tasks:
            for task in new_tasks:
                render_new_quote_card(task, negotiation_service)
        else:
            st.caption("Brak nowych zadań do wyceny.")

        st.markdown("---")
        
        if not pending_crew:
            st.info("✅ Wszystkie Twoje propozycje zostały rozpatrzone.")
        else:
            st.write(f"📌 **{len(pending_crew)} propozycji czeka na odpowiedź Inwestora**")
            for idx, neg in enumerate(pending_crew):
                render_crew_proposal_card(neg, negotiation_service, is_waiting=True, key=f"pending_{idx}")
    
    # =====================================================
    # TAB 2: KONTRPROPOZYCJE
    # =====================================================
    
    with tab_counter_offers:
        st.subheader("💬 Kontrpropozycje od Inwestora")
        
        pending_for_crew = negotiation_service.get_pending_for_crew(selected_project_id)
        
        if not pending_for_crew:
            st.info("✅ Brak kontrpropozycji do rozpatrzenia.")
        else:
            for idx, neg in enumerate(pending_for_crew):
                render_crew_counter_offer_card(neg, negotiation_service, key=f"counter_{idx}")
    
    # =====================================================
    # TAB 3: ZAAKCEPTOWANE
    # =====================================================
    
    with tab_accepted:
        st.subheader("✅ Zaakceptowane Umowy")
        if not accepted_crew:
            st.info("Brak zaakceptowanych negocjacji")
        else:
            for idx, neg in enumerate(accepted_crew):
                render_crew_accepted_card(neg, negotiation_service, key=f"accepted_{idx}")
    
    # =====================================================
    # TAB 4: STATYSTYKI
    # =====================================================
    
    with tab_statistics:
        st.subheader("📊 Podsumowanie Twoich Przychodów")
        render_crew_statistics(crew_proposals, total_proposed, total_accepted)


# =====================================================
# KOMPONENTY
# =====================================================

def render_new_quote_card(task, negotiation_service):
    """Karta do wysłania nowej wyceny."""
    with st.container(border=True):
        st.markdown(f"### 📍 {task['name']}")
        c1, c2, c3 = st.columns(3)
        with c1:
            p = st.number_input("Cena", min_value=0.0, value=1000.0, key=f"new_p_{task['id']}")
        with col2:
            # col2 not defined in this scope, fixing to c2
            pass
        
        # FIXING THE CARD LOGIC TO MATCH USER'S PREMIUM STYLE
        col1, col2, col3 = st.columns(3)
        with col1:
            p = st.number_input("Cena (zł)", min_value=0.0, value=1000.0, key=f"p_n_{task['id']}")
        with col2:
            d = st.number_input("Dni", min_value=1, value=1, key=f"d_n_{task['id']}")
        with col3:
            n = st.text_input("Notatka", key=f"n_n_{task['id']}")
            
        if st.button("Wyślij wycenę", key=f"btn_n_{task['id']}"):
            success, msg, _ = negotiation_service.propose_price(task['id'], 'crew', p, int(d), n)
            if success:
                st.success(msg)
                st.rerun()

def render_crew_proposal_card(neg, negotiation_service, is_waiting=False, key=""):
    task_info = neg.get('tasks', {})
    task_name = task_info.get('name', 'Nieznane zadanie')
    
    with st.container(border=True):
        col_title, col_status = st.columns([3, 1])
        with col_title:
            st.markdown(f"### 🔨 {task_name}")
        with col_status:
            st.caption("⏳ Czekam na Inwestora")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💰 Cena", f"{neg['proposed_price']:,.0f} zł")
        with col2:
            st.metric("⏱️ Czas", f"{neg['proposed_duration_days'] or 'brak'} dni")
        with col3:
            st.metric("📅 Data", neg['created_at'][:10])
        
        with st.expander("📜 Historia"):
            details = negotiation_service.get_negotiation_details(neg['id'])
            if details and details.get('history'):
                for event in details['history']:
                    render_history_event(event)

def render_crew_counter_offer_card(neg, negotiation_service, key=""):
    task_info = neg.get('tasks', {})
    task_name = task_info.get('name', 'Nieznane zadanie')
    
    with st.container(border=True):
        st.markdown(f"### 💬 {task_name}")
        
        c1, c2 = st.columns(2)
        with c1:
            st.metric("TWOJA CENA", f"{neg['proposed_price']:,.0f} zł")
        with c2:
            st.warning(f"KONTRA INWESTORA: {neg['response_price']:,.0f} zł")
        
        if neg.get('response_notes'):
            st.info(f"💬 Inwestor: {neg['response_notes']}")
        
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("✅ Akceptuję", key=f"acc_{neg['id']}_{key}", use_container_width=True):
                success, msg = negotiation_service.crew_accept_counter_offer(neg['id'])
                if success:
                    st.success(msg)
                    st.rerun()
        with b2:
            if st.button("🔄 Nowa oferta", key=f"cnt_{neg['id']}_{key}", use_container_width=True):
                st.session_state[f"mode_{neg['id']}"] = "counter"
                st.rerun()
        
        if st.session_state.get(f"mode_{neg['id']}") == "counter":
            with st.form(f"form_{neg['id']}"):
                p = st.number_input("Nowa cena", value=float(neg['response_price'] + 100))
                if st.form_submit_button("Wyślij"):
                    success, msg = negotiation_service.crew_counter_counter_offer(neg['id'], p, int(neg.get('proposed_duration_days', 1)))
                    if success:
                        st.session_state[f"mode_{neg['id']}"] = None
                        st.rerun()

def render_crew_accepted_card(neg, negotiation_service, key=""):
    task_info = neg.get('tasks', {})
    task_name = task_info.get('name', 'Nieznane zadanie')
    with st.container(border=True):
        st.markdown(f"### ✅ {task_name}")
        st.metric("Finalna cena", f"{neg['proposed_price']:,.0f} zł")
        st.caption(f"Umowa zawarta: {neg['responded_at'][:10] if neg.get('responded_at') else 'Brak daty'}")

def render_history_event(event):
    action = event['action']
    actor = "👷 Ty" if event['actor'] == 'crew' else "💎 Inwestor"
    dt = event['created_at'][5:16]
    st.write(f"**{dt}** | {actor}: {action} (`{event.get('details', {}).get('price', '')} zł`)")

def render_crew_statistics(proposals, total_proposed, total_accepted):
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Łączna wartość propozycji", f"{total_proposed:,.0f} zł")
    with col2:
        st.metric("Zatwierdzony przychód", f"{total_accepted:,.0f} zł")
    
    df = pd.DataFrame([
        {
            "Zadanie": n.get('tasks', {}).get('name', 'N/A'),
            "Twoja Cena": n['proposed_price'],
            "Status": n['status']
        }
        for n in proposals
    ])
    st.dataframe(df, use_container_width=True)

if __name__ == "__main__":
    st.warning("Uruchom przez app.py")
