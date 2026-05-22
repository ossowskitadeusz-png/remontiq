import streamlit as st
import pandas as pd
from datetime import datetime

def render_timeline_widget(timeline_service, project_id, ordering_service=None):
    """
    Renderuje wizualną oś czasu projektu (Gantt-like).
    Jeśli ordering_service jest dostępny, pokazuje sekwencyjne daty zadań.
    """
    timeline_data = timeline_service.get_project_timeline(
        project_id, ordering_service=ordering_service
    )
    
    if not timeline_data or not timeline_data.get('phases'):
        st.info("Brak zdefiniowanych faz projektu do wyświetlenia na osi czasu.")
        return

    # Nagłówek sekcji
    col_progress, col_stats = st.columns([2, 1])
    
    with col_progress:
        st.markdown(f"### Ogólny postęp: **{timeline_data['overall_progress']}%**")
        st.progress(timeline_data['overall_progress'] / 100)
    
    with col_stats:
        st.markdown(f"""
        <div style="background: rgba(255,255,255,0.05); padding: 10px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.1);">
            <div style="font-size: 12px; color: #94a3b8;">Status Projektu</div>
            <div style="font-size: 18px; font-weight: 700; color: #3b82f6;">{timeline_data['status']}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Renderowanie poszczególnych faz
    for phase in timeline_data['phases']:
        render_phase_row(phase)

def render_phase_row(phase):
    """
    Renderuje pojedynczy wiersz fazy z paskiem postępu, metrykami
    i sekwencyjnym harmonogramem zadań (jeśli dostępny).
    """
    status_colors = {
        "COMPLETED":  "#10b981",
        "IN_PROGRESS": "#3b82f6",
        "DELAYED":    "#ef4444",
        "PLANNING":   "#94a3b8"
    }
    status_label = {
        "COMPLETED":  "✅ UKOŃCZONO",
        "IN_PROGRESS": "🔵 W TRAKCIE",
        "DELAYED":    "🔴 OPÓŹNIONA",
        "PLANNING":   "⚪ PLANOWANIE"
    }
    
    color = status_colors.get(phase['status'], "#3b82f6")
    label = status_label.get(phase['status'], "NIEZNANY")
    
    def format_date(date_str):
        if not date_str: return "???"
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00')).strftime("%d %b")
        except:
            return "???"

    st.markdown(f"""
    <div style="background: white; padding: 20px; border-radius: 15px; margin-bottom: 5px;
                border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
            <div>
                <span style="font-weight: 800; font-size: 18px; color: #1e293b;">📦 {phase['phase_name']}</span>
                <span style="margin-left: 10px; font-size: 11px; font-weight: 700; color: {color};
                             border: 1px solid {color}; padding: 2px 8px; border-radius: 20px;">
                    {label}
                </span>
            </div>
            <div style="text-align: right;">
                <span style="font-size: 12px; color: #64748b;">
                    {format_date(phase['start_date'])} — {format_date(phase['end_date'])}
                </span>
            </div>
        </div>
        <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 10px;">
            <div style="flex-grow: 1; background: #f1f5f9; height: 12px; border-radius: 6px; overflow: hidden;">
                <div style="background: {color}; width: {phase['progress_percent']}%; height: 100%; border-radius: 6px;"></div>
            </div>
            <span style="font-weight: 700; color: #1e293b; font-size: 14px; width: 40px;">{phase['progress_percent']}%</span>
        </div>
        <div style="display: flex; gap: 20px; font-size: 12px; color: #64748b;">
            <span>📋 Zadania: <b>{phase['total_tasks']}</b> (✅{phase['completed_tasks']} ⏳{phase['in_progress_tasks']})</span>
            <span>⏱️ Czas: <b>{phase['elapsed_days']} / {phase['estimated_days']} dni</b></span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------
    # SEKWENCYJNY HARMONOGRAM ZADAŃ (nowe!)
    # -------------------------------------------------------
    seq_tasks = phase.get('sequential_tasks', [])
    if seq_tasks:
        with st.expander(f"📅 Harmonogram prac — {phase['phase_name']} ({len(seq_tasks)} zadań)", expanded=False):
            _render_sequential_tasks(seq_tasks, phase['progress_percent'])
    
    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)


def _render_sequential_tasks(tasks: list, phase_progress: float):
    """
    Renderuje listę zadań z kaskadowym harmonogramem dat.
    Wizualnie pokazuje: numer, nazwę, daty, pasek czasu względny, status.
    """
    if not tasks:
        st.caption("Brak zadań w tej fazie.")
        return

    # Oblicz zakres dat dla paska względnego
    first_start = tasks[0].get('seq_start')
    last_end    = tasks[-1].get('seq_end')
    total_span  = max((last_end - first_start).days, 1) if (first_start and last_end) else 1

    status_icons = {
        'READY':   '🟢',
        'PENDING': '⚪',
        'BLOCKED': '⏸️',
    }
    kanban_icons = {
        'DONE':               '✅',
        'IN_PROGRESS':        '🔵',
        'AWAITING_INSPECTION': '🔍',
        'TODO':               '⏳',
    }

    for idx, task in enumerate(tasks):
        seq_s = task.get('seq_start')
        seq_e = task.get('seq_end')
        dur   = task.get('duration_days', 1)

        # Pasek: offset i szerokość jako % całego zakresu
        if seq_s and first_start and total_span:
            offset_pct = max(0, (seq_s - first_start).days / total_span * 100)
            width_pct  = max(2, dur / total_span * 100)
        else:
            offset_pct, width_pct = 0, 10

        # Kolor zadania
        ks = task.get('kanban_status') or 'TODO'
        task_color = (
            '#10b981' if ks == 'DONE' else
            '#3b82f6' if ks == 'IN_PROGRESS' else
            '#f59e0b' if ks == 'AWAITING_INSPECTION' else
            '#94a3b8'
        )

        status_icon = status_icons.get(task.get('status', 'PENDING'), '⚪')
        kanban_icon = kanban_icons.get(ks, '⏳')
        name        = task.get('name', 'Zadanie')
        price       = task.get('final_price') or task.get('final_approved_price')
        price_str   = f"{float(price):,.0f} zł" if price else "brak ceny"
        start_str   = task.get('seq_start_str', '?')
        end_str     = task.get('seq_end_str', '?')

        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:10px;padding:8px 4px;border-bottom:1px solid #f1f5f9;">
            <div style="width:24px;text-align:center;font-size:11px;color:#94a3b8;flex-shrink:0;">#{idx+1}</div>
            <div style="width:180px;flex-shrink:0;">
                <div style="font-weight:600;font-size:13px;color:#1e293b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="{name}">{status_icon} {name}</div>
                <div style="font-size:10px;color:#94a3b8;">{kanban_icon} {ks}</div>
            </div>
            <div style="flex-grow:1;background:#f8fafc;height:22px;border-radius:4px;position:relative;overflow:hidden;">
                <div style="position:absolute;left:{offset_pct:.1f}%;width:{width_pct:.1f}%;height:100%;background:{task_color};border-radius:4px;opacity:0.85;"></div>
            </div>
            <div style="width:110px;text-align:right;flex-shrink:0;font-size:11px;color:#64748b;">
                {start_str} → {end_str}<br><span style="color:#94a3b8;">{dur} dni</span>
            </div>
            <div style="width:90px;text-align:right;flex-shrink:0;font-size:11px;font-weight:600;color:{'#10b981' if price else '#94a3b8'};">{price_str}</div>
        </div>
        """, unsafe_allow_html=True)
