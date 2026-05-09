# pages/investor_panel.py
# =====================================================
# PANEL INWESTORA - HANDSHAKE 2.0 PREMIUM UI
# =====================================================

import streamlit as st
from datetime import datetime
from services.negotiation_service import NegotiationService
from services.phase_service import PhaseService
from services.change_service import ChangeService
from supabase import create_client
import pandas as pd

def render_investor_panel(supabase=None, phase_service=None, negotiation_service=None, change_service=None):
    """
    Premium Panel Inwestora - Zarządzanie negocjacjami, zmianami, timeline'em.
    """
    
    # Uwaga: st.set_page_config jest wywoływane w app.py, więc tutaj go pomijamy
    st.header("💎 Panel Inwestora (Ty)")
    st.markdown("---")
    
    # Inicjalizacja serwisów (jeśli nie przekazano, używamy session_state lub tworzymy nowe)
    if not supabase:
        supabase = create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])
    if not negotiation_service:
        negotiation_service = NegotiationService()
    if not phase_service:
        phase_service = PhaseService()
    if not change_service:
        change_service = ChangeService()
    
    # =====================================================
    # 1. WYBÓR PROJEKTU
    # =====================================================
    
    projects = supabase.table("project_metadata").select("id, project_name").execute().data
    if not projects:
        st.warning("Brak projektów w systemie")
        return
    
    project_options = {p["project_name"]: p["id"] for p in projects}
    selected_project_name = st.selectbox(
        "📋 Wybierz projekt",
        options=project_options.keys(),
        key="investor_project_select"
    )
    selected_project_id = project_options[selected_project_name]
    
    st.markdown("---")
    
    # =====================================================
    # 2. DASHBOARD - METRYKI
    # =====================================================
    
    project_data = supabase.table("project_metadata").select("*").eq(
        "id", selected_project_id
    ).single().execute().data
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("💰 Budżet", f"{project_data.get('total_budget', 0) or 0:,.0f} zł")
    
    with col2:
        tasks_res = supabase.table("tasks").select("final_approved_price").eq(
            "project_id", selected_project_id
        ).execute().data
        spent = sum(t.get("final_approved_price", 0) or 0 for t in tasks_res)
        st.metric("💸 Wydano", f"{spent:,.0f} zł")
    
    with col3:
        total_budget = project_data.get('total_budget', 0) or 0
        remaining = total_budget - spent
        st.metric("📊 Pozostało", f"{remaining:,.0f} zł")
    
    with col4:
        pending_negs = negotiation_service.get_pending_for_investor(selected_project_id)
        st.metric("⏳ Czekające", f"{len(pending_negs)}")
    
    with col5:
        all_negs = negotiation_service.get_all_negotiations_for_project(selected_project_id)
        approved = len([n for n in all_negs if n['status'] == 'accepted'])
        st.metric("✅ Zatwierdzone", f"{approved}")
    
    st.markdown("---")
    
    # =====================================================
    # 3. TABY: NEGOCJACJE | ZMIANY | TIMELINE | BUDŻET
    # =====================================================
    
    tab_negotiations, tab_changes, tab_timeline, tab_budget = st.tabs([
        "💰 Negocjacje Cen",
        "📝 Wnioski o Zmiany",
        "📅 Timeline",
        "📊 Analiza Budżetu"
    ])
    
    # =====================================================
    # TAB 1: NEGOCJACJE CEN (PREMIUM UI)
    # =====================================================
    
    with tab_negotiations:
        st.subheader("💰 Negocjacje Cen - Handshake")
        
        if not pending_negs:
            st.info("✅ Brak czekających propozycji. Wszystkie zadania mają ustalone ceny!")
        else:
            st.write(f"📌 **{len(pending_negs)} czekających propozycji**")
            st.markdown("---")
            
            for idx, neg in enumerate(pending_negs):
                render_negotiation_card(
                    neg, 
                    negotiation_service, 
                    selected_project_id,
                    key=f"neg_{idx}"
                )
                st.markdown("---")
        
        # SEKCJA: ZATWIERDZONE NEGOCJACJE
        st.markdown("### ✅ Zatwierdzone Negocjacje")
        all_negs_approved = [n for n in all_negs if n['status'] == 'accepted']
        
        if all_negs_approved:
            approved_df = pd.DataFrame([
                {
                    'Zadanie': n.get('tasks', {}).get('name', 'N/A'),
                    'Cena': f"{n['proposed_price']:,.0f} zł" if n['proposed_by'] == 'crew' else f"{n['response_price']:,.0f} zł",
                    'Status': '✅ Zaakceptowana',
                    'Data': n['created_at'][:10]
                }
                for n in all_negs_approved
            ])
            st.dataframe(approved_df, use_container_width=True)
        else:
            st.info("Brak zatwierdzonych negocjacji")
    
    # =====================================================
    # TAB 2: WNIOSKI O ZMIANY
    # =====================================================
    
    with tab_changes:
        st.subheader("📝 Wnioski o Zmiany")
        
        changes = change_service.get_pending_changes(selected_project_id)
        
        if not changes:
            st.info("Brak wniosków o zmianę")
        else:
            for change in changes:
                render_change_card(change, change_service)
    
    # =====================================================
    # TAB 3: TIMELINE
    # =====================================================
    
    with tab_timeline:
        st.subheader("📅 Timeline Projektu")
        
        phases = phase_service.get_phases(selected_project_id)
        
        if phases:
            render_timeline(phases)
        else:
            st.info("Brak faz w projekcie")
    
    # =====================================================
    # TAB 4: ANALIZA BUDŻETU
    # =====================================================
    
    with tab_budget:
        st.subheader("📊 Analiza Budżetu")
        
        render_budget_analysis(supabase, selected_project_id)


# =====================================================
# KOMPONENTY - KARTY NEGOCJACJI
# =====================================================

def render_negotiation_card(neg, negotiation_service, project_id, key=""):
    """
    Renderuj kartę negocjacji z pełną historią (timeline).
    """
    
    task_info = neg.get('tasks', {})
    task_title = task_info.get('name', 'Nieznane zadanie')
    
    # GŁÓWNY KONTENER
    with st.container(border=True):
        
        # NAGŁÓWEK: Zadanie
        col_title, col_phase = st.columns([3, 1])
        with col_title:
            st.markdown(f"### 🔨 {task_title}")
        
        # SEKCJA: PROPOZYCJA KAROLA (OBECNA)
        st.markdown("#### 👷 **Propozycja Karola (Ekipy)**")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💰 Cena", f"{neg['proposed_price']:,.0f} zł")
        with col2:
            st.metric("⏱️ Czas", f"{neg['proposed_duration_days'] or 'brak'} dni")
        with col3:
            st.metric("📅 Data", neg['created_at'][:10])
        
        if neg.get('proposed_notes'):
            st.write(f"**Notatki:** {neg['proposed_notes']}")
        
        # SEPARATOR
        st.markdown("---")
        
        # SEKCJA: HISTORIA (TIMELINE)
        st.markdown("#### 📜 Historia Negocjacji")
        
        history_details = negotiation_service.get_negotiation_details(neg['id'])
        
        if history_details and history_details.get('history'):
            for event in history_details['history']:
                render_history_event(event)
        else:
            st.caption("Brak dodatkowych zdarzeń")
        
        st.markdown("---")
        
        # SEKCJA: AKCJE (PRZYCISKI)
        st.markdown("#### 🎯 Twoje Działania")
        
        col_accept, col_reject, col_counter = st.columns(3)
        
        with col_accept:
            if st.button(
                "✅ Akceptuj",
                key=f"accept_{neg['id']}_{key}",
                use_container_width=True,
                help="Zaakceptuj propozycję Karola"
            ):
                success, message = negotiation_service.accept_proposal(
                    negotiation_id=neg['id']
                )
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
        
        with col_reject:
            if st.button(
                "❌ Odrzuć",
                key=f"reject_{neg['id']}_{key}",
                use_container_width=True,
                help="Odrzuć propozycję - Karol może wysłać nową"
            ):
                st.session_state[f"reject_form_{neg['id']}"] = True
                st.rerun()
        
        with col_counter:
            if st.button(
                "💬 Kontrpropozycja",
                key=f"counter_{neg['id']}_{key}",
                use_container_width=True,
                help="Zaproponuj inną cenę"
            ):
                st.session_state[f"counter_form_{neg['id']}"] = True
                st.rerun()
        
        # FORMULARZ: ODRZUCENIE
        if st.session_state.get(f"reject_form_{neg['id']}", False):
            st.markdown("##### ❌ Odrzuć Propozycję")
            with st.form(f"reject_form_{neg['id']}"):
                reject_notes = st.text_area(
                    "Powód odrzucenia (opcjonalny)",
                    placeholder="np. Za drogo, zbyt długo..."
                )
                
                col_submit, col_cancel = st.columns(2)
                with col_submit:
                    if st.form_submit_button("Potwierdź Odrzucenie"):
                        success, message = negotiation_service.reject_proposal(
                            negotiation_id=neg_id,
                            investor_notes=reject_notes
                        )
                        if success:
                            st.success(message)
                    if st.form_submit_button("Anuluj"):
                        st.session_state[f"reject_form_{neg['id']}"] = False
                        st.rerun()
        
        # FORMULARZ: KONTRPROPOZYCJA
        if st.session_state.get(f"counter_form_{neg['id']}", False):
            st.markdown("##### 💬 Wyślij Kontrofertę")
            with st.form(f"counter_form_{neg['id']}"):
                counter_price = st.number_input(
                    "Twoja propozycja ceny (zł)",
                    value=float(neg['proposed_price'] * 0.9),
                    min_value=0.0,
                    step=100.0
                )
                counter_duration = st.number_input(
                    "Oczekiwany czas (dni)",
                    value=int(neg['proposed_duration_days'] or 1),
                    min_value=1
                )
                counter_notes = st.text_area(
                    "Notatki (opcjonalnie)",
                    placeholder="np. Możliwość negocjacji do 1500 zł..."
                )
                
                col_submit, col_cancel = st.columns(2)
                with col_submit:
                    if st.form_submit_button("Wyślij Kontrofertę"):
                        success, message = negotiation_service.counter_offer(
                            negotiation_id=neg['id'],
                            counter_price=counter_price,
                            counter_duration_days=int(counter_duration),
                            counter_notes=counter_notes
                        )
                        if success:
                            st.success(message)
                            st.session_state[f"counter_form_{neg['id']}"] = False
                            st.rerun()
                        else:
                            st.error(message)
                
                with col_cancel:
                    if st.form_submit_button("Anuluj"):
                        st.session_state[f"counter_form_{neg['id']}"] = False
                        st.rerun()


def render_history_event(event):
    """
    Renderuj jedno zdarzenie w historii negocjacji.
    """
    action = event['action']
    actor = "👷 Karol" if event['actor'] == 'crew' else "💎 Ty"
    date = event['created_at'][:10]
    time = event['created_at'][11:16]
    
    # Emoji dla akcji
    emoji_map = {
        'proposed': '📤',
        'counter_offered': '💬',
        'accepted': '✅',
        'rejected': '❌'
    }
    emoji = emoji_map.get(action, '📌')
    
    # Opis akcji
    action_text = {
        'proposed': 'zaproponował',
        'counter_offered': 'wysłał kontrofertę',
        'accepted': 'zaakceptował',
        'rejected': 'odrzucił'
    }.get(action, 'zmienił status')
    
    # Render
    col_emoji, col_info = st.columns([0.5, 9.5])
    
    with col_emoji:
        st.write(emoji)
    
    with col_info:
        details = event.get('details', {})
        
        if action == 'proposed':
            price = details.get('price', '?')
            duration = details.get('duration_days', '?')
            st.caption(f"**{date} {time}** — {actor} {action_text}: **{price} zł** ({duration} dni)")
        
        elif action == 'counter_offered':
            price = details.get('counter_price', '?')
            st.caption(f"**{date} {time}** — {actor} {action_text}: **{price} zł**")
        
        elif action == 'accepted':
            st.caption(f"**{date} {time}** — {actor} {action_text} ✅")
        
        elif action == 'rejected':
            reason = details.get('reason', '')
            st.caption(f"**{date} {time}** — {actor} {action_text} ❌" + 
                      (f" ({reason})" if reason else ""))
        
        else:
            st.caption(f"**{date} {time}** — {actor} {action_text}")


# =====================================================
# KOMPONENTY - WNIOSKI O ZMIANY
# =====================================================

def render_change_card(change, change_service):
    """
    Renderuj kartę wniosku o zmianę.
    """
    with st.container(border=True):
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.markdown(f"### 📝 {change.get('reason', 'Wniosek o zmianę')[:30]}...")
        with col2:
            st.caption(f"Status: {change.get('status', 'unknown')}")
        with col3:
            st.caption(f"Data: {change.get('created_at', '')[:10]}")
        
        st.write(change.get('reason', ''))
        
        if change.get('status') == 'pending':
            col_approve, col_reject = st.columns(2)
            with col_approve:
                if st.button("✅ Zatwierdź", key=f"approve_change_{change['id']}"):
                    change_service.approve_change(change['id'], "Ok")
                    st.success("Zmiana zatwierdzona!")
                    st.rerun()
            
            with col_reject:
                if st.button("❌ Odrzuć", key=f"reject_change_{change['id']}"):
                    # Zakładamy że serwis ma reject_change lub podobne
                    st.error("Opcja odrzucenia w budowie")


# =====================================================
# KOMPONENTY - TIMELINE
# =====================================================

def render_timeline(phases):
    """
    Renderuj timeline faz projektu.
    """
    for idx, phase in enumerate(phases):
        col_num, col_content = st.columns([1, 10])
        
        with col_num:
            st.markdown(f"### {idx + 1}")
        
        with col_content:
            st.markdown(f"**{phase.get('phase_name', 'Faza')}**")
            st.caption(f"Status: {phase.get('status', 'unknown')}")


# =====================================================
# KOMPONENTY - ANALIZA BUDŻETU
# =====================================================

def render_budget_analysis(supabase, project_id):
    """
    Renderuj analizę budżetu projektu.
    """
    project = supabase.table("project_metadata").select("*").eq(
        "id", project_id
    ).single().execute().data
    
    tasks = supabase.table("tasks").select("*").eq(
        "project_id", project_id
    ).execute().data
    
    total_budget = project.get('total_budget', 0) or 0
    spent = sum(t.get('final_approved_price', 0) or 0 for t in tasks)
    remaining = total_budget - spent
    
    # METRYKI
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("💰 Budżet", f"{total_budget:,.0f} zł")
    with col2:
        st.metric("💸 Wydano", f"{spent:,.0f} zł")
    with col3:
        percentage = (spent / total_budget * 100) if total_budget > 0 else 0
        st.metric("📊 Procent", f"{percentage:.1f}%")
    
    # PROGRESS BAR
    if total_budget > 0:
        st.progress(min(spent / total_budget, 1.0))
    
    # TABELA ZADAŃ
    st.markdown("### 📋 Podział Kosztów po Zadaniach")
    
    task_costs = []
    for task in tasks:
        task_costs.append({
            'Zadanie': task.get('name', 'N/A'),
            'Cena': f"{task.get('final_approved_price', 0) or 0:,.0f} zł",
            'Status': task.get('commercial_status', 'not_started')
        })
    
    if task_costs:
        df = pd.DataFrame(task_costs)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Brak zadań")


# =====================================================
# MAIN (do testów lokalnych)
# =====================================================

if __name__ == "__main__":
    st.warning("Uruchom przez app.py")
