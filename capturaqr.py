from datetime import datetime, timedelta, timezone
import pandas as pd
from sqlalchemy import text
import streamlit as st
import streamlit.components.v1 as components
from streamlit_qrcode_scanner import qrcode_scanner  # <-- Volvemos al escáner automático
from Conexion import obtener_conexion

# ==============================================================================
# CONFIGURACIÓN DE PÁGINA
# ==============================================================================
st.set_page_config(
    page_title='Control Entrada - Auto QR',
    page_icon='📷',
    layout='centered',
    initial_sidebar_state='collapsed',
)


# ==============================================================================
# FUNCIONES AUXILIARES
# ==============================================================================
def obtener_contexto_tiempo_mexico():
    """Retorna la fecha, hora actual (HH:MM:SS), número de día (1=Lunes) y hora corta (HH:MM)."""
    # Ajustar zona horaria si el servidor está en UTC (Streamlit Cloud)
    tz_mex = timezone(timedelta(hours=-6)) # Tiempo del Centro de México (CST)
    ahora = datetime.now(tz_mex)
    
    fecha_str = ahora.strftime('%Y-%m-%d')
    hora_str = ahora.strftime('%H:%M:%S')
    hora_corta = ahora.strftime('%H:%M')
    dia_semana = ahora.isoweekday() # 1=Lunes, 7=Domingo
    
    # Para pruebas, si estás fuera de horario, puedes forzar un día/hora aquí:
    # dia_semana = 1  # Forzar Lunes
    # hora_corta = '09:00' # Forzar hora de clase
    
    return fecha_str, hora_str, hora_corta, dia_semana


# ==============================================================================
# APLICACIÓN PRINCIPAL - ESCANEO AUTOMÁTICO
# ==============================================================================
def app_prefectura_auto_qr():
    engine = obtener_conexion()

    st.title('📷 Revisión de Aula (Auto QR)')

    # ------------------------------------------------------------------
    # 1. AUTENTICACIÓN (LOGIN GESTOR)
    # ------------------------------------------------------------------
    if 'gestor_autenticado' not in st.session_state:
        st.session_state['gestor_autenticado'] = False
        st.session_state['idGestor'] = None
        st.session_state['nombre'] = ''

    # PANTALLA DE SALIDA LIMPIA DESPUÉS DE GUARDAR
    if st.session_state.get('registro_exitoso', False):
        st.success('✅ **Registro de asistencia guardado correctamente.**')
        if st.button('🔄 Escanear otra aula', type='primary', use_container_width=True):
            st.session_state['registro_exitoso'] = False
            # Limpiar el valor del escáner para forzar una nueva lectura
            if 'escanner_aula_auto' in st.session_state:
                del st.session_state['escanner_aula_auto']
            st.rerun()
        st.stop()

    # FORMULARIO DE ACCESO
    if not st.session_state['gestor_autenticado']:
        st.subheader('🔐 Acceso a Prefectura')
        with st.form('form_login_auto_qr'):
            pwd_input = st.text_input('🔑 Contraseña:', type='password')
            btn_ingresar = st.form_submit_button('🔓 Ingresar', type='primary', use_container_width=True)

            if btn_ingresar:
                if not pwd_input.strip():
                    st.warning('⚠️ Ingresa tu contraseña.')
                else:
                    try:
                        query_valida = text("""
                            SELECT idGestor, nombre 
                            FROM gestor 
                            WHERE LTRIM(RTRIM(Password)) = :pwd AND activo = 1
                        """)
                        with engine.connect() as conn:
                            res = conn.execute(query_valida, {'pwd': pwd_input.strip()}).fetchone()
                            if res:
                                st.session_state['gestor_autenticado'] = True
                                st.session_state['idGestor'] = res.idGestor
                                st.session_state['nombre'] = res.nombre
                                st.rerun()
                            else:
                                st.error('❌ Contraseña incorrecta.')
                    except Exception as err_g:
                        st.error(f'⚠️ Error al conectar con la base de datos: {err_g}')
        st.stop()

    # ------------------------------------------------------------------
    # 2. BARRA SUPERIOR
    # ------------------------------------------------------------------
    col_info, col_logout = st.columns([3, 1])
    with col_info:
        st.caption(f"👤 Prefecto: {st.session_state['nombre']}")
    with col_logout:
        if st.button('🔒 Salir', use_container_width=True):
            st.session_state['gestor_autenticado'] = False
            st.rerun()

    st.divider()

    # ------------------------------------------------------------------
    # 3. ESCÁNER AUTOMÁTICO (SOLO ENFOCAR)
    # ------------------------------------------------------------------
    st.subheader('🎯 Enfoca el QR de la puerta')
    
    # Este componente abre la cámara e identifica el QR sin botones
    with st.container():
        num_aula_detectado = qrcode_scanner(key='escanner_aula_auto')

    # Si no se ha detectado nada, mostramos mensaje de espera
    if not num_aula_detectado:
        st.info('🔍 Buscando código QR... Mantén la cámara fija frente a la etiqueta.')
        st.stop()

    # ------------------------------------------------------------------
    # 4. PROCESAR AULA DETECTADA
    # ------------------------------------------------------------------
    # Limpiamos el valor por seguridad (espacios en blanco)
    num_aula = str(num_aula_detectado).strip()
    
    st.success(f'✅ **Aula detectada: {num_aula}**')
    
    fecha_act, hora_act, hora_corta, dia_semana = obtener_contexto_tiempo_mexico()

    # --------------------------------------------------------------
    # 5. CONSULTAR CLASE ACTUAL EN ESA AULA
    # --------------------------------------------------------------
    try:
        query_clase = text("""
            SELECT 
                hg.idhorario,
                m.idmaestro,
                mat.idmateria,
                m.nombrecorto AS maestro,
                mat.nombre AS materia,
                hg.grupo,
                hg.inicio,
                hg.fin
            FROM Horario_grupo hg
            INNER JOIN maestros m ON hg.idmaestro = m.idmaestro
            INNER JOIN materia mat ON hg.idmateria = mat.idmateria
            WHERE CAST(hg.aula AS VARCHAR) = :aula
              AND hg.dia_semana = :dia_semana
              AND :hora_actual >= hg.inicio 
              AND :hora_actual <= hg.fin
        """)

        with engine.connect() as conn:
            res_clase = conn.execute(
                query_clase,
                {
                    'aula': num_aula,
                    'dia_semana': dia_semana,
                    'hora_actual': hora_corta,
                },
            ).fetchone()

        # Si no hay clase programada en esa hora
        if not res_clase:
            st.warning(
                f'ℹ️ No hay clase programada en este momento ({hora_corta} hrs.) '
                f'para el día de hoy en el **Aula {num_aula}**.'
            )
            st.stop()

        # --------------------------------------------------------------
        # 6. TARJETA DE INFORMACIÓN DEL DOCENTE
        # --------------------------------------------------------------
        h_ini = str(res_clase.inicio)[:5]
        h_fin = str(res_clase.fin)[:5]

        st.markdown(
            f"""
            <div style="background-color: #f0f2f6; padding: 18px; border-radius: 12px; border-left: 6px solid #1d4ed8; margin: 15px 0;">
                <h2 style="margin: 0; color: #1e3a8a; font-size: 22px;">👨‍🏫 {res_clase.maestro}</h2>
                <p style="margin: 8px 0 0 0; font-size: 17px; color: #1f2937;"><strong>📚 Materia:</strong> {res_clase.materia}</p>
                <p style="margin: 4px 0; font-size: 16px; color: #4b5563;"><strong>👥 Grupo:</strong> {res_clase.grupo} | ⏰ <strong>Hora:</strong> {h_ini} - {h_fin}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # --------------------------------------------------------------
        # 7. BOTONES DE ACCIÓN RÁPIDA (UN SOLO TOCAR)
        # --------------------------------------------------------------
        st.subheader('⚡ Registrar Estatus Actual:')
        
        # Guardamos datos de la clase en session_state para la inserción
        st.session_state['datos_clase_actual'] = {
            'idmaestro': res_clase.idmaestro,
            'idmateria': res_clase.idmateria,
            'idhorario': res_clase.idhorario
        }

        # Estilo CSS para botones grandes y de un toque
        st.markdown("""
            <style>
                div.stButton > button {
                    height: 55px;
                    font-size: 18px !important;
                    font-weight: bold !important;
                    margin-bottom: 10px;
                }
            </style>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        col3, col4 = st.columns(2)

        id_accion_elegida = None

        with col1:
            if st.button('🟢 ASISTENCIA', use_container_width=True, type='primary'):
                id_accion_elegida = 1
        with col2:
            if st.button('🔴 FALTA', use_container_width=True):
                id_accion_elegida = 2
        with col3:
            if st.button('🟡 RETARDO', use_container_width=True):
                id_accion_elegida = 3
        with col4:
            if st.button('🔵 COMISIÓN', use_container_width=True):
                id_accion_elegida = 4

        # --------------------------------------------------------------
        # 8. INSERCIÓN A BASE DE DATOS Y CONFIRMACIÓN
        # --------------------------------------------------------------
        if id_accion_elegida:
            # Obtener datos guardados en session_state
            clase = st.session_state.get('datos_clase_actual')
            
            query_insert = text("""
                INSERT INTO Asistencia_prefectura (idmaestro, idmateria, fecha, hora, idaccion, idgestor, idhorario)
                VALUES (:idmaestro, :idmateria, :fecha, :hora, :idaccion, :idgestor, :idhorario)
            """)

            with engine.begin() as conn:
                conn.execute(
                    query_insert,
                    {
                        'idmaestro': clase['idmaestro'],
                        'idmateria': clase['idmateria'],
                        'fecha': fecha_act,
                        'hora': hora_act,
                        'idaccion': id_accion_elegida,
                        'idgestor': st.session_state['idGestor'],
                        'idhorario': clase['idhorario'] # Se agregó idhorario para mayor trazabilidad
                    },
                )

            # Efectos visuales y cambio de estado
            st.balloons()
            st.session_state['registro_exitoso'] = True
            
            # Limpiar variables temporales
            if 'datos_clase_actual' in st.session_state:
                del st.session_state['datos_clase_actual']
            if 'escanner_aula_auto' in st.session_state:
                del st.session_state['escanner_aula_auto']
                
            st.rerun()

    except Exception as err:
        st.error(f'⚠️ Error al consultar el horario o guardar registro: {err}')


# ==============================================================================
# EJECUCIÓN DIRECTA
# ==============================================================================
if __name__ == '__main__':
    app_prefectura_auto_qr()
