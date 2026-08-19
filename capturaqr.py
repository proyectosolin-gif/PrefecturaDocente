from datetime import datetime, timedelta, timezone
import cv2
import numpy as np
import pandas as pd
from sqlalchemy import text
import streamlit as st
import streamlit.components.v1 as components
from Conexion import obtener_conexion

# ==============================================================================
# CONFIGURACIÓN DE PÁGINA
# ==============================================================================
st.set_page_config(
    page_title='Control de Entrada - Escáner Aula',
    page_icon='📷',
    layout='centered',
    initial_sidebar_state='collapsed',
)


# ==============================================================================
# FUNCIONES AUXILIARES
# ==============================================================================
def obtener_contexto_tiempo_mexico():
    """Retorna la fecha, hora actual (HH:MM:SS), número de día (1=Lunes) y hora en string (HH:MM)."""
    tz_mex = timezone(timedelta(hours=-6))
    ahora = datetime.now(tz_mex)
    fecha_str = ahora.strftime('%Y-%m-%d')
    hora_str = ahora.strftime('%H:%M:%S')
    hora_corta = ahora.strftime('%H:%M')
    dia_semana = ahora.isoweekday()
    return fecha_str, hora_str, hora_corta, dia_semana


def procesar_qr_imagen(foto):
    """Procesa la imagen de la cámara y extrae el valor del código QR."""
    try:
        bytes_data = foto.getvalue()
        cv2_img = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        valor_qr, _, _ = detector.detectAndDecode(cv2_img)
        return valor_qr.strip() if valor_qr else None
    except Exception:
        return None


# ==============================================================================
# APLICACIÓN PRINCIPAL CON ESCÁNER DE AULA
# ==============================================================================
def app_escanner_prefectura():
    engine = obtener_conexion()

    st.title('📷 Escáner de Aula - Prefectura')

    # ------------------------------------------------------------------
    # 1. LOGIN / AUTENTICACIÓN
    # ------------------------------------------------------------------
    if 'gestor_autenticado' not in st.session_state:
        st.session_state['gestor_autenticado'] = False
        st.session_state['idGestor'] = None
        st.session_state['nombre'] = ''

    if not st.session_state['gestor_autenticado']:
        st.subheader('🔐 Acceso a Prefectura')

        with st.form('form_login_qr'):
            pwd_input = st.text_input('🔑 Contraseña:', type='password')
            btn_ingresar = st.form_submit_button(
                '🔓 Ingresar al Sistema', type='primary', use_container_width=True
            )

            if btn_ingresar:
                if not pwd_input.strip():
                    st.warning('⚠️ Ingresa tu contraseña.')
                else:
                    try:
                        query_valida = text("""
                            SELECT idGestor, nombre 
                            FROM gestor 
                            WHERE LTRIM(RTRIM(Password)) = :pwd 
                              AND activo = 1
                        """)
                        with engine.connect() as conn:
                            res = conn.execute(
                                query_valida, {'pwd': pwd_input.strip()}
                            ).fetchone()

                            if res:
                                st.session_state['gestor_autenticado'] = True
                                st.session_state['idGestor'] = res.idGestor
                                st.session_state['nombre'] = res.nombre
                                st.rerun()
                            else:
                                st.error('❌ Contraseña incorrecta.')
                    except Exception as err_g:
                        st.error(f'⚠️ Error al conectar con la BD: {err_g}')

        st.stop()

    # ------------------------------------------------------------------
    # 2. BARRA SUPERIOR
    # ------------------------------------------------------------------
    col_info, col_logout = st.columns([3, 1])
    with col_info:
        st.info(f"👤 **Prefecto:** {st.session_state['nombre']}")
    with col_logout:
        if st.button('🔒 Salir', use_container_width=True):
            st.session_state['gestor_autenticado'] = False
            st.rerun()

    st.divider()

    # ------------------------------------------------------------------
    # 3. ESCÁNER DE CÁMARA
    # ------------------------------------------------------------------
    st.subheader('🎯 Enfoca el QR del Aula')
    foto_camara = st.camera_input('Toma la foto al código en la puerta', key='cam_qr_aula')

    if foto_camara:
        num_aula = procesar_qr_imagen(foto_camara)

        if not num_aula:
            st.warning('⚠️ No se detectó un código QR válido en la imagen. Intenta enfocarlo mejor.')
            st.stop()

        fecha_act, hora_act, hora_corta, dia_semana = obtener_contexto_tiempo_mexico()

        st.success(f'✅ **Aula detectada: {num_aula}**')

        # --------------------------------------------------------------
        # 4. BUSCAR CLASE PROGRAMADA EN ESA AULA
        # --------------------------------------------------------------
        try:
            query_aula = text("""
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
                    query_aula,
                    {
                        'aula': str(num_aula),
                        'dia_semana': dia_semana,
                        'hora_actual': hora_corta,
                    },
                ).fetchone()

            if not res_clase:
                st.info(
                    f'ℹ️ No hay clase programada en este momento en el **Aula {num_aula}** '
                    f'({hora_corta} hrs).'
                )
                st.stop()

            # --------------------------------------------------------------
            # 5. TARJETA DE INFORMACIÓN DE LA CLASE
            # --------------------------------------------------------------
            inicio_str = str(res_clase.inicio)[:5]
            fin_str = str(res_clase.fin)[:5]

            st.markdown(
                f"""
                <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #0066cc; margin-bottom: 20px;">
                    <h3 style="margin: 0; color: #1f2937;">👨‍🏫 {res_clase.maestro}</h3>
                    <p style="margin: 5px 0; font-size: 16px;"><strong>📚 Materia:</strong> {res_clase.materia}</p>
                    <p style="margin: 5px 0; font-size: 16px;"><strong>👥 Grupo:</strong> {res_clase.grupo}</p>
                    <p style="margin: 5px 0; font-size: 16px;"><strong>⏰ Horario:</strong> {inicio_str} - {fin_str} hrs</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # --------------------------------------------------------------
            # 6. BOTONES DE ACCIÓN RÁPIDA (UN SOLO TOCAR)
            # --------------------------------------------------------------
            st.subheader('⚡ Registrar Estatus:')

            col1, col2 = st.columns(2)
            col3, col4 = st.columns(2)

            id_accion_sel = None

            with col1:
                if st.button('🟢 ASISTENCIA', use_container_width=True, type='primary'):
                    id_accion_sel = 1
            with col2:
                if st.button('🔴 FALTA', use_container_width=True):
                    id_accion_sel = 2
            with col3:
                if st.button('🟡 RETARDO', use_container_width=True):
                    id_accion_sel = 3
            with col4:
                if st.button('🔵 COMISIÓN', use_container_width=True):
                    id_accion_sel = 4

            # --------------------------------------------------------------
            # 7. INSERCIÓN A BD TRAS BOTONAZO
            # --------------------------------------------------------------
            if id_accion_sel is not None:
                query_insert = text("""
                    INSERT INTO Asistencia_prefectura (idmaestro, idmateria, fecha, hora, idaccion)
                    VALUES (:idmaestro, :idmateria, :fecha, :hora, :idaccion)
                """)

                with engine.begin() as conn:
                    conn.execute(
                        query_insert,
                        {
                            'idmaestro': res_clase.idmaestro,
                            'idmateria': res_clase.idmateria,
                            'fecha': fecha_act,
                            'hora': hora_act,
                            'idaccion': id_accion_sel,
                        },
                    )

                st.balloons()
                st.success('✅ **¡Registro guardado con éxito!** Listo para la siguiente aula.')

        except Exception as err:
            st.error(f'⚠️ Error al consultar el horario: {err}')


# ==============================================================================
# EJECUCIÓN DIRECTA
# ==============================================================================
if __name__ == '__main__':
    app_escanner_prefectura()
