import streamlit as st, requests
try:
    url = st.secrets['supabase']['url'] + '/rest/v1/?apikey=' + st.secrets['supabase']['key']
    res = requests.get(url).json()
    print('--- TABELE I KOLUMNY ---')
    for t, d in res.get('definitions', {}).items():
        print(f"\nTabela: {t}")
        for c, cd in d.get('properties', {}).items():
            desc = cd.get('description', '')
            ref = ' -> ' + desc if 'FKEY' in desc.upper() else ''
            print(f"  - {c} ({cd.get('type')}){ref}")
except Exception as e:
    print(f"Error: {e}")
