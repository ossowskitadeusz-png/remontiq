"""
INVESTOR_PANEL.PY — Panel dla Inwestora (Ty) - WERSJA PREMIUM 2.0
Odpowiada za: zatwierdzanie negocjacji (Handshake 2.0), dashboard budżetu, timeline
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
    
    st.title("💎 Centrum Dowodzenia Inwestora")
    
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
        "📋 Wybierz projekt do zarządzania",
        options=[p["id"] for p in projects],
        format_func=lambda x: project_names[x],
        key="investor_project_select"
    )
    
    if not selected_project_id:
        return
    
    # ============================================================================
    # 2. DASHBOARD PODSUMOWANIA (Górne metryki)
    # ============================================================================
    
    st.write("---")
    
    # Pobierz wszystkie fazy
    phases = phase_service.get_phases(selected_project_id)
    
    # Oblicz sumy
    total_budget = sum(float(p.get("estimated_budget", 0)) for p in phases)
    total_spent = sum(float(p.get("actual_spent", 0)) for p in phases)
    total_remaining = total_budget - total_spent
    
    # Statystyki negocjacji (dla metryk)
    neg_stats = negotiation_service.get_negotiation_statistics(selected_project_id)
    
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("🏗️ Fazy", len(phases))
    with m2:
        st.metric("💰 Budżet", f"{total_budget:,.0f} zł")
    with m3:
        spent_pct = (total_spent / total_budget * 100) if total_budget > 0 else 0
        st.metric("📈 Wydano", f"{spent_pct:.1f}%", f"-{total_remaining:,.0f} zł")
    with m4:
        st.metric("⏳ Czekające ceny", neg_stats.get('pending', 0), delta_color="inverse")
    with m5:
        st.metric("🛡️ Zaoszczędzono", f"{neg_stats.get('savings', 0):,.0f} zł", delta="PLN")

    # ============================================================================
    # 3. TABS: Negocjacje | Zmiany | Timeline | Budżet
    # ============================================================================
    
    tab_negotiations, tab_changes, tab_timeline, tab_budget = st.tabs([
        "💰 HANDSHAKE (Ceny)",
        "⚡ ZMIANY W PLANIE",
        "📅 HARMONOGRAM",
        "💵 ANALIZA KOSZTÓW"
    ])
    
    # ============================================================================
    # TAB 1: NEGOCJACJE (HANDSHAKE 2.0)
    # ============================================================================
    
    with tab_negotiations:
        st.subheader("📋 Propozycje cenowe od Karola")
        
        # Pobierz aktywne negocjacje
        pending_negs = negotiation_service.get_pending_for_investor(selected_project_id)
        
        if not pending_negs:
            st.success("✅ Wszystkie ceny są uzgodnione. Brak nowych propozycji.")
        else:
            for neg in pending_negs:
                # Wyciągamy dane
                neg_id = neg['id']
                task_info = neg.get('tasks', {})
                task_name = task_info.get('name', 'Zadanie')
                
                # Budujemy kartę negocjacji
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    
                    with c1:
                        st.markdown(f"### 📍 {task_name}")
                        st.caption(f"ID Negocjacji: {neg_id[:8]}")
                        if neg.get('proposed_notes'):
                            st.info(f"💬 **Karol pisze:** {neg['proposed_notes']}")
                        
                        # HISTORIA (Oś czasu)
                        with st.expander("📜 Pokaż historię negocjacji", expanded=False):
                            details = negotiation_service.get_negotiation_details(neg_id)
                            if details and details.get('history'):
                                for h in details['history']:
                                    icon = "👷" if h['actor'] == 'crew' else "👤"
                                    dt = datetime.fromisoformat(h['created_at']).strftime("%d.%m %H:%M")
                                    action_name = {
                                        'proposed': 'zaproponował cenę',
                                        'counter_offered': 'wysłał kontrpropozycję',
                                        'rejected': 'odrzucił ofertę',
                                        'accepted': 'zaakceptował warunki'
                                    }.get(h['action'], h['action'])
                                    
                                    st.write(f"**{dt}** | {icon} {h['actor'].capitalize()} {action_name}")
                                    if 'price' in h['details']:
                                        st.write(f"→ Kwota: `{h['details']['price']:,} zł`")
                            else:
                                st.caption("Brak historii dla tego zadania.")

                    with c2:
                        st.markdown("<br>", unsafe_allow_html=True)
                        st.metric("OFERTA KAROLA", f"{neg['proposed_price']:,.0f} zł")
                        st.caption(f"Przewidywany czas: {neg['proposed_duration_days']} dni")
                    
                    with c3:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if neg.get('response_price'):
                            st.metric("TWOJA KONTRA", f"{neg['response_price']:,.0f} zł", 
                                      delta=f"{neg['response_price'] - neg['proposed_price']:,.0f} zł")
                        else:
                            st.write("### Brak kontry")
                            st.caption("Czekasz na decyzję")

                    st.write("---")
                    
                    # Przyciski akcji
                    b1, b2, b3 = st.columns(3)
                    
                    with b1:
                        if st.button("✅ Akceptuj cenę", key=f"acc_{neg_id}", use_container_width=True):
                            success, msg = negotiation_service.accept_proposal(neg_id, "Zaakceptowane")
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                                
                    with b2:
                        if st.button("💬 Kontrpropozycja", key=f"cnt_{neg_id}", use_container_width=True):
                            st.session_state[f"mode_{neg_id}"] = "counter"
                            st.rerun()
                            
                    with b3:
                        if st.button("❌ Odrzuć", key=f"rej_{neg_id}", use_container_width=True):
                            st.session_state[f"mode_{neg_id}"] = "reject"
                            st.rerun()

                    # Obsługa trybów (Formularze pod kartą)
                    if st.session_state.get(f"mode_{neg_id}") == "counter":
                        st.markdown("#### ✍️ Formularz kontrpropozycji")
                        new_price = st.number_input("Twoja cena (PLN)", value=float(neg['proposed_price']*0.9), key=f"np_{neg_id}")
                        new_notes = st.text_area("Dlaczego taka cena?", key=f"nn_{neg_id}", placeholder="Napisz uzasadnienie dla Karola...")
                        
                        fb1, fb2 = st.columns(2)
                        with fb1:
                            if st.button("Wyślij do Karola", key=f"send_{neg_id}", type="primary"):
                                success, msg = negotiation_service.counter_offer(neg_id, new_price, neg['proposed_duration_days'], new_notes)
                                if success:
                                    st.success("Wysłano!")
                                    st.session_state[f"mode_{neg_id}"] = None
                                    st.rerun()
                        with fb2:
                            if st.button("Anuluj", key=f"can_{neg_id}"):
                                st.session_state[f"mode_{neg_id}"] = None
                                st.rerun()

                    if st.session_state.get(f"mode_{neg_id}") == "reject":
                        st.error("Czy na pewno chcesz odrzucić tę wycenę?")
                        rej_reason = st.text_area("Powód odrzucenia", key=f"rr_{neg_id}")
                        if st.button("Potwierdzam Odrzucenie", key=f"crej_{neg_id}", type="primary"):
                            success, msg = negotiation_service.reject_proposal(neg_id, rej_reason)
                            if success:
                                st.session_state[f"mode_{neg_id}"] = None
                                st.rerun()

    # ============================================================================
    # POZOSTAŁE TABY (BEZ ZMIAN W LOGICE, TYLKO UI)
    # ============================================================================
    
    with tab_changes:
        st.subheader("⚡ Zatwierdzanie Zmian")
        pending_changes = change_service.get_pending_changes(selected_project_id)
        if not pending_changes:
            st.success("Brak oczekujących zmian w planie.")
        else:
            for change in pending_changes:
                st.warning(f"Zgłoszenie zmiany: {change['reason']}")
                if st.button(f"Zatwierdź zmianę {change['id'][:4]}"):
                    change_service.approve_change(change['id'], "Ok")
                    st.rerun()

    with tab_timeline:
        st.subheader("📅 Harmonogram Projektu")
        timeline = phase_service.get_project_timeline(selected_project_id)
        if timeline.get('timeline'):
            for t in timeline['timeline']:
                st.write(f"**{t['phase_name']}** ({t['status']})")
                st.progress(t['progress_percent'] / 100)
    
    with tab_budget:
        st.subheader("📊 Szczegółowa Analiza Wydatków")
        st.write(f"### Całkowity budżet: {total_budget:,.0f} PLN")
        st.write(f"### Aktualne wydatki: {total_spent:,.0f} PLN")
        st.progress(spent_pct / 100)

if __name__ == "__main__":
    st.error("Ten plik powinien być importowany z app.py")
