import streamlit as st
import html
from datetime import datetime, date

def get_room_emoji(phase_name):
    name = (phase_name or "").lower()
    if "sypialnia" in name:
        return "🛏️"
    elif "łazienka" in name or "lazienka" in name:
        return "🚿"
    elif "kuchnia" in name:
        return "🍳"
    elif "salon" in name:
        return "🛋️"
    elif "korytarz" in name or "przedpokój" in name or "przedpokoj" in name:
        return "🚪"
    elif "ogólne" in name or "ogolne" in name:
        return "🧰"
    return "🏠"

def render_project_progress_dashboard(
    supabase,
    project_id,
    phase_service,
    is_task_completed_for_progress,
    get_project_days_info,
    viewer_role="investor"
):
    """
    Renderuje w pełni responsywny i premium wizualny dashboard 'Plan & Postęp'.
    Działa read-only i jest współdzielony przez Inwestora oraz Ekipę.
    """
    # 1. POBRANIE DANYCH
    tasks = []
    try:
        tasks_req = supabase.table("tasks").select("*").eq("project_id", project_id).execute()
        tasks = tasks_req.data or []
    except Exception as e:
        st.error(f"Błąd pobierania zadań: {e}")
        return

    phases = []
    try:
        phases = phase_service.get_phases(project_id) or []
    except Exception as e:
        st.error(f"Błąd pobierania faz/pomieszczeń: {e}")
        return

    # Jeśli brak zdefiniowanych pokoi/faz
    if not phases:
        st.info("📭 Brak zdefiniowanych pomieszczeń w tym projekcie.")
        return

    # 2. WYLICZENIE METRYK KPI
    # KPI A: Postęp prac (zadania)
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if is_task_completed_for_progress(t))
    task_progress_pct = round(completed_tasks / total_tasks * 100, 1) if total_tasks > 0 else 0.0

    # KPI B: Postęp pomieszczeń (średnia z postępów faz)
    phase_progresses = []
    for ph in phases:
        ph_tasks = [t for t in tasks if t.get("phase_id") == ph.get("id")]
        ph_done = sum(1 for t in ph_tasks if is_task_completed_for_progress(t))
        ph_total = len(ph_tasks)
        ph_pct = (ph_done / ph_total * 100) if ph_total > 0 else 0.0
        phase_progresses.append(ph_pct)
    
    phase_progress_avg = round(sum(phase_progresses) / len(phase_progresses), 1) if phase_progresses else 0.0

    # KPI C: Upływ czasu
    days_info = None
    if get_project_days_info:
        try:
            days_info = get_project_days_info()
        except:
            pass

    # 3. RENDEROWANIE STYLÓW CSS
    st.markdown("""
    <style>
    .kpi-container {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        margin-bottom: 28px;
    }
    .kpi-card {
        flex: 1 1 220px;
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 16px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    .kpi-title {
        font-size: 12px;
        color: #94a3b8;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 8px;
    }
    .kpi-value {
        font-size: 32px;
        font-weight: 800;
        margin-bottom: 4px;
    }
    .kpi-sub {
        font-size: 12px;
        color: #64748b;
        font-weight: 500;
    }
    .room-card {
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(148, 163, 184, 0.12);
        border-radius: 20px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
    }
    .room-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
    }
    .room-title {
        font-size: 18px;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .room-stats {
        font-size: 13px;
        font-weight: 700;
        color: #94a3b8;
    }
    .progress-container {
        background: rgba(148, 163, 184, 0.08);
        height: 8px;
        border-radius: 4px;
        overflow: hidden;
        margin-bottom: 20px;
    }
    .progress-bar {
        height: 100%;
        background: linear-gradient(90deg, #3b82f6 0%, #10b981 100%);
        border-radius: 4px;
    }
    .task-list {
        display: flex;
        flex-direction: column;
        gap: 10px;
    }
    .task-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 16px;
        background: rgba(255, 255, 255, 0.01);
        border: 1px solid rgba(148, 163, 184, 0.06);
        border-radius: 12px;
    }
    .task-left {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .task-name {
        font-size: 14px;
        font-weight: 600;
    }
    .task-price {
        font-size: 13px;
        font-weight: 700;
        color: #94a3b8;
    }
    .badge {
        display: inline-block;
        padding: 3px 9px;
        border-radius: 20px;
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }
    .badge-completed {
        background: rgba(16, 185, 129, 0.12);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.25);
    }
    .badge-in-progress {
        background: rgba(59, 130, 246, 0.12);
        color: #3b82f6;
        border: 1px solid rgba(59, 130, 246, 0.25);
    }
    .badge-blocked {
        background: rgba(239, 68, 68, 0.12);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.25);
    }
    .badge-delayed {
        background: rgba(245, 158, 11, 0.12);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.25);
    }
    .badge-planned {
        background: rgba(148, 163, 184, 0.12);
        color: #94a3b8;
        border: 1px solid rgba(148, 163, 184, 0.25);
    }
    </style>
    """, unsafe_allow_html=True)

    # 4. RENDEROWANIE KART KPI
    # Upływ czasu - tekst pomocniczy
    if days_info and days_info.get("total_days", 0) > 0:
        time_pct = days_info.get("progress_pct", 0)
        time_sub = f"{days_info.get('elapsed_days', 0)} z {days_info.get('total_days', 0)} dni"
        time_val = f"{time_pct}%"
    else:
        time_val = "Brak"
        time_sub = "Brak harmonogramu"

    st.markdown(f"""
    <div class="kpi-container">
        <div class="kpi-card">
            <div class="kpi-title">🏗️ Postęp prac</div>
            <div class="kpi-value">{task_progress_pct}%</div>
            <div class="kpi-sub">{completed_tasks} z {total_tasks} zadań</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">📊 Postęp pomieszczeń</div>
            <div class="kpi-value">{phase_progress_avg}%</div>
            <div class="kpi-sub">średnia z pokoi/faz</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">⏱️ Upływ czasu</div>
            <div class="kpi-value">{time_val}</div>
            <div class="kpi-sub">{time_sub}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 5. RENDEROWANIE POMIESZCZEŃ
    show_amounts = (viewer_role == "investor")

    for ph in phases:
        ph_tasks = [t for t in tasks if t.get("phase_id") == ph.get("id")]
        ph_done = sum(1 for t in ph_tasks if is_task_completed_for_progress(t))
        ph_total = len(ph_tasks)
        ph_pct = int(ph_done / ph_total * 100) if ph_total > 0 else 0
        
        ph_name_esc = html.escape(ph.get("phase_name") or ph.get("name") or "—")
        emoji = get_room_emoji(ph_name_esc)

        # Karta pokoju
        st.markdown(f"""
        <div class="room-card">
            <div class="room-header">
                <div class="room-title">
                    <span>{emoji}</span>
                    <span>{ph_name_esc}</span>
                </div>
                <div class="room-stats">{ph_pct}% ({ph_done}/{ph_total})</div>
            </div>
            <div class="progress-container">
                <div class="progress-bar" style="width: {ph_pct}%;"></div>
            </div>
            <div class="task-list">
        """, unsafe_allow_html=True)

        if ph_tasks:
            for t in ph_tasks:
                # Logika statusów
                today_d = date.today()
                is_completed = is_task_completed_for_progress(t)
                is_blocked = bool(t.get("is_blocked"))
                
                # Czy opóźnione
                is_delayed = False
                if not is_completed and t.get("planned_end_date"):
                    try:
                        p_end = datetime.strptime(t["planned_end_date"], "%Y-%m-%d").date()
                        if p_end < today_d:
                            is_delayed = True
                    except:
                        pass
                
                # Przypisanie badge statusu
                if is_completed:
                    badge_class = "badge-completed"
                    badge_text = "✅ Ukończone"
                elif is_blocked:
                    badge_class = "badge-blocked"
                    badge_text = "⛔ Zablokowane"
                elif is_delayed:
                    badge_class = "badge-delayed"
                    badge_text = "⚠️ Opóźnione"
                elif str(t.get("kanban_status") or "").upper() in ("IN_PROGRESS", "DOING", "IN_REVIEW", "REVIEW"):
                    badge_class = "badge-in-progress"
                    badge_text = "🚀 W realizacji"
                else:
                    badge_class = "badge-planned"
                    badge_text = "⏳ Zaplanowane"

                # Kwota
                price_html = ""
                if show_amounts:
                    price = t.get("final_approved_price")
                    if price:
                        price_formatted = f"{int(price):,}".replace(",", " ") + " zł"
                        price_html = f'<div class="task-price">{price_formatted}</div>'
                    else:
                        price_html = '<div class="task-price" style="color: #64748b; font-weight: normal; font-style: italic;">brak wyceny</div>'

                t_name_esc = html.escape(t.get("name") or "—")

                st.markdown(f"""
                <div class="task-item">
                    <div class="task-left">
                        <span class="badge {badge_class}">{badge_text}</span>
                        <span class="task-name">{t_name_esc}</span>
                    </div>
                    {price_html}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="font-size: 13px; color: #64748b; font-style: italic; text-align: center; padding: 10px 0;">
                Brak zadań przypisanych do tego pomieszczenia.
            </div>
            """, unsafe_allow_html=True)

        # Zamknięcie karty pokoju
        st.markdown("</div></div>", unsafe_allow_html=True)
