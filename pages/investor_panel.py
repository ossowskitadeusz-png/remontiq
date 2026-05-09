"""
INVESTOR_PANEL.PY — Panel dla Inwestora (Ty)
Odpowiada za: zatwierdzanie negocjacji, zatwierdza zmiany, dashboard budżetu
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import json
from typing import Optional

# Importy serwisów
from services.phase_service import PhaseService
from services.negotiation_service import NegotiationService
from services.change_service import ChangeService


def render_investor_panel(
    supabase,
    phase_service: PhaseService,
    negotiation_service: NegotiationService,
    change_service: ChangeService
):
    """
    Główny panel dla Inwestora (Ciebie).
    Umożliwia zarządzanie budżetem, negocjacje, zatwierdza zmiany.
    """
    
    st.header("💎 Panel Inwestora (Ty)")
    st.subheader("Zarządzaj budżetem, zatwierdź negocjacje, kontroluj zmiany")
    
    # ============================================================================
    # 1. WYBÓR PROJEKTU
    # ============================================================================
    
    try:
        projects_response = supabase.table("project_metadata").select("id, project_name").execute()
        projects = projects_response.data or []
    except Exception as e:
        st.error(f"Błąd przy pobieraniu projektów: {str(e)}")
        return
    
    if not projects:
        st.warning("Brak projektów. Utwórz projekt na stronie głównej.")
        return
    
    project_names = {p["id"]: p["project_name"] for p in projects}
    selected_project_id = st.selectbox(
        "📋 Wybierz projekt",
        options=[p["id"] for p in projects],
        format_func=lambda x: project_names[x],
        key="investor_project_select"
    )
    
    if not selected_project_id:
        return
    
    # ============================================================================
    # 2. DASHBOARD PODSUMOWANIA
    # ============================================================================
    
    st.write("---")
    st.subheader("📊 Szybki Podgląd Projektu")
    
    # Pobierz wszystkie fazy
    phases = phase_service.get_phases(selected_project_id)
    
    # Oblicz sumy
    total_budget = sum(float(p.get("estimated_budget", 0)) for p in phases)
    total_spent = sum(float(p.get("actual_spent", 0)) for p in phases)
    total_remaining = total_budget - total_spent
    
    # Statystyki faz
    completed_phases = sum(1 for p in phases if p.get("status") == "COMPLETED")
    in_progress = sum(1 for p in phases if p.get("status") == "IN_PROGRESS")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("📋 Wszystkich Faz", len(phases))
    
    with col2:
        st.metric("🟢 Ukończonych", completed_phases)
    
    with col3:
        st.metric("🟡 W Toku", in_progress)
    
    with col4:
        st.metric("💰 Budżet", f"{total_budget:,.0f} PLN")
    
    with col5:
        spent_pct = (total_spent / total_budget * 100) if total_budget > 0 else 0
        st.metric("📈 Wydano", f"{spent_pct:.0f}%")
    
    # ============================================================================
    # 3. TABS: Negocjacje | Zmiany | Timeline | Budżet
    # ============================================================================
    
    tab_negotiations, tab_changes, tab_timeline, tab_budget = st.tabs([
        "💰 Negocjacje Cen",
        "⚡ Zatwierdzanie Zmian",
        "📅 Timeline Projektu",
        "💵 Analiza Budżetu"
    ])
    
    # ============================================================================
    # TAB 1: NEGOCJACJE CENA
    # ============================================================================
    
    with tab_negotiations:
        st.subheader("💰 Negocjacje Cen — Propozycje od Karola")
        
        # Pobierz oczekujące negocjacje
        pending_negotiations = negotiation_service.get_pending_negotiations(selected_project_id)
        
        if not pending_negotiations:
            st.success("✅ Brak oczekujących negocjacji. Wszystko uzgodnione!")
        else:
            st.warning(f"⏳ {len(pending_negotiations)} negocjacji czeka na Twoją decyzję")
            
            for negotiation in pending_negotiations:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.write(f"**{negotiation['name']}**")
                        if negotiation.get('description'):
                            st.caption(negotiation.get('description'))
                    
                    with col2:
                        st.write("### Propozycja Karola")
                        st.metric("Cena", f"{negotiation.get('crew_price', 0):,.0f} PLN")
                        st.caption(f"{negotiation.get('estimated_hours', 0)} godzin")
                    
                    with col3:
                        st.write("### Twoja Kontrpropozycja")
                        if negotiation.get('investor_counter_price'):
                            st.metric(
                                "Kontrpropozycja",
                                f"{negotiation.get('investor_counter_price'):,.0f} PLN"
                            )
                            diff = negotiation.get('crew_price', 0) - negotiation.get('investor_counter_price', 0)
                            st.caption(f"Oszczędność: {diff:,.0f} PLN")
                        else:
                            st.info("Brak jeszcze kontrpropozycji")
                    
                    st.write("---")
                    
                    # Akcje
                    action_col1, action_col2, action_col3, action_col4 = st.columns(4)
                    
                    with action_col1:
                        if st.button(
                            "✅ Zaakceptuj",
                            key=f"accept_{negotiation['id']}"
                        ):
                            result = negotiation_service.accept_negotiation(
                                task_id=negotiation['id'],
                                accepted_price=negotiation.get('crew_price', 0),
                                accepted_hours=negotiation.get('estimated_hours'),
                                final_notes="Zaakceptowane przez inwestora"
                            )
                            
                            if result["success"]:
                                st.success("✅ Cena zatwierdzona!")
                                st.rerun()
                            else:
                                st.error(f"❌ Błąd: {result.get('error')}")
                    
                    with action_col2:
                        if st.button(
                            "💬 Kontrpropozycja",
                            key=f"counter_{negotiation['id']}"
                        ):
                            st.session_state[f"counter_mode_{negotiation['id']}"] = True
                            st.rerun()
                    
                    with action_col3:
                        if st.button(
                            "❌ Odrzuć",
                            key=f"reject_{negotiation['id']}"
                        ):
                            st.session_state[f"reject_mode_{negotiation['id']}"] = True
                            st.rerun()
                    
                    with action_col4:
                        st.caption("📋 Historia")
                    
                    # Formularz kontrpropozycji (jeśli włączony)
                    if st.session_state.get(f"counter_mode_{negotiation['id']}", False):
                        st.write("### Twoja Kontrpropozycja")
                        
                        counter_price = st.number_input(
                            f"Nowa cena {negotiation['id'][:8]}",
                            min_value=0.0,
                            value=float(negotiation.get('crew_price', 0) * 0.8),
                            step=50.0,
                            key=f"counter_price_{negotiation['id']}"
                        )
                        
                        counter_hours = st.number_input(
                            f"Godziny {negotiation['id'][:8]}",
                            min_value=1,
                            value=int(negotiation.get('estimated_hours', 8)),
                            key=f"counter_hours_{negotiation['id']}"
                        )
                        
                        counter_reason = st.text_area(
                            f"Powód kontrpropozycji {negotiation['id'][:8]}",
                            placeholder="Np. Cena za wysoka, możesz użyć tańszych materiałów...",
                            key=f"counter_reason_{negotiation['id']}"
                        )
                        
                        col_submit, col_cancel = st.columns(2)
                        
                        with col_submit:
                            if st.button(
                                "📤 Wyślij Kontrpropozycję",
                                key=f"submit_counter_{negotiation['id']}"
                            ):
                                result = negotiation_service.make_counter_offer(
                                    task_id=negotiation['id'],
                                    counter_price=counter_price,
                                    counter_hours=int(counter_hours),
                                    reason=counter_reason
                                )
                                
                                if result["success"]:
                                    st.success(f"✅ Kontrpropozycja wysłana! Oszczędzisz: {result.get('difference', 0):,.0f} PLN")
                                    st.session_state[f"counter_mode_{negotiation['id']}"] = False
                                    st.rerun()
                                else:
                                    st.error(f"❌ Błąd: {result.get('error')}")
                        
                        with col_cancel:
                            if st.button(
                                "Anuluj",
                                key=f"cancel_counter_{negotiation['id']}"
                            ):
                                st.session_state[f"counter_mode_{negotiation['id']}"] = False
                                st.rerun()
                    
                    # Formularz odrzucenia (jeśli włączony)
                    if st.session_state.get(f"reject_mode_{negotiation['id']}", False):
                        st.write("### Odrzuć Propozycję")
                        
                        reject_reason = st.text_area(
                            f"Powód odrzucenia {negotiation['id'][:8]}",
                            placeholder="Np. Za drogo, zadanie zbyt proste...",
                            key=f"reject_reason_{negotiation['id']}"
                        )
                        
                        col_submit, col_cancel = st.columns(2)
                        
                        with col_submit:
                            if st.button(
                                "🔴 Odrzuć",
                                key=f"submit_reject_{negotiation['id']}"
                            ):
                                result = negotiation_service.reject_proposal(
                                    task_id=negotiation['id'],
                                    reason=reject_reason
                                )
                                
                                if result["success"]:
                                    st.info("❌ Propozycja odrzucona. Karol może złożyć nową.")
                                    st.session_state[f"reject_mode_{negotiation['id']}"] = False
                                    st.rerun()
                                else:
                                    st.error(f"❌ Błąd: {result.get('error')}")
                        
                        with col_cancel:
                            if st.button(
                                "Anuluj",
                                key=f"cancel_reject_{negotiation['id']}"
                            ):
                                st.session_state[f"reject_mode_{negotiation['id']}"] = False
                                st.rerun()
        
        # Statystyki negocjacji
        st.write("---")
        st.write("### 📊 Statystyki Negocjacji")
        
        stats = negotiation_service.get_negotiation_statistics(selected_project_id)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("💬 Łącznie", stats.get('total_tasks', 0))
        
        with col2:
            st.metric("⏳ Oczekujące", stats.get('pending_negotiations', 0))
        
        with col3:
            st.metric("✅ Zaakceptowane", stats.get('accepted_negotiations', 0))
        
        with col4:
            st.metric("💰 Zaoszczędzono", f"{stats.get('total_savings', 0):,.0f} PLN")
    
    # ============================================================================
    # TAB 2: ZATWIERDZANIE ZMIAN
    # ============================================================================
    
    with tab_changes:
        st.subheader("⚡ Zarządzanie Zmianami — Wnioski od Karola")
        st.write("Karol prosi o rozszerzenie czasu lub zwiększenie budżetu. Tu decydujesz.")
        
        # Pobierz oczekujące zmiany
        pending_changes = change_service.get_pending_changes(selected_project_id)
        
        if not pending_changes:
            st.success("✅ Brak oczekujących zmian.")
        else:
            st.warning(f"⏳ {len(pending_changes)} zmian czeka na Twoją decyzję")
            
            for change in pending_changes:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.write(f"### {change['change_type']}")
                        st.caption(f"🔹 {change['reason']}")
                    
                    with col2:
                        st.write("### Stara Wartość")
                        old_val = change.get('old_value', {})
                        if isinstance(old_val, str):
                            old_val = json.loads(old_val)
                        
                        if change['change_type'] == 'DURATION_EXTENDED':
                            st.info(f"📅 {old_val.get('planned_end_date', '?')}")
                        elif change['change_type'] == 'BUDGET_INCREASED':
                            st.info(f"💰 {old_val.get('budget', 0):,.0f} PLN")
                    
                    with col3:
                        st.write("### Nowa Wartość")
                        new_val = change.get('new_value', {})
                        if isinstance(new_val, str):
                            new_val = json.loads(new_val)
                        
                        if change['change_type'] == 'DURATION_EXTENDED':
                            st.warning(f"📅 {new_val.get('planned_end_date', '?')}")
                            days_shift = new_val.get('additional_days', 0)
                            st.caption(f"+{days_shift} dni")
                        elif change['change_type'] == 'BUDGET_INCREASED':
                            st.warning(f"💰 {new_val.get('budget', 0):,.0f} PLN")
                            budget_shift = new_val.get('budget', 0) - old_val.get('budget', 0)
                            st.caption(f"+{budget_shift:,.0f} PLN")
                    
                    st.write("---")
                    
                    # Akcje
                    col_approve, col_reject = st.columns(2)
                    
                    with col_approve:
                        if st.button(
                            "✅ Zatwierdź Zmianę",
                            key=f"approve_change_{change['id']}"
                        ):
                            result = change_service.approve_change(
                                change_id=change['id'],
                                approval_notes="Zatwierdzone przez inwestora"
                            )
                            
                            if result["success"]:
                                st.success(f"✅ {result['message']}")
                                st.rerun()
                            else:
                                st.error(f"❌ Błąd: {result.get('error')}")
                    
                    with col_reject:
                        if st.button(
                            "❌ Odrzuć Zmianę",
                            key=f"reject_change_{change['id']}"
                        ):
                            st.session_state[f"reject_change_{change['id']}"] = True
                            st.rerun()
                    
                    # Formularz odrzucenia
                    if st.session_state.get(f"reject_change_{change['id']}", False):
                        rejection_reason = st.text_area(
                            f"Powód odrzucenia {change['id'][:8]}",
                            placeholder="Np. Budżet już wyczerpany, czas się mieści...",
                            key=f"change_reject_reason_{change['id']}"
                        )
                        
                        if st.button(
                            "🔴 Potwierdź Odrzucenie",
                            key=f"confirm_reject_{change['id']}"
                        ):
                            result = change_service.reject_change(
                                change_id=change['id'],
                                rejection_reason=rejection_reason
                            )
                            
                            if result["success"]:
                                st.info("❌ Zmiana odrzucona")
                                st.session_state[f"reject_change_{change['id']}"] = False
                                st.rerun()
                            else:
                                st.error(f"❌ Błąd: {result.get('error')}")
        
        # Historia zmian
        st.write("---")
        st.write("### 📋 Historia Zmian")
        
        all_changes = change_service.get_change_history(selected_project_id, limit=20)
        
        if all_changes:
            df_changes = pd.DataFrame([
                {
                    "Typ": c.get('change_type'),
                    "Status": c.get('status'),
                    "Powód": c.get('reason')[:50] + "..." if len(c.get('reason', '')) > 50 else c.get('reason'),
                    "Data": c.get('created_at')[:10]
                }
                for c in all_changes
            ])
            st.dataframe(df_changes, use_container_width=True)
        else:
            st.info("Brak historii zmian")
    
    # ============================================================================
    # TAB 3: TIMELINE PROJEKTU
    # ============================================================================
    
    with tab_timeline:
        st.subheader("📅 Timeline Projektu")
        st.write("Chronologiczny przegląd wszystkich faz.")
        
        if not phases:
            st.info("Brak faz w projekcie")
        else:
            timeline = phase_service.get_project_timeline(selected_project_id)
            
            for phase_data in timeline['timeline']:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.write(f"### {phase_data['phase_number']}. {phase_data['phase_name']}")
                        st.caption(f"{phase_data['planned_start']} → {phase_data['planned_end']}")
                    
                    with col2:
                        status_emoji = {
                            "PLANNING": "🔵",
                            "IN_PROGRESS": "🟡",
                            "COMPLETED": "🟢",
                            "PAUSED": "🔴"
                        }
                        st.write(f"{status_emoji.get(phase_data['status'], '⚪')} **{phase_data['status']}**")
                    
                    with col3:
                        progress = phase_data.get('progress_percent', 0)
                        st.metric("Postęp", f"{progress:.0f}%")
                    
                    # Progress bar
                    st.progress(progress / 100)
    
    # ============================================================================
    # TAB 4: ANALIZA BUDŻETU
    # ============================================================================
    
    with tab_budget:
        st.subheader("💵 Analiza Budżetu")
        
        # Tabela budżetu po fazach
        budget_data = []
        for phase in phases:
            financial = phase_service.get_phase_financial_status(phase['id'])
            
            budget_data.append({
                "Faza": phase['phase_name'],
                "Budżet (PLN)": f"{financial.get('estimated_budget', 0):,.0f}",
                "Wydano (PLN)": f"{financial.get('actual_spent', 0):,.0f}",
                "Pozostało (PLN)": f"{financial.get('remaining_budget', 0):,.0f}",
                "Wykorzystanie": f"{financial.get('budget_utilization_percent', 0):.0f}%",
                "Status": financial.get('status')
            })
        
        if budget_data:
            st.dataframe(
                pd.DataFrame(budget_data),
                use_container_width=True
            )
        else:
            st.info("Brak danych budżetowych")
        
        # Sumy
        st.write("---")
        st.write("### 📊 Podsumowanie")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("💰 Całkowity Budżet", f"{total_budget:,.0f} PLN")
        
        with col2:
            st.metric("📈 Wydano", f"{total_spent:,.0f} PLN")
        
        with col3:
            st.metric("🏦 Pozostało", f"{total_remaining:,.0f} PLN")
        
        with col4:
            utilization = (total_spent / total_budget * 100) if total_budget > 0 else 0
            st.metric("📊 Wykorzystanie", f"{utilization:.0f}%")
        
        # Ostrzeżenie jeśli budget przekroczony
        if total_remaining < 0:
            st.error(f"⚠️ UWAGA: Budżet przekroczony o {abs(total_remaining):,.0f} PLN!")
        elif total_remaining < (total_budget * 0.1):
            st.warning(f"⚠️ Zbliżasz się do limitu budżetu ({total_remaining:,.0f} PLN pozostało)")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    st.error("Ten plik powinien być importowany z app.py")
