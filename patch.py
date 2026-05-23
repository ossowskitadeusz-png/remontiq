import sys
import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern to match from "    # Obsługa przycisków funkcyjnych" to "# --- DALSZA LOGIKA DLA INWESTORA ---"
pattern = re.compile(r'    # Obsługa przycisków funkcyjnych.*?# --- DALSZA LOGIKA DLA INWESTORA ---', re.DOTALL)

replacement = """    # Obsługa Kokpitu Ekipy
    if menu == "crew_dashboard":
        from panels.crew_panel import render_crew_dashboard
        render_crew_dashboard(supabase, phase_service, negotiation_service, task_service)
        st.stop()

# --- DALSZA LOGIKA DLA INWESTORA ---"""

new_content, count = pattern.subn(replacement, content)

if count > 0:
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Replacement successful")
else:
    print("Could not find block to replace")
