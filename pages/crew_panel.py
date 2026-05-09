"""
CREW_PANEL.PY — Panel dla Karola (Ekipy Remontowej)
Odpowiada za: tworzenie faz, propozycje cen, zarządzanie zadaniami
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
from typing import Optional

# Importy serwisów
from services.phase_service import PhaseService
from services.negotiation_service import NegotiationService
from services.change_service import ChangeService


def render_crew_panel(
    supabase,
    phase_service: PhaseService,
    negotiation_service: NegotiationService,
    change_service: ChangeService
):
    """
    Główny panel dla Karola (ekipy remontowej).
    Umożliwia zarządzanie fazami, propozycje cen, żądania zmian.
    """
    
    st.header("🏗️ Panel Ekipy Remontowej (Karol)")
    st.subheader("Zarządzaj fazami, proponuj ceny, żądaj zmian")
    
    # ============================================================================
    # 1. WYBÓR PROJEKTU
    # ============================================================================
    
    try:
        # POPRAWKA: Używamy project_metadata zamiast projects
        projects_response = supabase.table("project_metadata").select("id, project_name").execute()
        projects = projects_response.data or []
    except Exception as e:
        st.error(f"Błąd przy pobieraniu projektów: {str(e)}")
        return
    
    if not projects:
        st.warning("Brak projektów. Najpierw utwórz projekt w panelu głównym.")
        return
    
    project_names = {p["id"]: p["project_name"] for p in projects}
    selected_project_id = st.selectbox(
        "📋 Wybierz projekt",
        options=[p["id"] for p in projects],
        format_func=lambda x: project_names[x]
    )
    
    if not selected_project_id:
        return
    
    # ============================================================================
    # 2. TABS: Fazy | Propozycje Cen | Żądania Zmian
    # ============================================================================
    
    tab_phases, tab_proposals, tab_changes = st.tabs([
        "📊 Fazy Projektu",
        "💰 Moje Propozycje Cen",
        "⚡ Żądania Zmian"
    ])
    
    # ============================================================================
    # TAB 1: FAZY PROJEKTU
    # ============================================================================
    
    with tab_phases:
        st.subheader("📊 Zarządzanie Fazami")
        
        # Pobierz fazy
        phases = phase_service.get_phases(selected_project_id)
        
        if not phases:
            st.info("Brak faz w tym projekcie. Stwórz nową fazę poniżej.")
        else:
            # Wyświetl istniejące fazy
            st.write("### Obecne fazy:")
            
            for phase in phases:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.write(f"**{phase['phase_number']}. {phase['phase_name']}**")
                        st.caption(f"{phase['planned_start_date']} → {phase['planned_end_date']}")
                        if phase.get('description'):
                            st.text(phase['description'])
                    
                    with col2:
                        status_color = {
                            "PLANNING": "🔵",
                            "IN_PROGRESS": "🟡",
                            "COMPLETED": "🟢",
                            "PAUSED": "🔴"
                        }
                        st.write(f"{status_color.get(phase['status'], '⚪')} {phase['status']}")
                    
                    with col3:
                        # Pobierz postęp
                        progress = phase_service.get_phase_progress(phase['id'])
                        st.metric(
                            "Postęp",
                            f"{progress.get('progress_percent', 0):.0f}%"
                        )
        
        # ======================================================================
        # FORMULARZ: Nowa Faza
        # ======================================================================
        
        st.write("### ➕ Stwórz Nową Fazę")
        
        with st.form("new_phase_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                phase_name = st.text_input("Nazwa fazy", placeholder="np. Demolka, Elektryka")
                phase_number = st.number_input(
                    "Numer fazy",
                    min_value=1,
                    max_value=20,
                    value=len(phases) + 1 if phases else 1
                )
                planned_start = st.date_input("Data rozpoczęcia")
            
            with col2:
                description = st.text_area(
                    "Opis fazy",
                    placeholder="Szczegóły pracy do wykonania..."
                )
                planned_duration_days = st.number_input(
                    "Szacunkowy czas trwania (dni)",
                    min_value=1,
                    max_value=180,
                    value=7
                )
                estimated_budget = st.number_input(
                    "Szacunkowy budżet (PLN)",
                    min_value=0.0,
                    value=5000.0,
                    step=100.0
                )
            
            # Data zakończenia auto-obliczona
            planned_end = planned_start + timedelta(days=planned_duration_days)
            st.info(f"📅 Planowana data zakończenia: **{planned_end.isoformat()}**")
            
            # Zależności (opcjonalnie)
            if phases:
                depends_on = st.multiselect(
                    "Ta faza zależy od (opcjonalnie):",
                    options=[p['id'] for p in phases],
                    format_func=lambda x: next(
                        (p['phase_name'] for p in phases if p['id'] == x),
                        "?"
                    )
                )
            else:
                depends_on = []
            
            submit_btn = st.form_submit_button("✅ Utwórz Fazę", use_container_width=True)
            
            if submit_btn:
                if not phase_name:
                    st.error("Podaj nazwę fazy!")
                else:
                    result = phase_service.create_phase(
                        project_id=selected_project_id,
                        phase_name=phase_name,
                        phase_number=int(phase_number),
                        planned_start_date=planned_start.isoformat(),
                        planned_end_date=planned_end.isoformat(),
                        description=description,
                        estimated_budget=estimated_budget,
                        created_by_crew_id="KAROL",
                        depends_on_phase_ids=depends_on
                    )
                    
                    if result["success"]:
                        st.success(result["message"])
                        st.rerun()
                    else:
                        st.error(f"❌ Błąd: {result.get('err    # TAB 2: PROPOZYCJE CEN
    # ============================================================================
    
    with tab_proposals:
        st.subheader("💰 Moje Propozycje Cen")
        st.write("Tutaj możesz proponować ceny za zadania. Inwestor je zatwierdzi lub zaproponuje kontrpropozycję.")
        
        # 1. ZADANIA CZEKAJĄCE NA PIERWSZĄ WYCENĘ
        try:
            tasks_response = supabase.table("tasks").select(
                "id, name, phase_id, description, commercial_status"
            ).eq("project_id", selected_project_id).execute()
            
            tasks = tasks_response.data or []
        except Exception as e:
            st.error(f"Błąd: {str(e)}")
            tasks = []
        
        # Filtruj zadania, które nie mają jeszcze negocjacji
        tasks_to_quote = [
            t for t in tasks
            if t.get("commercial_status") in ["not_started", "rejected"]
        ]
        
        if tasks_to_quote:
            st.write(f"### 📋 Zadania do wyceny ({len(tasks_to_quote)})")
            for task in tasks_to_quote:
                with st.container(border=True):
                    st.write(f"**{task['name']}**")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        price = st.number_input(f"Cena {task['id'][:4]}", min_value=0.0, value=500.0, key=f"p_{task['id']}")
                    with col2:
                        days = st.number_input(f"Dni {task['id'][:4]}", min_value=1, value=1, key=f"d_{task['id']}")
                    with col3:
                        notes = st.text_input(f"Uwagi {task['id'][:4]}", key=f"n_{task['id']}")
                    
                    if st.button("Wyślij Wycenę", key=f"btn_{task['id']}"):
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

        # 2. KONTRPROPOZYCJE OD INWESTORA (WYMAGAJĄ REAKCJI KAROLA)
        st.write("---")
        st.write("### 💬 Kontrpropozycje od Inwestora (Wymagają Twojej decyzji)")
        
        pending_for_crew = negotiation_service.get_pending_for_crew(selected_project_id)
        
        if not pending_for_crew:
            st.info("Brak oczekujących kontrpropozycji od Inwestora.")
        else:
            for neg in pending_for_crew:
                task_name = neg.get('tasks', {}).get('name', 'Zadanie')
                with st.container(border=True):
                    st.write(f"**{task_name}**")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Twoja cena:**")
                        st.write(f"{neg['proposed_price']} PLN")
                    with col2:
                        st.warning("**Propozycja Inwestora:**")
                        st.write(f"{neg['response_price']} PLN")
                        if neg.get('response_notes'):
                            st.caption(f"Uzasadnienie: {neg['response_notes']}")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ Akceptuję cenę Inwestora", key=f"crew_acc_{neg['id']}"):
                            success, msg = negotiation_service.crew_accept_counter_offer(neg['id'])
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                    with c2:
                        if st.button("🔄 Wyślij nową propozycję", key=f"crew_rev_{neg['id']}"):
                            st.session_state[f"crew_rev_mode_{neg['id']}"] = True
                            st.rerun()
                    
                    if st.session_state.get(f"crew_rev_mode_{neg['id']}", False):
                        new_p = st.number_input("Twoja nowa cena", value=float(neg['proposed_price']), key=f"new_p_{neg['id']}")
                        if st.button("Wyślij nową ofertę", key=f"send_new_{neg['id']}"):
                            success, msg = negotiation_service.crew_counter_counter_offer(
                                negotiation_id=neg['id'],
                                crew_counter_price=new_p,
                                crew_counter_duration_days=int(neg['proposed_duration_days'])
                            )
                            if success:
                                st.success(msg)
                                st.session_state[f"crew_rev_mode_{neg['id']}"] = False
                                st.rerun()
                            else:
                                st.error(msg)

        # 3. STATUS MOICH WYSŁANYCH PROPOZYCJI
        st.write("---")
        st.write("### ⏳ Wysłane propozycje (Czekają na Inwestora)")
        pending_for_investor = negotiation_service.get_pending_for_investor(selected_project_id)
        if pending_for_investor:
            for p in pending_for_investor:
                st.info(f"🔹 {p.get('tasks', {}).get('name')}: {p['proposed_price']} PLN (Status: {p['status']})")
        else:
            st.caption("Brak propozycji czekających na ruch Inwestora.")
            st.dataframe(df_pending, use_container_width=True)
        else:
            st.info("Brak oczekujących negocjacji")
    
    # ============================================================================
    # TAB 3: ŻĄDANIA ZMIAN
    # ============================================================================
    
    with tab_changes:
        st.subheader("⚡ Żądania Zmian (Opóźnienia, Budżet)")
        st.write("Jeśli potrzebujesz więcej czasu lub pieniędzy, złóż tu wniosek.")
        
        phases = phase_service.get_phases(selected_project_id)
        
        if not phases:
            st.warning("Brak faz. Stwórz fazę najpierw.")
        else:
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("### ⏱️ Żądanie Rozszerzenia Czasu")
                
                selected_phase = st.selectbox(
                    "Wybierz fazę",
                    options=[p['id'] for p in phases],
                    format_func=lambda x: next(
                        (p['phase_name'] for p in phases if p['id'] == x),
                        "?"
                    ),
                    key="phase_time"
                )
                
                additional_days = st.number_input(
                    "Ile dni dodatkowo?",
                    min_value=1,
                    max_value=60,
                    value=3,
                    key="additional_days"
                )
                
                time_reason = st.text_area(
                    "Powód opóźnienia",
                    placeholder="np. Materiały spóźnione, bardziej skomplikowana praca...",
                    key="time_reason"
                )
                
                if st.button("📅 Wyślij Wniosek o Rozszerzenie", use_container_width=True):
                    result = change_service.request_time_extension(
                        phase_id=selected_phase,
                        additional_days=int(additional_days),
                        reason=time_reason
                    )
                    
                    if result["success"]:
                        st.success("✅ Wniosek wysłany!")
                        st.rerun()
                    else:
                        st.error(f"❌ Błąd: {result.get('error')}")
            
            with col2:
                st.write("### 💵 Żądanie Wzrostu Budżetu")
                
                selected_phase_budget = st.selectbox(
                    "Wybierz fazę",
                    options=[p['id'] for p in phases],
                    format_func=lambda x: next(
                        (p['phase_name'] for p in phases if p['id'] == x),
                        "?"
                    ),
                    key="phase_budget"
                )
                
                additional_budget = st.number_input(
                    "O ile zwiększyć budżet (PLN)?",
                    min_value=100.0,
                    max_value=50000.0,
                    value=1000.0,
                    step=100.0,
                    key="additional_budget"
                )
                
                budget_reason = st.text_area(
                    "Powód wzrostu",
                    placeholder="np. Materiały droższe niż przewidywano...",
                    key="budget_reason"
                )
                
                if st.button("💰 Wyślij Wniosek o Budżet", use_container_width=True):
                    result = change_service.request_budget_increase(
                        phase_id=selected_phase_budget,
                        additional_amount=additional_budget,
                        reason=budget_reason
                    )
                    
                    if result["success"]:
                        st.success("✅ Wniosek wysłany!")
                        st.rerun()
                    else:
                        st.error(f"❌ Błąd: {result.get('error')}")
        
        # Historia zmian
        st.write("### 📋 Historia Moich Wniosków")
        
        changes = change_service.get_change_history(selected_project_id, limit=20)
        
        if changes:
            df_changes = pd.DataFrame([
                {
                    "Typ": c.get('change_type'),
                    "Status": c.get('status'),
                    "Powód": c.get('reason'),
                    "Data": c.get('created_at')[:10]
                }
                for c in changes
            ])
            st.dataframe(df_changes, use_container_width=True)
        else:
            st.info("Brak wniosków")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    st.error("Ten plik powinien być importowany z app.py")
