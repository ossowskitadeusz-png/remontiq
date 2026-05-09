# pages/investor_panel.py
# =====================================================
# PANEL INWESTORA - HANDSHAKE 2.0 PREMIUM UI (FIXED)
# =====================================================

import streamlit as st
import pandas as pd
from datetime import datetime
from services.negotiation_service import NegotiationService
from services.phase_service import PhaseService
from services.change_service import ChangeService
from supabase import create_client

def render_investor_panel(supabase=None, phase_service=None, negotiation_service=None, change_service=None):
    """
    Premium Panel Inwestora - Zarządzanie negocjacjami, zmianami, timeline'em.
    """
    
    st.header("💎 Panel Inwestora (Ty)")
    st.markdown("---")
    
    if not supabase:
        supabase = create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])
    if not negotiation_service:
        negotiation_service = NegotiationService(supabase)
    if not phase_service:
        phase_service = PhaseService()
    if not change_service:
        change_service = ChangeService()
    
    # 1. WYBÓR PROJEKTU
    projects = supabase.table("project_metadata").select("id, project_name").execute().data
    if not projects:
        st.warning("Brak projektów w systemie")
        return
    
    project_options = {p["project_name"]: p["id"] for p in projects}
    selected_project_name = st.selectbox("📋 Wybierz projekt", options=project_options.keys(), key="investor_project_select")
    selected_project_id = project_options[selected_project_name]
    
    st.markdown("---")
    
    # 2. DASHBOARD - METRYKI
    project_data = supabase.table("project_metadata").select("*").eq("id", selected_project_id).single().execute().data
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("💰 Budżet", f"{project_data.get('total_budget', 0) or 0:,.0f} zł")
    
    with col2:
        tasks_res = supabase.table("tasks").select("final_approved_price").eq("project_id", selected_project_id).execute().data
        spent = sum(t.get("final_approved_price", 0) or 0 for t in tasks_res)
        st.metric("💸 Wydano", f"{spent:,.0f} zł")
    
    with col3:
        total_budget = project_data.get('total_budget', 0) or 0
        st.metric("📊 Pozostało", f"{(total_budget - spent):,.0f} zł")
    
    with col4:
        pending_negs = negotiation_service.get_pending_for_investor(selected_project_id)
        st.metric("⏳ Czekające", f"{len(pending_negs)}")
    
    with col5:
        all_negs = negotiation_service.get_all_negotiations_for_project(selected_project_id)
        approved = len([n for n in all_negs if n['status'] == 'accepted'])
        st.metric("✅ Zatwierdzone", f"{approved}")
    
    st.markdown("---")
    
    # 3. TABY
    tab_negotiations, tab_changes, tab_timeline, tab_budget = st.tabs(["💰 Negocjacje Cen", "📝 Wnioski o Zmiany", "📅 Timeline", "📊 Analiza Budżetu"])
    
    with tab_negotiations:
        st.subheader("💰 Negocjacje Cen - Handshake")
        if not pending_negs:
            st.info("✅ Wszystkie ceny są ustalone!")
        else:
            for idx, neg in enumerate(pending_negs):
                render_negotiation_card(neg, negotiation_service, key_suffix=f"investor_{idx}")
    
    with tab_changes:
        st.subheader("📝 Wnioski o Zmiany")
        changes = change_service.get_pending_changes(selected_project_id)
        if not changes:
            st.info("Brak wniosków o zmianę")
        else:
            for change in changes:
                render_change_card(change, change_service)

    with tab_timeline:
        st.subheader("📅 Timeline Projektu")
        phases = phase_service.get_phases(selected_project_id)
        if phases:
            for idx, p in enumerate(phases):
                st.write(f"**{idx+1}. {p['phase_name']}** ({p.get('status', 'not_started')})")

    with tab_budget:
        st.subheader("📊 Analiza Budżetu")
        st.write(f"Wydano {spent:,.0f} zł z {total_budget:,.0f} zł")
        if total_budget > 0:
            st.progress(min(spent / total_budget, 1.0))

# =====================================================
# KOMPONENTY
# =====================================================

def render_negotiation_card(neg, negotiation_service, key_suffix=""):
    neg_id = neg['id']
    task_name = neg.get('tasks', {}).get('name', 'Nieznane zadanie')
    
    with st.container(border=True):
        st.markdown(f"### 🔨 {task_name}")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("OFERTA KAROLA", f"{neg['proposed_price']:,.0f} zł")
        with col2:
            if neg.get('response_price'):
                st.warning(f"TWOJA KONTRA: {neg['response_price']:,.0f} zł")
        with col3:
            st.caption(f"Status: {neg['status']}")

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("✅ Akceptuj", key=f"btn_acc_{neg_id}_{key_suffix}", use_container_width=True):
                success, msg = negotiation_service.accept_proposal(neg_id)
                if success:
                    st.success(msg)
                    st.rerun()
        with b2:
            if st.button("💬 Kontra", key=f"btn_cnt_{neg_id}_{key_suffix}", use_container_width=True):
                st.session_state[f"show_cnt_form_{neg_id}"] = True
                st.rerun()
        with b3:
            if st.button("❌ Odrzuć", key=f"btn_rej_{neg_id}_{key_suffix}", use_container_width=True):
                st.session_state[f"show_rej_form_{neg_id}"] = True
                st.rerun()

        # FORMULARZE Z UNIKALNYMI KLUCZAMI
        if st.session_state.get(f"show_cnt_form_{neg_id}", False):
            with st.form(key=f"form_counter_widget_{neg_id}"):
                st.markdown("##### 💬 Wyślij Kontrofertę")
                p = st.number_input("Cena (zł)", value=float(neg['proposed_price'] * 0.9))
                n = st.text_area("Notatka")
                if st.form_submit_button("Wyślij"):
                    success, msg = negotiation_service.counter_offer(neg_id, p, int(neg.get('proposed_duration_days', 1)), n)
                    if success:
                        st.session_state[f"show_cnt_form_{neg_id}"] = False
                        st.rerun()
                if st.form_submit_button("Anuluj"):
                    st.session_state[f"show_cnt_form_{neg_id}"] = False
                    st.rerun()

        if st.session_state.get(f"show_rej_form_{neg_id}", False):
            with st.form(key=f"form_reject_widget_{neg_id}"):
                st.markdown("##### ❌ Odrzuć Propozycję")
                n = st.text_area("Powód")
                if st.form_submit_button("Potwierdzam Odrzucenie"):
                    success, msg = negotiation_service.reject_proposal(neg_id, n)
                    if success:
                        st.session_state[f"show_rej_form_{neg_id}"] = False
                        st.rerun()
                if st.form_submit_button("Anuluj"):
                    st.session_state[f"show_rej_form_{neg_id}"] = False
                    st.rerun()

def render_change_card(change, change_service):
    with st.container(border=True):
        st.write(f"**Zmiana:** {change.get('reason', '')}")
        if st.button("Zatwierdź", key=f"btn_chg_{change['id']}"):
            change_service.approve_change(change['id'], "OK")
            st.rerun()

if __name__ == "__main__":
    st.warning("Uruchom przez app.py")
