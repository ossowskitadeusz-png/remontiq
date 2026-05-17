import streamlit as st
import pandas as pd
from datetime import datetime

def render_timeline_widget(timeline_service, project_id):
    """
    Renderuje wizualną oś czasu projektu (Gantt-like).
    """
    timeline_data = timeline_service.get_project_timeline(project_id)
    
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
    Renderuje pojedynczy wiersz fazy z paskiem postępu i metrykami.
    """
    # Kolory statusów
    status_colors = {
        "COMPLETED": "#10b981",  # Zielony
        "IN_PROGRESS": "#3b82f6", # Niebieski
        "DELAYED": "#ef4444",    # Czerwony
        "PLANNING": "#94a3b8"     # Szary
    }
    
    status_label = {
        "COMPLETED": "✅ UKOŃCZONO",
        "IN_PROGRESS": "🔵 W TRAKCIE",
        "DELAYED": "🔴 OPÓŹNIONA",
        "PLANNING": "⚪ PLANOWANIE"
    }
    
    color = status_colors.get(phase['status'], "#3b82f6")
    label = status_label.get(phase['status'], "NIEZNANY")
    
    # Formatowanie dat
    def format_date(date_str):
        if not date_str: return "???"
        return datetime.fromisoformat(date_str.replace('Z', '+00:00')).strftime("%d %b")

    st.markdown(f"""
    <div style="background: white; padding: 20px; border-radius: 15px; margin-bottom: 15px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
            <div>
                <span style="font-weight: 800; font-size: 18px; color: #1e293b;">📦 {phase['phase_name']}</span>
                <span style="margin-left: 10px; font-size: 11px; font-weight: 700; color: {color}; border: 1px solid {color}; padding: 2px 8px; border-radius: 20px;">
                    {label}
                </span>
            </div>
            <div style="text-align: right;">
                <span style="font-size: 12px; color: #64748b;">{format_date(phase['start_date'])} — {format_date(phase['end_date'])}</span>
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
