import streamlit as st
from supabase import create_client, Client
import pandas as pd
import bcrypt
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit_cookies_manager as cookies_manager
from informes import obtener_word_tierras, obtener_word_aislamientos

st.set_page_config(page_title="Gestión de Centros", page_icon="🏢")

cookies = cookies_manager.CookieManager()

# Conexión Supabase
url = st.secrets["supabase"]["SUPABASE_URL"]
key = st.secrets["supabase"]["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# Obtener hora en horario español
def ahora_es():
    return datetime.now(ZoneInfo("Europe/Madrid"))

# Login
def verificar_login(username, password):
    try:
        response = supabase.table('usuarios').select('*').eq('username', username).execute()
        if not response.data:
            return False
        usuario = response.data[0]
        return bcrypt.checkpw(password.encode(), usuario['password'].encode())
    except Exception as e:
        st.error(f"Error de autenticación: {str(e)}")
        return False

def obtener_centros():
    return pd.DataFrame(supabase.table('centros').select('*').execute().data)

def obtener_cuadros(centro_id):
    return pd.DataFrame(supabase.table('cuadros').select('*').eq('centro_id', centro_id).execute().data)

def agregar_cuadro(centro_id, tipo, nombre, numero, usuario, tierra, aislamiento):
    data = {
        "centro_id": centro_id,
        "tipo": tipo,
        "nombre": nombre,
        "numero": numero,
        "tierra_ohmnios": tierra,
        "aislamiento_megaohmnios": aislamiento,
        "ultimo_usuario": usuario,
        "ultima_modificacion": ahora_es().isoformat()
    }
    return supabase.table('cuadros').insert(data).execute()

def guardar_estado_sesion(username, pagina, centro_id):
    ahora = ahora_es().isoformat()
    data = {
        "username": username,
        "pagina": pagina,
        "centro_seleccionado": centro_id,
        "timestamp": ahora
    }
    supabase.table("sesiones").upsert(data, on_conflict=["username"]).execute()
    cookies["usuario"] = username
    cookies["pagina"] = pagina
    cookies["centro_seleccionado"] = centro_id
    cookies["timestamp"] = ahora
    cookies.save()

def cerrar_sesion():
    supabase.table("sesiones").delete().eq("username", st.session_state["usuario"]).execute()
    cookies.clear()
    st.session_state.clear()
    cookies["logout"] = True
    cookies.save()
    st.session_state["logout_forzado"] = True
    st.rerun()

def actualizar_tierra(cuadro_id, tierra, usuario):
    supabase.table('cuadros').update({
        "tierra_ohmnios": tierra,
        "ultimo_usuario": usuario,
        "ultima_modificacion": ahora_es().isoformat()
    }).eq('id', cuadro_id).execute()

def actualizar_aislamiento(cuadro_id, aislamiento, usuario):
    supabase.table('cuadros').update({
        "aislamiento_megaohmnios": aislamiento,
        "ultimo_usuario": usuario,
        "ultima_modificacion": ahora_es().isoformat()
    }).eq('id', cuadro_id).execute()

# PANTALLAS
def pantalla_login():
    st.title("Inicio de Sesión")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if verificar_login(username, password):
            st.session_state.update({"autenticado": True, "usuario": username, "pagina": "inicio"})
            guardar_estado_sesion(username, "inicio", None)
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos")

def pantalla_inicio():
    st.title("Lista de Centros")
    if st.button("Cerrar sesión"):
        cerrar_sesion()
        st.rerun()

    provincia = st.selectbox("Filtrar por provincia", ["Todas", "Alicante", "Valencia", "Castellón"])
    busqueda = st.text_input("Buscar centro")
    df = obtener_centros()
    if provincia != "Todas":
        df = df[df["provincia"] == provincia]
    if busqueda:
        df = df[df["nombre"].str.contains(busqueda, case=False, na=False)]

    for _, row in df.iterrows():
        if st.button(f"Gestionar {row['nombre']}"):
            st.session_state.update({
                "centro_seleccionado": row["id"],
                "nombre_centro": row["nombre"],
                "pagina": "gestion"
            })
            guardar_estado_sesion(st.session_state["usuario"], "gestion", row["id"])
            st.rerun()

def eliminar_cuadro(cuadro_id):
    supabase.table('cuadros').delete().eq('id', cuadro_id).execute()

def pantalla_gestion():
    centro_id = st.session_state["centro_seleccionado"]
    nomb = st.session_state["nombre_centro"]
    st.title(f"Gestión del Centro {nomb}")

    if st.button("Cerrar sesión"):
        cerrar_sesion()
        st.rerun()
    
    if st.button("Volver al listado"):
        st.session_state["pagina"] = "inicio"
        st.session_state["centro_seleccionado"] = None
        guardar_estado_sesion(st.session_state["usuario"], st.session_state["pagina"], st.session_state["centro_seleccionado"])
        st.rerun()

    df_cuadros = obtener_cuadros(centro_id)

    # Verificar si hay cuadros y si la columna 'ultima_modificacion' existe
    if not df_cuadros.empty and "ultima_modificacion" in df_cuadros.columns:
        # Filtramos filas que tengan fecha válida
        df_filtrado = df_cuadros.dropna(subset=["ultima_modificacion"])
        if not df_filtrado.empty:
            # Convertimos la fecha a zona horaria de Madrid
            df_filtrado["ultima_modificacion"] = pd.to_datetime(
                df_filtrado["ultima_modificacion"], utc=True
            ).dt.tz_convert("Europe/Madrid")
            cuadro_reciente = df_filtrado.sort_values("ultima_modificacion", ascending=False).iloc[0]
            fecha_hora_mod = cuadro_reciente["ultima_modificacion"].strftime("%d/%m/%Y a las %H:%M")
            st.write(f"Última modificación por: {cuadro_reciente['ultimo_usuario']} el: {fecha_hora_mod}")
    else:
        st.write("Aún no hay cuadros creados.")

    for _, row in df_cuadros.iterrows():
        cuadro_id = row['id']
        st.subheader(f"Cuadro: {row['nombre']}")
        with st.expander("Editar cuadro"):
            nuevo_tipo = st.selectbox("Tipo", ["CGBT", "CS", "CT", "CC"], index=["CGBT", "CS", "CT", "CC"].index(row["tipo"]), key=f"edit_tipo_{cuadro_id}")
            nuevo_numero = st.number_input("Número", value=row["numero"], min_value=0, max_value=100, key=f"edit_numero_{cuadro_id}")
            nuevo_nombre = st.text_input("Nombre", value=row["nombre"], key=f"edit_nombre_{cuadro_id}")
            
            if st.button("Guardar cambios", key=f"guardar_edicion_{cuadro_id}"):
                actualizar_datos = {
                    "tipo": nuevo_tipo,
                    "numero": nuevo_numero,
                    "nombre": nuevo_nombre,
                    "ultimo_usuario": st.session_state["usuario"],
                    "ultima_modificacion": datetime.now(ZoneInfo("Europe/Madrid")).isoformat()
                }
                supabase.table('cuadros').update(actualizar_datos).eq('id', cuadro_id).execute()
                st.success("Cuadro actualizado correctamente.")
                st.rerun()

        tierra = st.number_input(
            "Medición de Tierra (Ω)",
            value=row["tierra_ohmnios"] or 0.0,
            key=f"tierra_input_{cuadro_id}",
            min_value=0.0,
            step=1.0,
            on_change=lambda: actualizar_tierra(cuadro_id, st.session_state[f"tierra_input_{cuadro_id}"], st.session_state["usuario"])
        )
        aislamiento = st.number_input(
            "Medición de Aislamiento (MΩ)",
            value=row["aislamiento_megaohmnios"] or 0.0,
            key=f"aislamiento_input_{cuadro_id}",
            min_value=0.0,
            step=1.0,
            on_change=lambda: actualizar_aislamiento(cuadro_id, st.session_state[f"aislamiento_input_{cuadro_id}"], st.session_state["usuario"])
        )

        col1, col2 = st.columns([1, 1])

        with col2:
            with st.expander("Eliminar cuadro", expanded=False):
                st.warning("Esta acción no se puede deshacer.")
                if st.button("Confirmar eliminación", key=f"eliminar_btn_{cuadro_id}"):
                    eliminar_cuadro(cuadro_id)
                    st.success(f"Cuadro '{row['nombre']}' eliminado.")
                    st.rerun()
    
    st.subheader("Añadir Cuadro Eléctrico")
    tipo = st.selectbox("Tipo", ["CGBT", "CS", "CT", "CC"], key="tipo")
    numero = st.number_input("Número del cuadro", key="numero", min_value=0, max_value=100, step=1) 
    nombre = st.text_input("Nombre del cuadro", key="nombre")
    col1, col2 = st.columns([1, 1])
    with col1:
        tierra = st.number_input(
            "Medición de Tierra (Ω)",
            value=0.0,
            key=f"new_tierra_input",
            min_value=0.0,
            step=1.0,
        )
    with col2:
        aislamiento = st.number_input(
            "Medición de Aislamiento (MΩ)",
            value=0.0,
            key=f"new_aislamiento_input",
            min_value=0.0,
            step=1.0,
        )

    usuario = st.session_state['usuario']
    if st.button("Añadir Cuadro"):
        if nombre:
            try:
                agregar_cuadro(centro_id, tipo, nombre, numero, usuario, tierra, aislamiento)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        else:
            st.warning("Debes completar todos los campos")
    
    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("Generar Informe Tierras"):
            obtener_word_tierras(centro_id)

    with col2:
        if st.button("Generar Informe Aislamientos"):
            obtener_word_aislamientos(centro_id)
# FLUJO PRINCIPAL
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False

if "logout_forzado" in st.session_state:
    st.session_state.pop("logout_forzado")
else:
    if not cookies.ready():
        st.info("Cargando sesión... refresque la página si tarda mucho.")
        st.stop()
    if not st.session_state['autenticado']:
        username = cookies.get("usuario")
        if username:
            resp = supabase.table("sesiones").select("*").eq("username", username).execute()
            if resp.data:
                sesion = resp.data[0]
                ahora = ahora_es()
                ultima = datetime.fromisoformat(sesion["timestamp"]).astimezone(ZoneInfo("Europe/Madrid"))
                if (ahora - ultima).total_seconds() <= 8 * 3600:
                    st.session_state.update({
                        "autenticado": True,
                        "usuario": username,
                        "pagina": sesion["pagina"],
                        "centro_seleccionado": sesion["centro_seleccionado"]
                    })
                    if sesion["centro_seleccionado"]:
                        centro = supabase.table("centros").select("*").eq("id", sesion["centro_seleccionado"]).execute().data[0]
                        st.session_state["nombre_centro"] = centro["nombre"]

if not st.session_state['autenticado']:
    pantalla_login()
elif st.session_state["pagina"] == "inicio":
    pantalla_inicio()
elif st.session_state["pagina"] == "gestion":
    pantalla_gestion()  
