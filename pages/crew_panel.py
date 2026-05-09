# pages/crew_panel.py
# =====================================================
# PANEL EKIPY (KAROL) - HANDSHAKE 2.0 PREMIUM UI (FIXED)
# =====================================================

import streamlit as st
import pandas as pd
from datetime import datetime
from services.negotiation_service import NegotiationService
from services.phase_service import PhaseService
from supabase import create_client

def render_crew_panel(supabase=None, phase_service=None, negotiation_service=None, change_service=None):
    """
    Premium Panel Karola - Zarządzanie pracami, wycenami i negocjacjami.
    """
    
    st.header("👷 Panel Ekipy (Karol)")
    st.markdown("---")
    
    # Inicjalizacja serwisów
    if not supabase:
        supabase = create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])
    if not negotiation_service:
        negotiation_service = NegotiationService(supabase)
    if not phase_service:
        phase_service = PhaseService()
    
    # 1. WYBÓR PROJEKTU
    projects_res = supabase.table("project_metadata").select("id, project_name").execute()
    projects = projects_res.data or []
    if not projects:
        st.warning("Brak projektów w systemie")
        return
    
    project_options = {p["project_name"]: p["id"] for p in projects}
    selected_project_name = st.selectbox("🏗️ Wybierz projekt", options=project_options.keys(), key="crew_project_select")
    selected_project_id = project_options[selected_project_name]
    
    st.markdown("---")
    
    # 2. DASHBOARD - METRYKI
    all_negs = negotiation_service.get_all_negotiations_for_project(selected_project_id)
    approved_negs = [n for n in all_negs if n['status'] == 'accepted']
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        new_tasks = supabase.table("tasks").select("id").eq("project_id", selected_project_id).eq("commercial_status", "not_started").execute().data
        st.metric("📋 Do wyceny", len(new_tasks or []))
    with col2:
        pending_inv = len([n for n in all_negs if n['status'] == 'pending'])
        st.metric("⏳ Czekam na Inwestora", pending_inv)
    with col3:
        st.metric("✅ Zatwierdzone", len(approved_negs))
    with col4:
        total_val = sum(float(n.get('response_price') or n['proposed_price']) for n in approved_negs)
        st.metric("💰 Wartość umów", f"{total_val:,.0f} zł")

    st.markdown("---")
    
    # 3. TABY
    tab_new_proposal, tab_quotes, tab_counter, tab_accepted = st.tabs([
        "➕ Wyślij Nową Wycenę", 
        "📤 Wysłane Propozycje", 
        "💬 Kontrpropozycje", 
        "✅ Moje Umowy"
    ])
    
    with tab_new_proposal:
        st.subheader("➕ Wyślij Nową Wycenę")
        render_new_proposal_form(supabase, negotiation_service, selected_project_id)
        
    with tab_quotes:
        st.subheader("📤 Propozycje wysłane do Inwestora")
        pending_inv_negs = [n for n in all_negs if n['status'] == 'pending']
        if not pending_inv_negs:
            st.success("Wszystkie Twoje propozycje zostały rozpatrzone!")
        else:
            for idx, neg in enumerate(pending_inv_negs):
                render_crew_pending_card(neg, negotiation_service)

    with tab_counter:
        st.subheader("💬 Kontrpropozycje od Inwestora")
        pending_crew = negotiation_service.get_pending_for_crew(selected_project_id)
        if not pending_crew:
            st.info("Brak nowych kontrpropozycji")
        else:
            for idx, neg in enumerate(pending_crew):
                render_crew_counter_card(neg, negotiation_service, key_suffix=f"crew_cnt_{idx}")

    with tab_accepted:
        st.subheader("✅ Zatwierdzone Umowy")
        if not approved_negs:
            st.info("Brak zatwierdzonych umów")
        else:
            for idx, neg in enumerate(approved_negs):
                render_crew_accepted_card(neg, key_suffix=f"crew_acc_{idx}")

# =====================================================
# KOMPONENTY
# =====================================================

def render_new_proposal_form(supabase, negotiation_service, project_id):
    """
    Formularz do wysłania nowej propozycji ceny.
    """
    
    # Pobierz zadania bez aktywnych negocjacji
    all_tasks = supabase.table("tasks").select("id, name, phase_id, final_approved_price").eq(
        "project_id", project_id
    ).execute().data
    
    if not all_tasks:
        st.warning("Brak zadań w tym projekcie")
        return
    
    # Filtruj: pokaż tylko zadania bez zaakceptowanej ceny lub bez aktywnej negocjacji
    available_tasks = []
    for task in all_tasks:
        if task.get('final_approved_price'):
            continue
            
        active_neg = supabase.table("negotiations").select("id").eq(
            "task_id", task['id']
        ).in_("status", ["pending", "counter_offer"]).execute()
        
        if not active_neg.data:
            available_tasks.append(task)
            
    if not available_tasks:
        st.info("✅ Wszystkie zadania mają już ustalone ceny lub czekające propozycje!")
        return
        
    st.markdown("### 📝 Formularz Wyceny")
    
    with st.form("new_proposal_form"):
        task_options = {t['name']: t['id'] for t in available_tasks}
        selected_task_name = st.selectbox("🔨 Wybierz zadanie", options=list(task_options.keys()))
        selected_task_id = task_options[selected_task_name]
        
        proposed_price = st.number_input("💰 Proponowana cena (zł)", min_value=0.0, step=100.0, value=1000.0)
        proposed_duration = st.number_input("⏱️ Szacunkowy czas (dni)", min_value=1, step=1, value=5)
        proposed_notes = st.text_area("📝 Notatki (opcjonalnie)", placeholder="np. Wliczone materiały, robocizna...")
        
        if st.form_submit_button("📤 Wyślij Wycenę", use_container_width=True):
            success, message, neg_id = negotiation_service.propose_price(
                task_id=selected_task_id,
                proposed_by='crew',
                price=proposed_price,
                duration_days=int(proposed_duration),
                notes=proposed_notes
            )
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

def render_crew_pending_card(neg, negotiation_service):
    task_name = neg.get('tasks', {}).get('name', 'Nieznane zadanie')
    with st.container(border=True):
        st.markdown(f"### ⏳ {task_name}")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Twoja Cena", f"{neg['proposed_price']:,.0f} zł")
        with c2:
            st.metric("Czas", f"{neg['proposed_duration_days']} dni")
        with c3:
            st.caption("Czekam na Inwestora")

def render_crew_counter_card(neg, negotiation_service, key_suffix=""):
    neg_id = neg['id']
    task_name = neg.get('tasks', {}).get('name', 'Nieznane zadanie')
    
    with st.container(border=True):
        st.markdown(f"### 💬 {task_name}")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("TWOJA CENA", f"{neg['proposed_price']:,.0f} zł")
        with c2:
            st.warning(f"KONTRA INWESTORA: {neg['response_price']:,.0f} zł")
        
        if neg.get('response_notes'):
            st.info(f"💬 Inwestor: {neg['response_notes']}")
            
        b1, b2 = st.columns(2)
        with b1:
            if st.button("✅ Akceptuję", key=f"btn_acc_{neg_id}_{key_suffix}", use_container_width=True):
                success, msg = negotiation_service.crew_accept_counter_offer(neg_id)
                if success:
                    st.rerun()
        with b2:
            if st.button("🔄 Nowa oferta", key=f"btn_rev_{neg_id}_{key_suffix}", use_container_width=True):
                st.session_state[f"show_crew_form_{neg_id}"] = True
                st.rerun()
        
        if st.session_state.get(f"show_crew_form_{neg_id}", False):
            with st.form(key=f"form_crew_widget_{neg_id}"):
                p = st.number_input("Nowa cena dla Inwestora", value=float(neg['response_price'] + 100))
                if st.form_submit_button("Wyślij"):
                    success, msg = negotiation_service.crew_counter_counter_offer(neg_id, p, int(neg.get('proposed_duration_days', 1)))
                    if success:
                        st.session_state[f"show_crew_form_{neg_id}"] = False
                        st.rerun()
                if st.form_submit_button("Anuluj"):
                    st.session_state[f"show_crew_form_{neg_id}"] = False
                    st.rerun()

def render_crew_accepted_card(neg, key_suffix=""):
    task_name = neg.get('tasks', {}).get('name', 'Nieznane zadanie')
    final_price = neg.get('response_price') or neg['proposed_price']
    with st.container(border=True):
        st.markdown(f"### ✅ {task_name}")
        st.metric("Cena finalna", f"{final_price:,.0f} zł")
        st.caption(f"Status: Zaakceptowano")

if __name__ == "__main__":
    st.warning("Uruchom przez app.py")
