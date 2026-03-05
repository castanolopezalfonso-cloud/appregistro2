import streamlit as st
import pandas as pd
import calendar
import json
import os
import sqlite3
from datetime import datetime, time, timedelta, date
from fpdf import FPDF

# --- 1. CONFIGURACIÓN Y ESTILO ---
st.set_page_config(page_title="Control Diario - Gestión Elite", layout="wide", page_icon="🚀")

try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    
    /* --- DISEÑO DE PESTAÑAS MODERNAS --- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: transparent;
        padding: 10px 0px;
    }

    .stTabs [data-baseweb="tab"] {
        height: 60px;
        background-color: #161b22;
        border-radius: 12px 12px 0px 0px;
        border: 1px solid #30363d;
        border-bottom: none;
        padding: 10px 30px;
        font-weight: bold;
        color: #8b949e;
        transition: all 0.3s ease;
        font-size: 1.1rem;
        letter-spacing: 1px;
    }

    .stTabs [data-baseweb="tab"]:hover {
        background-color: #1c2128;
        color: #f0f6fc;
        transform: translateY(-2px);
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(145deg, #161b22, #00c0f222) !important;
        color: #00c0f2 !important;
        border-top: 3px solid #00c0f2 !important;
        box-shadow: 0px -5px 15px rgba(0, 192, 242, 0.2);
    }

    /* --- ESTILOS DE MÉTRICAS Y CELDAS --- */
    [data-testid="stMetric"] {
        background-color: #161b22;
        border-radius: 15px;
        padding: 15px !important;
        border: 1px solid #30363d;
    }
    [data-testid="stMetricValue"] { color: #00c0f2 !important; }
    
    .cal-cell {
        border-radius: 10px !important;
        padding: 8px !important;
        min-height: 95px !important;
        border: 1px solid #30363d !important;
        margin-bottom: 5px;
        transition: transform 0.2s;
        color: white;
        overflow: hidden;
        word-wrap: break-word;
    }
    .cal-cell:hover { transform: scale(1.03); border-color: #f0f6fc !important; }
    
    /* GLOWS ESPECIALES */
    .hoy-calendario-glow { 
        border: 3px solid #ffea00 !important; 
        box-shadow: 0 0 20px rgba(255, 234, 0, 0.6) !important;
        position: relative;
        z-index: 1;
    }
    .festivo-glow { border: 2px solid #ff9800 !important; box-shadow: 0 0 12px rgba(255, 152, 0, 0.4); }
    .finde-glow { border: 2px solid #58a6ff !important; box-shadow: 0 0 12px rgba(88, 166, 255, 0.4); }
    .vaca-glow { border: 2px solid #00ff88 !important; box-shadow: 0 0 12px rgba(0, 255, 136, 0.4); }
    .descanso-glow { border: 2px solid #ffffff !important; box-shadow: 0 0 12px rgba(255, 255, 255, 0.3); }

    .sidebar-info { 
        background: #1b1f23; padding: 15px; border-radius: 10px; border-left: 4px solid #8b949e; margin-bottom: 15px; 
    }
    
    .glow-today-lime { 
        border: 1px solid #ccff00 !important; box-shadow: 0 0 15px rgba(204, 255, 0, 0.3); 
        border-left: 5px solid #ccff00 !important; background: linear-gradient(145deg, #1b1f23, #1a2300);
    }
    .glow-next-violet { 
        border: 1px solid #bc13fe !important; box-shadow: 0 0 15px rgba(188, 19, 254, 0.3); 
        border-left: 5px solid #bc13fe !important; background: linear-gradient(145deg, #1b1f23, #150023);
    }
    
    .stButton>button { border-radius: 15px !important; font-weight: bold !important; }
    .event-text { font-size: 0.7rem; font-weight: 500; line-height: 1.1; display: block; margin-top: 4px; }
    
    /* ESTILO TARJETAS VACACIONES/DESCANSOS */
    .stat-card {
        padding: 15px;
        border-radius: 15px;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

FILE_REGISTRO = "datos_jornadas.csv"
FILE_TARIFAS = "config_tarifas.json"

# --- 2. LÓGICA DE CÁLCULO Y FUNCIONES ---
def calcular_total_con_extras(tarifa_obj, horas_extra_totales):
    precio_base = float(tarifa_obj['precio'])
    extra_base_precio = float(tarifa_obj['extra'])
    precios_especificos = tarifa_obj.get('extras_especificos', {})
    total_extras = 0.0
    
    for i in range(1, int(horas_extra_totales) + 1):
        precio_hora = precios_especificos.get(str(i + int(tarifa_obj['horas_std'])), 0.0)
        if precio_hora == 0.0: precio_hora = extra_base_precio
        total_extras += float(precio_hora)
        
    fraccion = horas_extra_totales - int(horas_extra_totales)
    if fraccion > 0:
        siguiente_hora = int(horas_extra_totales) + int(tarifa_obj['horas_std']) + 1
        precio_hora_frac = precios_especificos.get(str(siguiente_hora), 0.0)
        if precio_hora_frac == 0.0: precio_hora_frac = extra_base_precio
        total_extras += (fraccion * float(precio_hora_frac))
    return precio_base + total_extras

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'REGISTRO DE JORNADAS', 0, 1, 'C')
        self.ln(5)

def exportar_pdf(df, mes, anio):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    col_widths = [25, 50, 30, 20, 20, 20, 25]
    headers = ["Fecha", "Evento", "Tarifa", "Entrada", "Salida", "Extras", "Total"]
    pdf.set_fill_color(200, 220, 255)
    for i, h in enumerate(headers): pdf.cell(col_widths[i], 10, h, 1, 0, 'C', True)
    pdf.ln()
    for _, row in df.iterrows():
        # Asegurar que evento_limpio sea siempre str para el type checker
        evento_limpio: str = str(row['Evento']) if pd.notnull(row['Evento']) else ""
        
        pdf.cell(col_widths[0], 10, row['Fecha'].strftime('%d/%m/%Y'), 1)
        pdf.cell(col_widths[1], 10, str(evento_limpio[:25]), 1)
        pdf.cell(col_widths[2], 10, str(row['Tarifa']), 1)
        pdf.cell(col_widths[3], 10, str(row['H_Entrada'] if row['H_Entrada'] else "-"), 1)
        pdf.cell(col_widths[4], 10, str(row['H_Salida'] if row['H_Salida'] else "-"), 1)
        pdf.cell(col_widths[5], 10, f"{row['Horas Extra']:.1f}", 1)
        pdf.cell(col_widths[6], 10, f"{row['Total']:.2f} EUR", 1)
        pdf.ln()
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"TOTAL MES: {df['Total'].sum():,.2f} EUR", 0, 1, 'R')
    return pdf.output(dest='S').encode('latin-1')

def obtener_info_dia(fecha):
    y = fecha.year
    es_finde = fecha.weekday() >= 5
    es_fest = False
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19*a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2*e + 2*i - h - k) % 7
    m = (a + 11*h + 22*l) // 451
    mes_pascua = (h + l - 7*m + 114) // 31
    dia_pascua = ((h + l - 7*m + 114) % 31) + 1
    domingo_pascua = date(y, mes_pascua, dia_pascua)
    jueves_santo = domingo_pascua - timedelta(days=3)
    viernes_santo = domingo_pascua - timedelta(days=2)
    festivos_fijos = [date(y, 1, 1), date(y, 1, 6), date(y, 5, 1), date(y, 5, 2), date(y, 5, 15), date(y, 8, 15), date(y, 10, 12), date(y, 11, 1), date(y, 11, 9), date(y, 12, 6), date(y, 12, 8), date(y, 12, 25)]
    todos = festivos_fijos + [jueves_santo, viernes_santo]
    trasladados = [f + timedelta(days=1) for f in todos if f.weekday() == 6]
    if fecha.date() in todos or fecha.date() in trasladados: es_fest = True
    return es_fest, es_finde

def init_db(db_file):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS registro (
                 Fecha TEXT, Tarifa TEXT, Evento TEXT, 
                 "Horas Jornada" REAL, "Horas Extra" REAL, Total REAL, 
                 En_Registro INTEGER, H_Entrada TEXT, H_Salida TEXT, Modo_Horas TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tarifas (id INTEGER PRIMARY KEY, config TEXT)''')
    conn.commit()
    
    # Migración de datos antiguos (solo para el primer usuario que migre)
    if os.path.exists(FILE_REGISTRO) and not c.execute("SELECT COUNT(*) FROM registro").fetchone()[0]:
        try:
            df = pd.read_csv(FILE_REGISTRO)
            df.to_sql('registro', conn, if_exists='append', index=False)
            os.rename(FILE_REGISTRO, FILE_REGISTRO + ".bak")
        except:
            pass
            
    if os.path.exists(FILE_TARIFAS) and not c.execute("SELECT COUNT(*) FROM tarifas").fetchone()[0]:
        try:
            with open(FILE_TARIFAS, "r") as f:
                config = f.read()
            c.execute("INSERT INTO tarifas (config) VALUES (?)", (config,))
            conn.commit()
            os.rename(FILE_TARIFAS, FILE_TARIFAS + ".bak")
        except:
            pass
            
    conn.close()

def cargar_tarifas(db_file):
    init_db(db_file)
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    row = c.execute("SELECT config FROM tarifas ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    
    tarifas = []
    if row:
        tarifas = json.loads(row[0])
    else:
        tarifas = [{"nombre": "Normal", "precio": 200.0, "extra": 25.0, "color": "#00c0f2", "horas_std": 8.0, "en_registro": True, "extras_especificos": {}}]
        
    nombres_existentes = [str(t.get("nombre", "")).upper() for t in tarifas]
    if "VACACIONES" not in nombres_existentes:
        tarifas.append({"nombre": "VACACIONES", "precio": 0.0, "extra": 0.0, "color": "#00ff88", "horas_std": 0.0, "en_registro": False, "extras_especificos": {}})
    if "DESCANSO" not in nombres_existentes:
        tarifas.append({"nombre": "DESCANSO", "precio": 0.0, "extra": 0.0, "color": "#ffffff", "horas_std": 0.0, "en_registro": False, "extras_especificos": {}})
        
    for t in tarifas:
        if str(t.get("nombre", "")).upper() in ["VACACIONES", "DESCANSO"]:
            t["precio"] = 0.0  # type: ignore
            t["extra"] = 0.0  # type: ignore
            t["horas_std"] = 0.0  # type: ignore
            t["en_registro"] = False  # type: ignore

    return tarifas

def guardar_tarifas(tarifas, db_file):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute("INSERT INTO tarifas (config) VALUES (?)", (json.dumps(tarifas),))
    conn.commit()
    conn.close()

def cargar_datos(db_file):
    init_db(db_file)
    conn = sqlite3.connect(db_file)
    cols = ["Fecha", "Tarifa", "Evento", "Horas Jornada", "Horas Extra", "Total", "En_Registro", "H_Entrada", "H_Salida", "Modo_Horas"]
    try:
        df = pd.read_sql('SELECT * FROM registro', conn)
        if not df.empty:
            df['Fecha'] = pd.to_datetime(df['Fecha'])
            for c in cols:
                if c not in df.columns: df[c] = None
            conn.close()
            return df[cols]
    except:
        pass
    conn.close()
    df = pd.DataFrame(columns=cols)
    df['Fecha'] = pd.to_datetime(df['Fecha'])
    return df[cols]

def guardar_datos(df, db_file):
    conn = sqlite3.connect(db_file)
    df.to_sql('registro', conn, if_exists='replace', index=False)
    conn.close()

# --- 3. INICIO SESIÓN MULTI-USUARIO ---
if 'usuario_actual' not in st.session_state:
    st.session_state.usuario_actual = None

if not st.session_state.usuario_actual:
    st.title("🛡️ Elite Access")
    user_input = st.text_input("Username")
    pass_input = st.text_input("Password", type="password")
    if st.button("Unlock"):
        usuarios_validos = st.secrets.get("users", {})
        if user_input in usuarios_validos and pass_input == usuarios_validos[user_input]:
            st.session_state.usuario_actual = user_input
            st.session_state.db_file = f"registro_{user_input}.db"
            st.rerun()
        else:
            st.error("Credenciales incorrectas")
    st.stop()

# Garantizar que db_file esté siempre definido (por si la sesión persiste sin rerun)
if 'db_file' not in st.session_state:
    st.session_state.db_file = f"registro_{st.session_state.usuario_actual}.db"

if 'tarifas' not in st.session_state: st.session_state.tarifas = cargar_tarifas(st.session_state.db_file)
if 'registro' not in st.session_state: st.session_state.registro = cargar_datos(st.session_state.db_file)

# Asegurar que Fecha sea datetime aunque venga de una sesión antigua cacheada
st.session_state.registro['Fecha'] = pd.to_datetime(st.session_state.registro['Fecha'])

# --- 4. SIDEBAR ---
with st.sidebar:
    st.header("📝 Gestión de Jornadas")
    st.divider()
    ahora = datetime.now()
    hoy_dt = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    hoy_ts = pd.Timestamp(hoy_dt.date())
    manana_ts = pd.Timestamp((hoy_dt + timedelta(days=1)).date())
    
    df_actual = st.session_state.registro[st.session_state.registro['Fecha'].dt.month == hoy_dt.month]
    jornadas_mes = len(df_actual[df_actual['En_Registro'] == True])
    st.markdown(f'<div class="sidebar-info"><p style="margin:0; font-size:0.8rem; color:#8b949e;">MES ACTUAL</p><h3 style="margin:0; color:#00c0f2;">{jornadas_mes} Jornadas</h3></div>', unsafe_allow_html=True)
    
    df_hoy = st.session_state.registro[st.session_state.registro['Fecha'] == hoy_ts]
    ev_h = df_hoy.iloc[0]['Evento'] if (not df_hoy.empty and df_hoy.iloc[0]['Evento']) else "Sin actividad"
    st.markdown(f'<div class="sidebar-info glow-today-lime"><p style="margin:0; font-size:0.8rem; color:#ccff00; font-weight:bold;">HOY (ACTUAL)</p><p style="margin:0; font-weight:bold; color:white;">{ev_h}</p></div>', unsafe_allow_html=True)

    df_manana = st.session_state.registro[st.session_state.registro['Fecha'] == manana_ts]
    ev_m = df_manana.iloc[0]['Evento'] if (not df_manana.empty and df_manana.iloc[0]['Evento']) else "Sin asignar"
    st.markdown(f'<div class="sidebar-info glow-next-violet"><p style="margin:0; font-size:0.8rem; color:#bc13fe; font-weight:bold;">MAÑANA (PLAN)</p><p style="margin:0; font-weight:bold; color:white;">{ev_m}</p></div>', unsafe_allow_html=True)

    st.divider()
    if st.button("⚡ DUPLICAR AYER EN HOY", use_container_width=True):
        f_ayer = pd.Timestamp((hoy_dt - timedelta(days=1)).date())
        ayer_d = st.session_state.registro[st.session_state.registro['Fecha'] == f_ayer]
        if not ayer_d.empty:
            nueva = ayer_d.iloc[0].copy(); nueva['Fecha'] = hoy_ts
            st.session_state.registro = pd.concat([st.session_state.registro[st.session_state.registro['Fecha'] != hoy_ts], pd.DataFrame([nueva])], ignore_index=True)
            st.rerun()

    st.divider()
    if st.button("➕ Nueva Tarifa"):
        st.session_state.tarifas.append({"nombre":"Nueva","precio":0.0,"extra":0.0,"color":"#ffffff","horas_std":8.0,"en_registro":True, "extras_especificos": {}})
    
    with st.expander("⚙️ CONFIGURACIÓN TARIFAS"):
        for i, t in enumerate(st.session_state.tarifas):
            if str(t.get('nombre', '')).upper() in ["VACACIONES", "DESCANSO"]:
                st.markdown(f"**{t['nombre']}** *(Sistema - No cuenta para horas/pagos)*")
                continue
                
            with st.expander(f"Tarifa: {t['nombre']}"):
                st.session_state.tarifas[i]['nombre'] = st.text_input("Nombre", value=t['nombre'], key=f"n_{i}")
                st.session_state.tarifas[i]['en_registro'] = st.checkbox("Incluir en totales", value=t.get('en_registro', True), key=f"reg_{i}")
                st.session_state.tarifas[i]['precio'] = st.number_input("Base €", value=float(t['precio']), key=f"p_{i}")
                st.session_state.tarifas[i]['horas_std'] = st.number_input("Horas Jornada (Std)", value=float(t.get('horas_std', 8.0)), key=f"std_{i}")
                st.session_state.tarifas[i]['extra'] = st.number_input("Extra General (€/h)", value=float(t['extra']), key=f"e_{i}")
                with st.expander("💰 Extras Especiales"):
                    if 'extras_especificos' not in t: st.session_state.tarifas[i]['extras_especificos'] = {}
                    for h_idx in range(1, 11): 
                        h_real = int(t.get('horas_std', 8)) + h_idx
                        h_s = str(h_real)
                        v_a = t.get('extras_especificos', {}).get(h_s, 0.0)
                        st.session_state.tarifas[i]['extras_especificos'][h_s] = st.number_input(f"Hora {h_real} (€)", value=float(v_a), key=f"eh_{i}_{h_idx}")
                st.session_state.tarifas[i]['color'] = st.color_picker("Color", value=t['color'], key=f"c_{i}")
                if st.button("Eliminar", key=f"del_{i}"): st.session_state.tarifas.pop(i); st.rerun()

    if st.button("💾 GUARDAR CAMBIOS", type="primary", use_container_width=True):
        guardar_tarifas(st.session_state.tarifas, st.session_state.db_file)
        guardar_datos(st.session_state.registro, st.session_state.db_file)
        st.success("Guardado en la Base de Datos")

# --- 5. TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📅 CALENDARIO", "🔍 BUSCADOR", "📊 ANUAL", "📈 ESTADÍSTICAS"])
meses_n = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

with tab1:
    c1, c2 = st.columns([2,1])
    m_sel = c1.selectbox("Mes", meses_n, index=datetime.now().month - 1)
    a_sel = c2.number_input("Año", value=2026)
    m_idx = meses_n.index(m_sel) + 1
    cal = calendar.monthcalendar(a_sel, m_idx)
    
    cols_h = st.columns(7)
    for j, d_n in enumerate(["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]): 
        cols_h[j].markdown(f"<p style='text-align:center; color:#00c0f2;'><b>{d_n}</b></p>", unsafe_allow_html=True)
    
    for sem in cal:
        cols = st.columns(7)
        for i, dia in enumerate(sem):
            if dia != 0:
                f_dt = pd.Timestamp(datetime(a_sel, m_idx, dia))
                data_d = st.session_state.registro[st.session_state.registro['Fecha'] == f_dt]
                es_fest, es_fin = obtener_info_dia(f_dt)
                es_hoy_real = (f_dt.date() == datetime.now().date())
                nom_t = str(data_d.iloc[0]['Tarifa']).upper() if (not data_d.empty and pd.notna(data_d.iloc[0]['Tarifa'])) else ""
                
                c_c = "cal-cell"
                if es_hoy_real: c_c += " hoy-calendario-glow"
                if nom_t == "VACACIONES": c_c += " vaca-glow"
                elif nom_t == "DESCANSO": c_c += " descanso-glow"
                elif es_fest: c_c += " festivo-glow"
                elif es_fin: c_c += " finde-glow"
                
                bg = next((tf['color'] for tf in st.session_state.tarifas if tf['nombre'] == data_d.iloc[0]['Tarifa']), "#161b22") if not data_d.empty else "#161b22"
                ev = data_d.iloc[0]['Evento'] if not data_d.empty else ""
                
                cols[i].markdown(f'<div class="{c_c}" style="background-color: {bg}66; border-top: 5px solid {bg if not data_d.empty else "#30363d"};"><b>{dia}</b><span class="event-text">{ev}</span></div>', unsafe_allow_html=True)
                
                if cols[i].button("✎", key=f"btn_{a_sel}_{m_idx}_{dia}", use_container_width=True): 
                    st.session_state.dia_sel = f_dt

    if 'dia_sel' in st.session_state:
        st.divider()
        f_t = pd.to_datetime(st.session_state.dia_sel)
        ex = st.session_state.registro[st.session_state.registro['Fecha'] == f_t]
        
        st.subheader(f"Registro: {f_t.strftime('%d/%m/%Y')}")
        c1, c2, c3 = st.columns(3)
        
        v_t = ex.iloc[0]['Tarifa'] if (not ex.empty and ex.iloc[0]['Tarifa'] in [tf['nombre'] for tf in st.session_state.tarifas]) else st.session_state.tarifas[0]['nombre']
        t_sel = c1.selectbox("Tarifa", [tf['nombre'] for tf in st.session_state.tarifas], index=[tf['nombre'] for tf in st.session_state.tarifas].index(v_t))
        e_nom = c2.text_input("Evento", value=ex.iloc[0]['Evento'] if not ex.empty else "")
        v_modo = ex.iloc[0]['Modo_Horas'] if not ex.empty and pd.notnull(ex.iloc[0]['Modo_Horas']) else "Horas Estándar"
        modo = c3.radio("Modo", ["Horas Estándar", "Entrada/Salida"], index=0 if v_modo == "Horas Estándar" else 1, horizontal=True)
        
        h_jornada_final, h_extra_final = 0.0, 0.0
        h_in_str, h_out_str = None, None
        tf_actual = next(tf for tf in st.session_state.tarifas if tf['nombre'] == t_sel)

        if modo == "Horas Estándar": 
            h_jornada_final = float(tf_actual['horas_std'])
            h_extra_final = st.number_input("Extras Manuales", value=float(ex.iloc[0]['Horas Extra']) if not ex.empty else 0.0)
        else:
            d_in, d_out = time(8,0), time(18,0)
            if not ex.empty and pd.notnull(ex.iloc[0]['H_Entrada']):
                try: d_in = datetime.strptime(str(ex.iloc[0]['H_Entrada']), "%H:%M").time()
                except: pass
            if not ex.empty and pd.notnull(ex.iloc[0]['H_Salida']):
                try: d_out = datetime.strptime(str(ex.iloc[0]['H_Salida']), "%H:%M").time()
                except: pass
            
            ci, co = st.columns(2)
            ti, to = ci.time_input("Entrada", d_in), co.time_input("Salida", d_out)
            h_in_str, h_out_str = ti.strftime("%H:%M"), to.strftime("%H:%M")
            
            dt_i, dt_o = datetime.combine(date.today(), ti), datetime.combine(date.today(), to)
            if to <= ti: dt_o += timedelta(days=1)
            
            horas_totales_reales = (dt_o - dt_i).total_seconds() / 3600
            h_jornada_final = min(horas_totales_reales, float(tf_actual['horas_std']))
            h_extra_final = max(0.0, horas_totales_reales - float(tf_actual['horas_std']))

        c_btn1, c_btn2 = st.columns(2)
        if c_btn1.button("💾 GUARDAR REGISTRO", use_container_width=True, type="primary"):
            total_dinero = calcular_total_con_extras(tf_actual, h_extra_final)
            
            # SOLUCIÓN ERROR ROUND: Forzar float antes de redondear
            nueva_fila = {
                "Fecha": f_t, "Tarifa": t_sel, "Evento": e_nom, 
                "Horas Jornada": float(round(float(h_jornada_final), 2)), 
                "Horas Extra": float(round(float(h_extra_final), 2)), 
                "Total": total_dinero, "En_Registro": tf_actual['en_registro'], 
                "Modo_Horas": modo, "H_Entrada": h_in_str, "H_Salida": h_out_str
            }
            st.session_state.registro = pd.concat([st.session_state.registro[st.session_state.registro['Fecha'] != f_t], pd.DataFrame([nueva_fila])], ignore_index=True)
            guardar_datos(st.session_state.registro, st.session_state.db_file)
            if 'dia_sel' in st.session_state: del st.session_state.dia_sel
            st.rerun()
            
        if c_btn2.button("🗑️ ELIMINAR REGISTRO", use_container_width=True):
            st.session_state.registro = st.session_state.registro[st.session_state.registro['Fecha'] != f_t]
            guardar_datos(st.session_state.registro, st.session_state.db_file)
            if 'dia_sel' in st.session_state: del st.session_state.dia_sel
            st.rerun()

    st.divider()
    df_m = st.session_state.registro[(st.session_state.registro['Fecha'].dt.month == m_idx) & (st.session_state.registro['Fecha'].dt.year == a_sel)].sort_values("Fecha")
    if not df_m.empty:
        df_reg = df_m[df_m['En_Registro'] == True].copy()
        df_reg["Horas Totales"] = df_reg["Horas Jornada"].fillna(0) + df_reg["Horas Extra"].fillna(0)
        
        cont_vaca_mes = len(df_m[df_m['Tarifa'].astype(str).str.upper() == "VACACIONES"])
        cont_desc_mes = len(df_m[df_m['Tarifa'].astype(str).str.upper() == "DESCANSO"])
        df_anual_full_cont = st.session_state.registro[st.session_state.registro['Fecha'].dt.year == a_sel]
        cont_vaca_ano = len(df_anual_full_cont[df_anual_full_cont['Tarifa'].astype(str).str.upper() == "VACACIONES"])
        cont_desc_ano = len(df_anual_full_cont[df_anual_full_cont['Tarifa'].astype(str).str.upper() == "DESCANSO"])

        st.subheader(f"🏖️ Control de Disponibilidad - {m_sel}")
        col_v1, col_v2, col_d1, col_d2 = st.columns(4)
        
        with col_v1:
            st.markdown(f'<div class="stat-card" style="background: #00ff8811; border: 1px solid #00ff8844; border-left: 5px solid #00ff88;"><p style="margin:0; color:#00ff88; font-size:0.8rem; font-weight:bold;">VACACIONES MES</p><h2 style="margin:0; color:white;">{cont_vaca_mes} <span style="font-size:1rem;">días</span></h2></div>', unsafe_allow_html=True)
        with col_v2:
            st.markdown(f'<div class="stat-card" style="background: #161b22; border: 1px solid #30363d; border-left: 5px solid #00ff8888;"><p style="margin:0; color:#8b949e; font-size:0.8rem;">VACACIONES ANUAL</p><h2 style="margin:0; color:white;">{cont_vaca_ano} <span style="font-size:1rem;">días</span></h2></div>', unsafe_allow_html=True)
        with col_d1:
            st.markdown(f'<div class="stat-card" style="background: #ffffff11; border: 1px solid #ffffff44; border-left: 5px solid #ffffff;"><p style="margin:0; color:#ffffff; font-size:0.8rem; font-weight:bold;">DESCANSOS MES</p><h2 style="margin:0; color:white;">{cont_desc_mes} <span style="font-size:1rem;">días</span></h2></div>', unsafe_allow_html=True)
        with col_d2:
            st.markdown(f'<div class="stat-card" style="background: #161b22; border: 1px solid #30363d; border-left: 5px solid #ffffff88;"><p style="margin:0; color:#8b949e; font-size:0.8rem;">DESCANSOS ANUAL</p><h2 style="margin:0; color:white;">{cont_desc_ano} <span style="font-size:1rem;">días</span></h2></div>', unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        with st.expander("👁️ MOSTRAR DATOS ECONÓMICOS DEL MES"):
            st.dataframe(df_reg[["Fecha", "Evento", "Tarifa", "H_Entrada", "H_Salida", "Horas Jornada", "Horas Extra", "Horas Totales", "Total"]], use_container_width=True, hide_index=True)
            c1, c2, c3 = st.columns(3); c1.metric("Jornadas", len(df_reg)); c2.metric("Horas Mes", f"{df_reg['Horas Totales'].sum():.1f}h"); c3.metric("Total Mes", f"{df_reg['Total'].sum():,.2f} €")
        
        pdf_data = exportar_pdf(df_reg, m_sel, a_sel)
        st.download_button(label="📥 Descargar PDF", data=pdf_data, file_name=f"Registro_{m_sel}.pdf", mime="application/pdf", use_container_width=True)

with tab2:
    st.subheader("🔍 Buscador")
    if not st.session_state.registro.empty:
        ct, cl, cy = st.columns([2, 2, 1]); q = ct.text_input("Buscar evento...")
        lista_ev = sorted([str(e) for e in st.session_state.registro["Evento"].dropna().unique() if e != ""])
        sel_ev = cl.selectbox("Seleccionar", ["Todos"] + lista_ev); yr_s = cy.number_input("Año", value=2026, key="sy")
        df_f = st.session_state.registro[st.session_state.registro["Fecha"].dt.year == yr_s]
        if q: df_f = df_f[df_f["Evento"].str.contains(q, case=False, na=False)]
        if sel_ev != "Todos": df_f = df_f[df_f["Evento"] == sel_ev]
        
        with st.expander("Ver resultados de búsqueda"):
            st.dataframe(df_f.sort_values("Fecha", ascending=False), use_container_width=True, hide_index=True)

with tab3:
    st.subheader(f"📊 Resumen Anual {a_sel}")
    df_anual_full = st.session_state.registro[st.session_state.registro['Fecha'].dt.year == a_sel]
    df_anual = df_anual_full[df_anual_full['En_Registro'] == True].copy()
    if not df_anual_full.empty:
        df_anual["Horas Totales"] = df_anual["Horas Jornada"].fillna(0) + df_anual["Horas Extra"].fillna(0)
        
        with st.expander("💰 MOSTRAR TOTALES ECONÓMICOS ANUALES"):
            c1, c2, c3 = st.columns(3); c1.metric("TOTAL ANUAL", f"{df_anual['Total'].sum():,.2f} €"); c2.metric("JORNADAS", len(df_anual)); c3.metric("HORAS AÑO", f"{df_anual['Horas Totales'].sum():.1f}h")
            res_list = [{"Mes": m, "Jornadas": int(len(df_anual[df_anual['Fecha'].dt.month == (i+1)])), "Total (€)": float(df_anual[df_anual['Fecha'].dt.month == (i+1)]['Total'].sum())} for i, m in enumerate(meses_n)]
            st.table(pd.DataFrame(res_list).style.format({"Total (€)": "{:,.2f} €"}))

with tab4:
    st.subheader("📈 Estadísticas y Frecuencia")
    df_st_full = st.session_state.registro[st.session_state.registro['Fecha'].dt.year == a_sel]
    df_st = df_st_full[df_st_full['En_Registro'] == True].copy()
    
    if not df_st_full.empty:
        d_list = [{"Mes": m, 
                   "Descanso": len(df_st_full[(df_st_full['Fecha'].dt.month == (i+1)) & (df_st_full['Tarifa'].astype(str).str.upper() == "DESCANSO")]), 
                   "Vaca": len(df_st_full[(df_st_full['Fecha'].dt.month == (i+1)) & (df_st_full['Tarifa'].astype(str).str.upper() == "VACACIONES")])} 
                  for i, m in enumerate(meses_n)]
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("Descansos Año", len(df_st_full[df_st_full['Tarifa'].astype(str).str.upper() == 'DESCANSO']))
            st.metric("Vacaciones Año", len(df_st_full[df_st_full['Tarifa'].astype(str).str.upper() == 'VACACIONES']))
        with c2:
            st.write("**Días Libres por Mes**")
            st.dataframe(pd.DataFrame(d_list), hide_index=True, use_container_width=True)

        st.divider()

        st.write("### 🏆 Ranking de Tarifas")
        if not df_st.empty:
            df_st["Horas Totales"] = df_st["Horas Jornada"].fillna(0) + df_st["Horas Extra"].fillna(0)
            stats_tarifas = df_st.groupby("Tarifa").agg({
                "Fecha": "count",
                "Horas Totales": "sum"
            }).rename(columns={"Fecha": "Veces Utilizada", "Horas Totales": "Total Horas"}).sort_values("Veces Utilizada", ascending=False)
            
            st.dataframe(stats_tarifas, use_container_width=True)

        if not df_st.empty:
            with st.expander("📈 MOSTRAR RENTABILIDAD ECONÓMICA"):
                st.write("**Por Evento:**")
                stats_ev = df_st.groupby("Evento").agg({"Total": "sum", "Horas Extra": "sum", "Horas Jornada": "sum"}).rename(columns={"Total": "Euros"})
                stats_ev["Horas Totales"] = stats_ev["Horas Jornada"].fillna(0) + stats_ev["Horas Extra"].fillna(0)
                st.dataframe(stats_ev[["Euros", "Horas Totales"]].sort_values("Euros", ascending=False).style.format("{:.2f}"), use_container_width=True)
                
                st.write("**Por Tarifa (Ingresos):**")
                stats_tarifas_money = df_st.groupby("Tarifa").agg({"Total": "sum"}).rename(columns={"Total": "Ingresos Totales (€)"})
                st.dataframe(stats_tarifas_money.sort_values("Ingresos Totales (€)", ascending=False).style.format("{:,.2f}"), use_container_width=True)