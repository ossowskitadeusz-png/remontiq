# pages/crew_panel.py
# =====================================================
# PANEL EKIPY (KAROL) - HANDSHAKE 2.0 PREMIUM UI (FIXED)
# =====================================================

import streamlit as st
import pandas as pd
from datetime import datetime
from services.negotiation_service import NegotiationService
from services.phase_service import PhaseService
from components.chat_component import send_system_chat_alert
from supabase import create_client

def render_crew_panel(supabase=None, phase_service=None, negotiation_service=None, change_service=None, task_service=None, ordering_service=None):
    """
    Premium Panel Ekipy - Zarządzanie pracami, wycenami i negocjacjami.
    """
    
    st.markdown("---")
    
    # Inicjalizacja serwisów
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
    if not task_service:
        from services.task_service import TaskService
        task_service = TaskService(supabase)
    if not ordering_service:
        from services.ordering_service import OrderingService
        ordering_service = OrderingService(supabase, task_service)
    
    # 1. AUTORYZOWANY PROJEKT
    selected_project_id = st.session_state.get("crew_authorized_project_id")
    if not selected_project_id:
        st.error("Brak przypisanego remontu. Zaloguj się poprawnym kodem.")
        return
        
    projects_res = supabase.table("project_metadata").select("id, project_name, crew_lead_name").eq("id", selected_project_id).execute()
    projects = projects_res.data or []
    if not projects:
        st.warning("Projekt, do którego próbujesz się dostać, nie istnieje.")
        return
    
    selected_project_data = projects[0]
    crew_boss_name = selected_project_data.get("crew_lead_name") or "Ekipy"
    selected_project_name = selected_project_data["project_name"]
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.header(f"👷 Panel Ekipy ({crew_boss_name})")
    with col_refresh:
        if st.button("🔄 Odśwież Dane", use_container_width=True):
            st.rerun()
    
    st.markdown("---")
    
    # 2. DASHBOARD - METRYKI
    all_negs = negotiation_service.get_all_negotiations_for_project(selected_project_id)
    approved_negs = [n for n in all_negs if n['status'] == 'accepted']
    pending_crew = negotiation_service.get_pending_for_crew(selected_project_id)
    
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
    
    # ALERT KONTROFERT - Najważniejsza powiadomienie
    if pending_crew:
        st.error(f"🚨 **UWAGA! Masz {len(pending_crew)} nową(e) kontrofertę(y) od Inwestora!** Zajrzyj do zakładki 'Kontrpropozycje', aby podjąć decyzję.", icon="🚨")
        
    with st.expander("⚡ Szybkie akcje", expanded=False):
        with st.form("quick_action_msg_form", clear_on_submit=True):
            quick_msg = st.text_area("💬 Napisz do inwestora", placeholder="Wpisz treść wiadomości...", height=80)
            if st.form_submit_button("Wyślij wiadomość", type="primary"):
                if not quick_msg.strip():
                    st.warning("Wiadomość nie może być pusta.")
                else:
                    msg_with_prefix = f"👷 Wiadomość od ekipy: {quick_msg.strip()}"
                    success = send_system_chat_alert(supabase, selected_project_id, msg_with_prefix)
                    if success:
                        st.success("Wiadomość została wysłana do Inwestora!")
                    else:
                        st.error("Nie udało się wysłać wiadomości (brak zadań w projekcie lub błąd bazy).")

    # 3. TABY
    counter_tab_title = f"💬 Kontrpropozycje 🔴 ({len(pending_crew)})" if pending_crew else "💬 Kontrpropozycje"
    
    tab_planning, tab_quotes, tab_counter, tab_accepted = st.tabs([
        "📋 Plan Remontu",
        "📤 Wysłane Propozycje", 
        counter_tab_title, 
        "✅ Moje Umowy"
    ])
    
    with tab_planning:
        render_crew_planning_module(task_service, ordering_service, selected_project_id, phase_service)
        
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

# Metoda render_new_proposal_form została skonsolidowana z tab_planning.

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

def render_crew_planning_module(task_service, ordering_service, project_id, phase_service):
    """
    Panel planowania Karola z możliwością zmiany kolejności zadań.
    """
    supabase = task_service.supabase
    
    # Formularz dodawania nowego Pomieszczenia
    with st.expander("🏠 Dodaj Pomieszczenie do swojego Planu"):
        with st.form("form_add_room", clear_on_submit=True):
            try:
                available_rooms_req = supabase.table("rooms").select("*").eq("project_id", project_id).execute()
                available_rooms = available_rooms_req.data or []
            except:
                available_rooms = []
            
            try:
                existing_phases = phase_service.get_phases(project_id)
                existing_names = {ph.get("phase_name") for ph in existing_phases}
            except:
                existing_names = set()
            
            filtered_rooms = [r for r in available_rooms if r.get("name") not in existing_names]
            
            if not available_rooms:
                st.warning("Inwestor nie zdefiniował jeszcze żadnych pomieszczeń.")
                st.form_submit_button("Dodaj", disabled=True)
            elif not filtered_rooms:
                st.info("Wszystkie zdefiniowane przez Inwestora pomieszczenia zostały już dodane do Twojego planu.")
                st.form_submit_button("Dodaj", disabled=True)
            else:
                room_names = [r.get("name", "Nieznane") for r in filtered_rooms]
                p_name = st.selectbox("Wybierz pomieszczenie z listy Inwestora *", options=room_names)

                col_date, col_days = st.columns(2)
                from datetime import date as _date, timedelta as _timedelta
                p_start = col_date.date_input("📅 Kiedy zaczynasz?", value=_date.today())
                p_days = col_days.number_input("⏱️ Ile dni potrzebujesz?", min_value=1, max_value=365, value=7, step=1)
                p_end = p_start + _timedelta(days=p_days)
                st.caption(f"→ Planowany koniec: **{p_end.strftime('%d.%m.%Y')}**")

                if st.form_submit_button("✅ Dodaj do Planu", type="primary"):
                    if p_name in existing_names:
                        st.error(f"Pomieszczenie '{p_name}' jest już w Twoim planie!")
                    else:
                        res = phase_service.create_phase(
                            project_id,
                            p_name,
                            planned_start_date=p_start.isoformat(),
                            planned_end_date=p_end.isoformat()
                        )
                        if res.get("success"):
                            st.success(f"Pomieszczenie '{p_name}' dodane!")
                            st.rerun()
                        else:
                            st.error(f"Błąd: {res.get('error')}")
    
    st.markdown("---")
    
    phases = phase_service.get_phases(project_id)
    if not phases:
        st.info("Brak pomieszczeń w planie.")
        return
        
    for p in phases:
        phase_id = p['id']
        with st.container(border=True):
            # Pobierz posortowane zadania przez OrderingService
            ordered_tasks = ordering_service.get_ordered_tasks(phase_id)
            
            # Sprawdzamy ryczałt
            is_lump_sum_room = any("[LUMP_SUM_ROOM]" in (t.get('description') or '') for t in ordered_tasks)
            
            # Sprawdzamy czy pokój ma wycenione zadania pojedyncze
            has_individual_prices = any((float(t.get('final_price') or t.get('final_approved_price') or 0) > 0 or t.get('commercial_status') in ['pending', 'approved']) and "[LUMP_SUM_ROOM]" not in (t.get('description') or '') for t in ordered_tasks)
            
            # Oblicz sumę wycenioną dla tego pokoju
            room_approved_total = sum(float(t.get('final_price') or 0) for t in ordered_tasks if t.get('commercial_status') == 'approved')
            room_pending_total = sum(float(t.get('final_price') or 0) for t in ordered_tasks if t.get('commercial_status') == 'pending')
            
            col_room, col_del = st.columns([5, 1])
            with col_room:
                title_suffix = " 🔒 `RYCZAŁT`" if is_lump_sum_room else ""
                st.markdown(f"### 📦 {p['phase_name']}{title_suffix}")
                
                if is_lump_sum_room:
                    lump_sum_amount = sum(float(t.get('final_price') or 0) for t in ordered_tasks if "[LUMP_SUM_ROOM]" in (t.get('description') or ''))
                    extras_amount = sum(float(t.get('final_price') or 0) for t in ordered_tasks if "[LUMP_SUM_ROOM]" not in (t.get('description') or ''))
                    st.markdown(f"💰 **Ryczałt:** `{lump_sum_amount:,.0f} zł` | **Dodatkowe:** `{extras_amount:,.0f} zł` | **Razem:** `{lump_sum_amount + extras_amount:,.0f} zł`")
                else:
                    price_line = f"💰 **Zatwierdzone:** `{room_approved_total:,.0f} zł`"
                    if room_pending_total > 0:
                        price_line += f" | ⏳ *W negocjacjach:* `{room_pending_total:,.0f} zł`"
                    st.markdown(price_line)
                
                # --- OSTRZEŻENIE O PRZECIĄGANIU ---
                try:
                    from services.timeline_service import TimelineService
                    tl_service = TimelineService(supabase)
                    warning = tl_service.get_phase_delay_warning(phase_id)
                    if warning.get("has_warning"):
                        planned_end = warning.get("planned_end", "?")
                        delay_days = warning.get("delay_days", 0)
                        culprits = warning.get("culprit_tasks", [])
                        culprit_str = ", ".join(f'"{t}"' for t in culprits) if culprits else "ostatnio dodane"
                        st.warning(
                            f"⚠️ **Uwaga na plan!** Zgłosiłeś datę: {planned_end}, ale Twoje zadania "
                            f"przeciągają ten pokój o **{delay_days} dni**. "
                            f"Sprawdź: {culprit_str}. Przemyśl plan!"
                        )
                except Exception as _e:
                    pass
                
                # Jeśli to nie ryczałt, dajemy opcję wyceny ryczałtowej
                if not is_lump_sum_room:
                    if has_individual_prices:
                        st.info("Ten pokój ma już wycenione pojedyncze zadania. Aby uniknąć podwójnego naliczania, nie można dodać ryczałtu.")
                    else:
                        with st.popover("📦 Wyceń jako Ryczałt za całość"):
                            st.markdown(f"#### 💰 Propozycja Ryczałtu: **{p['phase_name']}**")
                            st.caption("Wycena ryczałtowa za całe pomieszczenie. Inne prace w tym pokoju będą mogły mieć cenę 0.00 zł.")
                        with st.form(key=f"form_lump_sum_{phase_id}", clear_on_submit=True):
                            lump_price = st.number_input("Cena ryczałtu (zł)", min_value=0.0, step=500.0, value=5000.0)
                            lump_duration = st.number_input("Czas realizacji (dni)", min_value=1, step=1, value=7)
                            lump_notes = st.text_area("Notatki dla Inwestora (opcjonalnie)")
                            
                            if st.form_submit_button("📤 Wyślij Wycenę Ryczałtową", use_container_width=True):
                                try:
                                    lump_task = task_service.create_task(
                                        project_id=project_id,
                                        phase_id=phase_id,
                                        name=f"Ryczałt - {p['phase_name']}",
                                        description="[LUMP_SUM_ROOM]",
                                        estimated_duration_days=int(lump_duration)
                                    )
                                    if lump_task:
                                        neg_service = st.session_state.negotiation_service
                                        success, msg, _ = neg_service.propose_price(
                                            task_id=lump_task['id'],
                                            proposed_by='crew',
                                            price=lump_price,
                                            duration_days=int(lump_duration),
                                            notes=lump_notes
                                        )
                                        if success:
                                            st.success("✅ Propozycja ryczałtu wysłana!")
                                            try:
                                                from components.chat_component import send_system_chat_alert
                                                alert_msg = f"🚨 RYCZAŁT — Pomieszczenie '{p['phase_name']}': Szef Ekipy zaproponował ryczałt za całość w wysokości {lump_price:,.0f} zł (szacowany czas: {lump_duration} dni)."
                                                send_system_chat_alert(supabase, project_id, alert_msg)
                                            except:
                                                pass
                                            st.rerun()
                                        else:
                                            st.error(msg)
                                    else:
                                        st.error("Nie udało się utworzyć zadania ryczałtowego.")
                                except Exception as e:
                                    st.error(f"Błąd: {e}")
            
            with col_del:
                if not ordered_tasks:
                    if st.button("🗑️", key=f"del_room_{phase_id}", help="Usuń puste pomieszczenie"):
                        phase_service.delete_phase(phase_id)
                        st.rerun()

            def draw_task_row(task, idx, all_tasks):
                col_num, col_info, col_move, col_edit, col_del, col_price = st.columns([0.5, 2.5, 1, 0.7, 0.7, 1.5])
                
                with col_num:
                    st.markdown(f"<div style='padding-top:10px; opacity:0.5;'>#{idx+1}</div>", unsafe_allow_html=True)
                
                with col_info:
                    st.write(f"**{task['name']}**")
                    status = task['status']
                    if "[INCLUDED_IN_LUMP_SUM]" in (task.get('description') or ''):
                        st.caption("📦 *Wliczone w ryczałt*")
                    elif float(task.get('final_price') or 0) > 0 and "[LUMP_SUM_ROOM]" not in (task.get('description') or ''):
                        st.caption("🛠️ *Robota dodatkowa*")
                        
                    if status == 'READY':
                        st.caption("🟢 **Gotowe do realizacji**")
                    elif status == 'PENDING':
                        st.caption("⚪ **Szkic / Do wyceny**")
                    elif status == 'BLOCKED':
                        st.caption("⏸️ **Czeka na poprzednie zadanie**")
                
                with col_move:
                    m1, m2 = st.columns(2)
                    with m1:
                        if st.button("⬆️", key=f"up_{task['id']}", disabled=(idx==0), help="Przesuń wyżej"):
                            if ordering_service.move_task_up(task['id']): st.rerun()
                            else: st.error("Nie udało się.")
                    with m2:
                        if st.button("⬇️", key=f"down_{task['id']}", disabled=(idx==len(all_tasks)-1), help="Przesuń niżej"):
                            if ordering_service.move_task_down(task['id']): st.rerun()
                            else: st.error("Nie udało się.")

                # Zabezpieczenie przed edycją zablokowanych (chyba że wliczone w ryczałt - też uznajemy za zablokowane cenowo)
                is_locked = bool(task.get('final_price')) or task['status'] != 'PENDING' or "[INCLUDED_IN_LUMP_SUM]" in (task.get('description') or '')

                with col_edit:
                    if is_locked and task['status'] != 'PENDING' and "[INCLUDED_IN_LUMP_SUM]" not in (task.get('description') or ''):
                        st.button("✏️", key=f"edit_lock_{task['id']}", disabled=True)
                    else:
                        with st.popover("✏️"):
                            st.caption("Popraw nazwę zadania")
                            new_name = st.text_input("Nowa nazwa", value=task['name'], key=f"inp_{task['id']}")
                            if st.button("Zapisz", key=f"save_{task['id']}", type="primary"):
                                if new_name and new_name != task['name']:
                                    task_service.update_task(task['id'], {"name": new_name})
                                    st.rerun()

                with col_del:
                    if is_locked and task['status'] != 'PENDING' and "[INCLUDED_IN_LUMP_SUM]" not in (task.get('description') or ''):
                        st.button("🗑️", key=f"del_lock_{task['id']}", disabled=True)
                    else:
                        if st.button("🗑️", key=f"deltask_{task['id']}", help="Usuń to zadanie"):
                            task_service.delete_task(task['id'])
                            st.rerun()
                
                with col_price:
                    if "[INCLUDED_IN_LUMP_SUM]" in (task.get('description') or ''):
                        st.markdown(f"<div style='text-align:right; opacity:0.8;'>0 zł (Ryczałt)</div>", unsafe_allow_html=True)
                    elif task['final_price']:
                        st.markdown(f"<div style='text-align:right; color:#10b981; font-weight:700;'>{task['final_price']:,.0f} zł</div>", unsafe_allow_html=True)
                    elif task['status'] == 'PENDING':
                        with st.popover("💰 Wycena"):
                            st.caption("Wyślij wycenę do Inwestora")
                            price_val = st.number_input("Cena (PLN)", min_value=0.0, step=100.0, key=f"price_{task['id']}")
                            days_val = st.number_input("Czas robocizny (dni)", min_value=1, step=1, value=1, key=f"days_{task['id']}")
                            if st.button("Wyślij", type="primary", key=f"send_{task['id']}"):
                                neg_service = st.session_state.negotiation_service
                                success, msg, _ = neg_service.propose_price(
                                    task_id=task['id'],
                                    proposed_by='crew',
                                    price=price_val,
                                    duration_days=days_val
                                )
                                if success:
                                    st.success(msg)
                                    import time
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(msg)
                    else:
                        st.markdown(f"<div style='text-align:right; opacity:0.5;'>brak ceny</div>", unsafe_allow_html=True)

            if ordered_tasks:
                if is_lump_sum_room:
                    # Podział na sekcje dla pokoju ryczałtowego
                    ryczalt_i_wliczone = [t for t in ordered_tasks if "[LUMP_SUM_ROOM]" in (t.get('description') or '') or float(t.get('final_price') or t.get('final_approved_price') or 0) == 0 or "[INCLUDED_IN_LUMP_SUM]" in (t.get('description') or '')]
                    dodatkowe = [t for t in ordered_tasks if t not in ryczalt_i_wliczone]
                    
                    if ryczalt_i_wliczone:
                        st.markdown("##### 📦 Prace wliczone w ryczałt")
                        for idx, task in enumerate(ryczalt_i_wliczone):
                            draw_task_row(task, idx, ryczalt_i_wliczone)
                    
                    if dodatkowe:
                        st.markdown("##### 🛠️ Roboty dodatkowe płatne")
                        for idx, task in enumerate(dodatkowe):
                            draw_task_row(task, idx, dodatkowe)
                else:
                    for idx, task in enumerate(ordered_tasks):
                        draw_task_row(task, idx, ordered_tasks)
            else:
                st.caption("Brak zadań. Dodaj pierwsze zadanie w tym pokoju.")

            # Przycisk dodania nowego zadania
            st.divider()
            with st.expander("➕ Dodaj zadanie do tego pokoju"):
                if is_lump_sum_room:
                    st.caption("Ten pokój jest rozliczany ryczałtem. Prace wliczone mają koszt 0 zł, a roboty dodatkowe są doliczane osobno.")
                    task_type = st.radio("Typ pracy", ["Wliczona w ryczałt", "Robota dodatkowa płatna"], key=f"ttype_{phase_id}")
                    
                    if task_type == "Robota dodatkowa płatna":
                        extra_price = st.number_input("Cena za robotę dodatkową (zł)", min_value=1.0, value=100.0, step=10.0, key=f"tprice_{phase_id}")
                    else:
                        extra_price = 0.0

                    new_t_name = st.text_input("Nazwa zadania", key=f"tname_{phase_id}")
                    new_t_dur = st.number_input("Szacowane dni", min_value=1, value=1, key=f"tdur_{phase_id}")
                    
                    if st.button("Dodaj zadanie", key=f"btn_add_{phase_id}", use_container_width=True):
                        if new_t_name:
                            new_task = task_service.create_task(
                                project_id=project_id,
                                phase_id=phase_id,
                                name=new_t_name,
                                estimated_duration_days=int(new_t_dur)
                            )
                            if new_task:
                                if task_type == "Wliczona w ryczałt":
                                    task_service.update_task(new_task['id'], {
                                        "final_approved_price": 0,
                                        "commercial_status": "approved",
                                        "description": (new_task.get("description") or "") + "\n[INCLUDED_IN_LUMP_SUM]"
                                    })
                                else:
                                    neg_service = st.session_state.negotiation_service
                                    neg_service.propose_price(
                                        task_id=new_task['id'],
                                        proposed_by='crew',
                                        price=extra_price,
                                        duration_days=int(new_t_dur)
                                    )
                            st.rerun()
                else:
                    with st.form(key=f"fast_add_task_{phase_id}"):
                        new_t_name = st.text_input("Nazwa zadania")
                        new_t_dur = st.number_input("Szacowane dni", min_value=1, value=1)
                        if st.form_submit_button("Dodaj zadanie", use_container_width=True):
                            if new_t_name:
                                task_service.create_task(
                                    project_id=project_id,
                                    phase_id=phase_id,
                                    name=new_t_name,
                                    estimated_duration_days=int(new_t_dur)
                                )
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
