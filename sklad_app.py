# Tady je ta změna: Načítáme z 'secrets' místo ze souboru
        creds_dict = st.secrets["gcp_service_account"]
        gc = gspread.service_account_from_dict(creds_dict)
        return gc.open("Sklad_DB")
    except Exception as e:
        st.error(f"Chyba připojení: {e}")
        return Noneimport streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import time

# --- 1. KONFIGURACE A STYL ---
st.set_page_config(page_title="STARNET Sklad v137", layout="wide")
LOGO_URL = "https://www.starnet.cz/_app/immutable/assets/logo-full.BuKwkfDc.svg"

if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 'user_id': "", 'role': "", 
        'full_name': "", 'last_activity': 0.0
    })

st.markdown("""
    <style>
    .stApp { background-color: #ffffff; }
    .stTabs [aria-selected="true"] { color: #e30613 !important; border-bottom: 2px solid #e30613 !important; font-weight: bold; }
    div.stButton > button { background-color: #e30613 !important; color: white !important; font-weight: bold; border-radius: 5px; }
    .metric-card { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #e30613; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. JÁDRO (DB FUNKCE) ---

@st.cache_resource
def connect_db():
    try:
        # TENTO ŘÁDEK NESMÍ MÍT ŽÁDNOU MEZERU NA ZAČÁTKU (před "if")
            if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            gc = gspread.service_account_from_dict(creds_dict)
            return gc.open("Sklad_DB")
        else:
            st.error("❌ Chybí nastavení Secrets!")
            return None
    except Exception as e:
        st.error(f"❌ Chyba připojení: {e}")
        return None

sh = connect_db()

def get_data(sheet_name):
    if not sh: return pd.DataFrame()
    try:
        wks = sh.worksheet(sheet_name)
        df = pd.DataFrame(wks.get_all_records())
        df.columns = [c.lower().strip() for c in df.columns]
        for col in ['id', 'produkt_id', 'uzivatel_id', 'prijemce_id', 'ean', 'role', 'stav']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        return df
    except: return pd.DataFrame()

def log_movement(p_id, typ, qty, unit, price, src_id, tgt_id, ucel):
    try:
        wks = sh.worksheet("Pohyby")
        row = [datetime.now().strftime("%Y-%m-%d %H:%M"), str(p_id), typ, qty, unit, price, str(src_id), str(tgt_id), ucel]
        wks.append_row(row)
        return True
    except: return False

def get_balance(df_p, df_m, entity_id):
    if df_p.empty or df_m.empty: return pd.DataFrame()
    e_id = str(entity_id).strip()
    res = []
    for _, row in df_m.iterrows():
        p_id, p_rows = str(row['id']), df_p[df_p['produkt_id'] == str(row['id'])]
        if e_id == "Sklad":
            v_in = sum(pd.to_numeric(p_rows[(p_rows['prijemce_id'] == e_id) & (p_rows['typ'] != 'vratka_zadost')]['mnozstvi'], errors='coerce').fillna(0))
            v_out = sum(pd.to_numeric(p_rows[p_rows['uzivatel_id'] == e_id]['mnozstvi'], errors='coerce').fillna(0))
        else:
            v_in = sum(pd.to_numeric(p_rows[p_rows['prijemce_id'] == e_id]['mnozstvi'], errors='coerce').fillna(0))
            v_out = sum(pd.to_numeric(p_rows[p_rows['uzivatel_id'] == e_id]['mnozstvi'], errors='coerce').fillna(0))
        stav = v_in - v_out
        if stav != 0 or e_id == "Sklad":
            cena = pd.to_numeric(row.get('cena', 0), errors='coerce') or 0
            m_s = pd.to_numeric(row.get('min_stav', 0), errors='coerce') or 0
            res.append({
                'ID': p_id, 'Produkt': row['produkt'], 'Stav': stav, 'Min_stav': m_s,
                'Jednotka': row.get('jednotka', 'ks'), 'Hodnota': stav * cena, 
                'URL': row.get('url', ''), 'EAN': row.get('ean', '')
            })
    return pd.DataFrame(res)

def style_low_stock(row):
    return ['background-color: #ffcccc' if row['Stav'] < row['Min_stav'] else '' for _ in row]

# --- 3. ROZHRANÍ ---

if not st.session_state.logged_in:
    _, col_mid, _ = st.columns([1, 1.2, 1])
    with col_mid:
        st.image(LOGO_URL, use_container_width=True)
        with st.form("login"):
            l_in, p_in = st.text_input("Login").strip(), st.text_input("Heslo", type="password").strip()
            if st.form_submit_button("VSTOUPIT"):
                u_df = get_data("Uzivatele")
                match = u_df[(u_df['uzivatel'] == l_in) & (u_df['heslo'] == p_in)]
                if not match.empty:
                    r = match.iloc[0]
                    st.session_state.update({'logged_in': True, 'user_id': str(r['id']), 'role': str(r['role']).lower().strip(), 'full_name': f"{r['jmeno']} {r['prijmeni']}"})
                    st.rerun()
                st.error("❌ Neplatné údaje.")
else:
    c1, c2, c3 = st.columns([2, 4, 1])
    with c1: st.image(LOGO_URL, width=165)
    with c2: st.info(f"👤 **{st.session_state.full_name}** | ROLE: **{st.session_state.role.upper()}**")
    if c3.button("Odhlásit"): st.session_state.logged_in = False; st.rerun()

    df_p, df_u, df_m, df_o = get_data("Pohyby"), get_data("Uzivatele"), get_data("Produkty"), get_data("Objednavky")
    my_id = str(st.session_state.user_id)
    next_id = max(pd.to_numeric(df_m['id'], errors='coerce').dropna().astype(int).tolist() or [5000]) + 1

    if "skladnik" in st.session_state.role:
        t = st.tabs(["🛒 OBJEDNÁVKY", "📥 PŘÍJEM ZBOŽÍ", "📤 VÝDEJ", "📊 SKLAD", "👥 TECHNICI", "📦 PRODUKTY", "📜 LOG"])
        
        with t[0]: # OBJEDNÁVKY
            o_mode = st.radio("Produkt:", ["Stávající", "Nový produkt do systému"], horizontal=True, key="sk_o_m")
            with st.form("f_sk_o"):
                if o_mode == "Nový produkt do systému":
                    st.info(f"🆕 Budoucí ID: {next_id}")
                    nn, ne, nu = st.text_input("Název *"), st.text_input("EAN"), st.text_input("URL")
                    nm, nj = st.number_input("Min. stav", 0), st.selectbox("Jedn.", ["ks", "m", "bal"])
                else:
                    p_sel = st.selectbox("Produkt", [f"{r['id']} - {r['produkt']}" for _, r in df_m.iterrows()])
                    final_pid = p_sel.split(" - ")[0]
                oq, os = st.number_input("Kusů", 1), st.selectbox("Dodavatel", ["Sklad Starnet", "Sklad externí"])
                if st.form_submit_button("ULOŽIT"):
                    if o_mode == "Nový produkt do systému" and nn:
                        sh.worksheet("Produkty").append_row([str(next_id), nn, nu, nm, nj, 0, ne]); final_pid = str(next_id)
                    sh.worksheet("Objednavky").append_row([datetime.now().strftime("%Y-%m-%d"), final_pid, oq, os, my_id, "Objednáno", 0, ""]); st.rerun()

        with t[1]: # PŘÍJEM
            p_m = st.radio("Zdroj:", ["Z objednávky", "Přímý příjem (novinka)", "Vratky"], horizontal=True)
            if p_m == "Vratky":
                vratky = df_p[df_p['typ'] == 'vratka_zadost']
                if not vratky.empty:
                    v_r = vratky.merge(df_u[['id', 'jmeno', 'prijmeni']], left_on='uzivatel_id', right_on='id', how='left').merge(df_m[['id', 'produkt']], left_on='produkt_id', right_on='id', how='left')
                    for _, v in v_r.iterrows():
                        st.write(f"🔄 **{v['jmeno']} {v['prijmeni']}** vrací {v['mnozstvi']}ks - {v['produkt']}")
                        if st.button(f"Převzít: {v['produkt']}", key=f"v_{v['datum']}"):
                            wks_p = sh.worksheet("Pohyby"); cell = wks_p.find(v['datum']); wks_p.update_cell(cell.row, 3, "vratka_potvrzena"); st.rerun()
                else: st.info("Žádné vratky k vyřízení.")
            elif p_m == "Z objednávky":
                pend = df_o[df_o['stav'].str.lower() == 'objednáno'].merge(df_m[['id', 'produkt']], left_on='produkt_id', right_on='id', how='left')
                if not pend.empty:
                    o_c = st.selectbox("Objednávka:", [f"{r['produkt']} ({r['mnozstvi']} ks) | ID:{r['produkt_id']}" for _, r in pend.iterrows()])
                    oid = o_c.split("| ID:")[1]
                    with st.form("f_p_o"):
                        qq, pp = st.number_input("Počet", 1), st.number_input("Cena", 0.0)
                        if st.form_submit_button("POTVRDIT"):
                            log_movement(oid, "prijem", qq, "ks", pp, "Sklad Starnet", "Sklad", "obj"); st.rerun()
                else: st.info("Žádné otevřené objednávky k vyřízení.")
            else:
                with st.form("f_d_p"):
                    nn, ne, nu = st.text_input("Název *"), st.text_input("EAN"), st.text_input("URL")
                    nm, nj, nc = st.number_input("Min. stav", 0), st.selectbox("Jedn.", ["ks", "m"]), st.number_input("Cena", 0.0)
                    pq = st.number_input("Počet", 1)
                    if st.form_submit_button("ZAPSAT"):
                        sh.worksheet("Produkty").append_row([str(next_id), nn, nu, nm, nj, nc, ne]); log_movement(str(next_id), "prijem", pq, nj, nc, "Sklad externí", "Sklad", "direct"); st.rerun()

        with t[3]: # 📊 SKLAD
            st.subheader("Aktuální stav skladu")
            wh_bal = get_balance(df_p, df_m, "Sklad")
            if not wh_bal.empty:
                st.dataframe(wh_bal.style.apply(style_low_stock, axis=1), use_container_width=True, hide_index=True)
                csv = wh_bal.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 EXPORT PRO EXCEL (CSV)", data=csv, file_name=f"sklad_{datetime.now().strftime('%Y%m%d')}.csv", mime='text/csv')

        with t[2]: # VÝDEJ
            wh_bal = get_balance(df_p, df_m, "Sklad")
            # Robustnější vyhledávání techniků i zde
            t_df = df_u[df_u['role'].str.lower().str.contains('technik', na=False)]
            if not wh_bal[wh_bal['Stav']>0].empty and not t_df.empty:
                with st.form("f_sk_v"):
                    v_p = st.selectbox("Zboží", [f"{r['ID']} - {r['Produkt']} ({r['Stav']})" for _, r in wh_bal[wh_bal['Stav']>0].iterrows()])
                    v_q = st.number_input("Počet", 1)
                    t_m = {f"{r['jmeno']} {r['prijmeni']}": r['id'] for _, r in t_df.iterrows()}
                    v_t = st.selectbox("Technik", list(t_m.keys()))
                    if st.form_submit_button("VYDAT"):
                        log_movement(v_p.split(" - ")[0], "vydej", v_q, "ks", 0, "Sklad", t_m[v_t], "výdej"); st.rerun()

        with t[4]: # TECHNICI
            st.subheader("Mezisklady technických vozidel")
            # Oprava filtru: Odstranění case-sensitivity a mezer
            t_list = df_u[df_u['role'].str.lower().str.contains('technik', na=False)]
            if not t_list.empty:
                v_total = 0
                for tid in t_list['id']:
                    b = get_balance(df_p, df_m, tid)
                    if not b.empty: v_total += b['Hodnota'].sum()
                st.markdown(f'<div class="metric-card">HODNOTA V TERÉNU: <b>{v_total:,.2f} Kč</b></div>', unsafe_allow_html=True)
                sel_t = st.selectbox("Auto:", ["-- Vyberte --"] + [f"{r['jmeno']} {r['prijmeni']}" for _, r in t_list.iterrows()])
                if sel_t != "-- Vyberte --":
                    tid = t_list[(t_list['jmeno'] + " " + t_list['prijmeni']) == sel_t]['id'].values[0]
                    st.dataframe(get_balance(df_p, df_m, tid), use_container_width=True, hide_index=True)
            else: st.warning("V tabulce nebyli nalezeni žádní uživatelé s rolí Technik.")

        with t[5]: # PRODUKTY
            with st.expander("➕ NOVÝ PRODUKT"):
                with st.form("f_n_p"):
                    nn, ne, nu = st.text_input("Název *"), st.text_input("EAN"), st.text_input("URL")
                    nm, nj, np = st.number_input("Min. stav", 0), st.selectbox("Jedn.", ["ks", "m"]), st.number_input("Cena", 0.0)
                    if st.form_submit_button("ULOŽIT"):
                        sh.worksheet("Produkty").append_row([str(next_id), nn, nu, nm, nj, np, ne]); st.rerun()
            st.dataframe(df_m, use_container_width=True, hide_index=True, column_config={"url": st.column_config.LinkColumn("Odkaz")})

        with t[6]: st.dataframe(df_p.iloc[::-1], use_container_width=True, hide_index=True)

    elif "technik" in st.session_state.role:
        tt = st.tabs(["🚗 MOJE AUTO", "🛒 KOŠÍK", "⚡ SPOTŘEBA", "🔄 PŘESUN / SKLAD", "📜 LOG"])
        car = get_balance(df_p, df_m, my_id)
        wh = get_balance(df_p, df_m, "Sklad")

        with tt[3]: # PŘESUN (NEDOTČENO)
            others = df_u[(df_u['id'] != my_id) & (df_u['id'] != "")]
            o_map = {f"👤 Kolega: {r['jmeno']} {r['prijmeni']}": r['id'] for _, r in others.iterrows()}
            dest_options = ["Sklad"] + list(o_map.keys())
            if not car.empty:
                with st.form("f_t_m"):
                    p_sel = st.selectbox("Produkt:", [f"{r['ID']} - {r['Produkt']} ({r['Stav']})" for _, r in car.iterrows()])
                    p_qty = st.number_input("Množství", 1)
                    target_label = st.selectbox("Cíl:", dest_options)
                    if st.form_submit_button("POTVRDIT"):
                        p_id = p_sel.split(" - ")[0]
                        target_id, m_type = ("Sklad", "vratka_zadost") if target_label == "Sklad" else (o_map.get(target_label), "prevod")
                        log_movement(p_id, m_type, p_qty, "ks", 0, my_id, target_id, "presun"); st.rerun()

        with tt[0]: st.dataframe(car[['ID', 'Produkt', 'Stav', 'Jednotka', 'URL']], use_container_width=True, hide_index=True, column_config={"URL": st.column_config.LinkColumn("Web")})
        with tt[1]:
            avail = wh[wh['Stav']>0]
            if not avail.empty:
                with st.form("f_t_c"):
                    l_p = st.selectbox("Zboží:", [f"{r['ID']} - {r['Produkt']} ({r['Stav']})" for _, r in avail.iterrows()])
                    l_q = st.number_input("Beru si:", 1, int(avail[avail['ID']==l_p.split(" - ")[0]]['Stav'].iloc[0]))
                    if st.form_submit_button("PŘIDAT"):
                        log_movement(l_p.split(" - ")[0], "vydej", l_q, "ks", 0, "Sklad", my_id, "samoobsluha"); st.rerun()
        with tt[2]:
            if not car.empty:
                with st.form("f_t_s"):
                    s_p = st.selectbox("Z auta:", [f"{r['ID']} - {r['Produkt']} ({r['Stav']})" for _, r in car.iterrows()])
                    s_q, s_t = st.number_input("Kusů", 1), st.text_input("Zakázka")
                    if st.form_submit_button("ODPSAT"):
                        log_movement(s_p.split(" - ")[0], "spotreba", s_q, "ks", 0, my_id, s_t, "montáž"); st.rerun()
        with tt[4]:

            st.dataframe(df_p[(df_p['uzivatel_id']==my_id)|(df_p['prijemce_id']==my_id)].iloc[::-1], use_container_width=True, hide_index=True)

