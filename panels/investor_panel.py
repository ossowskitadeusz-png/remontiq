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

def render_investor_panel(supabase=None, phase_service=None, negotiation_service=None, change_service=None, task_service=None, timeline_service=None, ordering_service=None):
    """
    Premium Panel Inwestora - Zarządzanie negocjacjami, zmianami, timeline'em.
    """
    
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.header("💎 Panel Inwestora (Ty)")
    with col_refresh:
        if st.button("🔄 Odśwież Dane", use_container_width=True):
            st.rerun()
            
    st.markdown("---")
    
    if not supabase:
        try:
            from services.supabase_client import get_supabase_client
            supabase = get_supabase_client()
        except Exception as e:
            st.error("Błąd połączenia z Supabase.")
            st.code(f"{type(e).__name__}: {str(e)}")
            st.stop()
    if not negotiation_service:
        negotiation_service = NegotiationService(supabase)
    if not phase_service:
        phase_service = PhaseService()
    if not change_service:
        change_service = ChangeService()
    if not task_service:
        from services.task_service import TaskService
        task_service = TaskService(supabase)
    if not timeline_service:
        from services.timeline_service import TimelineService
        timeline_service = TimelineService(supabase, task_service, negotiation_service)
    if not ordering_service:
        from services.ordering_service import OrderingService
        ordering_service = OrderingService(supabase, task_service)
    
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
    crew_name = project_data.get("crew_lead_name") or "Ekipa"
    
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
    awaiting_tasks_res = supabase.table("tasks").select("id, name, phase_name, planned_end_date").eq("project_id", selected_project_id).eq("kanban_status", "AWAITING_INSPECTION").execute()
    awaiting_tasks = awaiting_tasks_res.data or []
    
    tab_title_inspections = f"🔍 Odbiory Prac ({len(awaiting_tasks)})" if awaiting_tasks else "🔍 Odbiory Prac"
    
    tab_negotiations, tab_changes, tab_budget, tab_timeline, tab_rooms, tab_inspections = st.tabs([
        "💰 Negocjacje Cen", 
        "📝 Wnioski o Zmiany", 
        "📊 Analiza Budżetu",
        "🕒 Oś Czasu Projektu",
        "🏠 Pomieszczenia do remontu",
        tab_title_inspections
    ])
    
    with tab_negotiations:
        st.subheader("💰 Negocjacje Cen - Handshake")
        if not pending_negs:
            st.info("✅ Nie masz żadnych propozycji do rozpatrzenia.")
        else:
            for idx, neg in enumerate(pending_negs):
                render_negotiation_card(neg, negotiation_service, crew_name=crew_name, key_suffix=f"investor_{idx}")
                
        st.markdown("---")
        st.subheader("✅ Zatwierdzone Negocjacje")
        approved_negs = [n for n in all_negs if n['status'] == 'accepted']
        
        if approved_negs:
            approved_df = pd.DataFrame([
                {
                    'Zadanie': n.get('tasks', {}).get('name', 'N/A'),
                    'Finalna Cena': f"{n.get('response_price') or n['proposed_price']:,.0f} zł",
                    'Data Zatwierdzenia': n['responded_at'][:10] if n.get('responded_at') else n['created_at'][:10]
                }
                for n in approved_negs
            ])
            st.dataframe(approved_df, use_container_width=True)
        else:
            st.info("Brak zatwierdzonych umów")
    
    with tab_changes:
        st.subheader("📝 Wnioski o Zmiany")
        changes = change_service.get_pending_changes(selected_project_id)
        if not changes:
            st.info("Brak wniosków o zmianę")
        else:
            for change in changes:
                render_change_card(change, change_service)

    with tab_budget:
        st.subheader("📊 Analiza Budżetu i Kosztów")
        
        # 1. Podsumowanie ogólne w ładnych kartach/metrykach
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Budżet Całkowity", f"{total_budget:,.0f} zł")
        c2.metric("💸 Wydano (Zatwierdzone)", f"{spent:,.0f} zł", delta=f"{spent/total_budget*100:.1f}% budżetu" if total_budget > 0 else None)
        
        # Obliczenie sumy wszystkich zatwierdzonych i oczekujących zadań
        try:
            all_project_tasks = task_service.get_tasks_by_project(selected_project_id)
        except:
            all_project_tasks = []
            
        total_approved = sum(float(t.get('final_approved_price') or 0) for t in all_project_tasks if t.get('commercial_status') == 'approved')
        
        c3.metric("📊 Pozostało w Budżecie", f"{max(0, total_budget - total_approved):,.0f} zł")
        
        if total_budget > 0:
            st.progress(min(total_approved / total_budget, 1.0))
            
        st.markdown("---")
        st.markdown("### 🏠 Szczegółowy Kosztorys Pomieszczeń (Rozbicie Prac)")
        
        try:
            phases = phase_service.get_phases(selected_project_id)
        except:
            phases = []
            
        if not phases:
            st.info("Brak zdefiniowanych pomieszczeń w projekcie.")
        else:
            for p in phases:
                phase_id = p['id']
                room_tasks = [t for t in all_project_tasks if t.get('phase_id') == phase_id]
                
                # Obliczanie sum dla tego pokoju
                room_approved = sum(float(t.get('final_approved_price') or 0) for t in room_tasks if t.get('commercial_status') == 'approved')
                
                # Nagłówek pomieszczenia w formie karty ze spisem kosztów
                with st.container(border=True):
                    # Sprawdzamy czy w tym pomieszczeniu jest ryczałt
                    has_lump_sum = any("[LUMP_SUM_ROOM]" in (t.get('description') or '') for t in room_tasks)
                    lump_sum_suffix = " 🔒 `RYCZAŁT`" if has_lump_sum else ""
                    
                    st.markdown(f"#### 📦 {p['phase_name']}{lump_sum_suffix}")
                    st.markdown(f"**Suma zatwierdzonych prac:** `<span style='color:#10b981; font-weight:bold; font-size:16px;'>{room_approved:,.0f} zł</span>`", unsafe_allow_html=True)
                    
                    if room_tasks:
                        # Przygotowanie tabeli/listy zadań
                        task_data = []
                        for t in room_tasks:
                            price_val = t.get('final_approved_price')
                            
                            # Status handshaku
                            status_db = t.get('commercial_status') or 'pending'
                            if status_db == 'approved':
                                status_desc = "✅ Zaakceptowane"
                                price_str = f"{price_val:,.0f} zł"
                            else:
                                status_desc = "⏳ Wycena/Negocjacje"
                                price_str = "W ustaleniach"
                                
                            task_data.append({
                                "Zadanie / Robota": t['name'],
                                "Status Wyceny": status_desc,
                                "Koszt (PLN)": price_str
                            })
                            
                        # Konwertujemy na DataFrame, aby wyświetlić piękną tabelę
                        df_tasks = pd.DataFrame(task_data)
                        st.table(df_tasks)
                    else:
                        st.caption("Brak zaplanowanych zadań w tym pomieszczeniu.")

    with tab_timeline:
        from components.timeline_widget import render_timeline_widget
        st.subheader("🕒 Oś Czasu Projektu")
        render_timeline_widget(timeline_service, selected_project_id)

    with tab_rooms:
        st.subheader("🏠 Podziel mieszkanie na poszczólne pomieszczenia")
        st.write(f"Wpisz tu pokoje, z których {crew_name} będzie mógł budować swój harmonogram.")

        # Dodawanie nowego pomieszczenia
        with st.form("add_room_form_center", clear_on_submit=True):
            col1, col2 = st.columns([3, 1])
            new_room_name = col1.text_input("Nazwa pomieszczenia (np. Sypialnia, Łazienka)")
            if col2.form_submit_button("➕ Dodaj do remontu", use_container_width=True):
                if new_room_name:
                    try:
                        supabase.table("rooms").insert({"name": new_room_name, "project_id": selected_project_id}).execute()
                        st.success(f"Dodano: {new_room_name}")
                        st.rerun()
                    except Exception as e:
                        if "23505" in str(e) or "duplicate" in str(e).lower():
                            st.warning(f"⚠️ Pokój '{new_room_name}' już istnieje!")
                        else:
                            st.error(f"Błąd: {e}")
                else:
                    st.error("Podaj nazwę pokoju.")

        # Edycja istniejących
        st.write("### Edycja istniejących pomieszczeń")
        rooms_data_c = supabase.table("rooms").select("*").eq("project_id", selected_project_id).execute().data
        old_names_c = {r['id']: r['name'] for r in rooms_data_c} if rooms_data_c else {}
        df_r_c = pd.DataFrame(rooms_data_c) if rooms_data_c else pd.DataFrame()

        if not df_r_c.empty:
            edited_r_c = st.data_editor(df_r_c[['id', 'name']], disabled=["id"], hide_index=True, width="stretch", key="rooms_editor_center")
            if st.button("💾 Zapisz zmiany w nazwach", type="primary", key="save_rooms_center"):
                updated = 0
                for _, row in edited_r_c.iterrows():
                    rid, new_name, old_name = row['id'], row['name'], old_names_c.get(row['id'], '')
                    supabase.table("rooms").update({"name": new_name}).eq("id", rid).execute()
                    if old_name and old_name != new_name:
                        supabase.table("project_phases")\
                            .update({"phase_name": new_name})\
                            .eq("project_id", selected_project_id)\
                            .eq("phase_name", old_name).execute()
                        updated += 1
                st.success(f"✅ Zapisano! Zaktualizowano {updated} pomieszczeń również w planie ekipy ({crew_name}).")
                st.rerun()
        else:
            st.info("📦 Brak pokójów. Dodaj pierwsze pomieszczenie powyżej.")

    with tab_inspections:
        st.subheader("🔍 Odbiory Prac")
        st.write("Tu pojawiają się zadania, które Ekipa zgłosiła jako **Zakończone** i czekają na Twój odbiór.")
        
        if not awaiting_tasks:
            st.success("✅ Brak zadań oczekujących na odbiór.")
        else:
            for t in awaiting_tasks:
                with st.container(border=True):
                    col_info, col_action = st.columns([3, 1])
                    with col_info:
                        st.markdown(f"### {t['name']}")
                        st.caption(f"Pokój: **{t.get('phase_name', 'Brak')}**")
                        
                        planned_end = t.get('planned_end_date')
                        if planned_end:
                            end_date_obj = datetime.strptime(planned_end, "%Y-%m-%d").date()
                            today = datetime.now().date()
                            if today > end_date_obj:
                                st.error(f"⚠️ Planowo miało się skończyć: {planned_end} (Opóźnienie: {(today - end_date_obj).days} dni)")
                            else:
                                st.info(f"📅 Planowano do: {planned_end} (W terminie)")
                        
                    with col_action:
                        if st.button("✅ ZATWIERDŹ ODBIÓR", key=f"insp_{t['id']}", type="primary", use_container_width=True):
                            # Zmieniamy status zadania na zarchiwizowane/finalnie odebrane
                            task_service.update_task(t['id'], {"kanban_status": "DONE", "completion_status": "Zatwierdzone", "actual_end_date": datetime.now().date().isoformat()})
                            st.success("Odebrano pomyślnie!")
                            st.rerun()

# =====================================================
# KOMPONENTY
# =====================================================

def render_negotiation_card(neg, negotiation_service, crew_name="Ekipa", key_suffix=""):
    neg_id = neg['id']
    task_name = neg.get('tasks', {}).get('name', 'Nieznane zadanie')
    
    with st.container(border=True):
        st.markdown(f"### 🔨 {task_name}")
        task_desc = neg.get('tasks', {}).get('description')
        if task_desc:
            st.caption(f"**Opis techniczny:** {task_desc}")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(f"OFERTA ({crew_name.upper()})", f"{neg['proposed_price']:,.0f} zł")
        with col2:
            if neg.get('response_price'):
                st.warning(f"TWOJA KONTRA: {neg['response_price']:,.0f} zł")
        with col3:
            st.metric("Czas realizacji", f"{neg.get('proposed_duration_days', '?')} dni")
            
        if neg.get('proposed_notes'):
            st.info(f"👷 **Wiadomość ({crew_name}):** {neg['proposed_notes']}")

        st.markdown("---")
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
