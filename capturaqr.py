from datetime import datetime, timedelta, timezone
import pandas as pd
from sqlalchemy import text
import streamlit as st
from streamlit_qrcode_scanner import qrcode_scanner
from Conexion import obtener_conexion

# ==============================================================================
# CONFIGURACIÓN DE PÁGINA
# ==============================================================================
st.set_page_config(
    page_title='Control Entrada - Prefectura',
    page_icon='📋',
    layout='centered',
    initial_sidebar_state='collapsed',
)


# ==============================================================================
# FUNCIONES AUXILIARES
# ==============================================================================
def obtener_contexto_tiempo_mexico():
    """Retorna la fecha (YYYY-MM-DD), hora actual (HH:MM:SS), número de día (1=Lunes) y hora corta (HH:MM)."""
    tz_mex = timezone(timedelta(hours=-6))  # CST (Tiempo del Centro de México)
    ahora = datetime.now(tz_mex)
    
    fecha_str = ahora.strftime('%Y-%m-%d')
    hora_str = ahora.strftime('%H:%M:%S')
    hora_corta = ahora.strftime('%H:%M')
    dia_semana = ahora.isoweekday()  # 1=Lunes, 7=Domingo
    
    return fecha_str, hora_str, hora_corta, dia_semana


DICCIONARIO_ACCIONES = {
    1: '🟢 ASISTENCIA',
    2: '🔴 FALTA',
    3: '🟡 RETARDO',
    4: '🔵 COMISIÓN'
}


# ==============================================================================
# MÓDULO 1: ESCANEO QR Y CAPTURA
# ==============================================================================
def modulo_escaneo_qr(engine):
    st.subheader('🎯 Enfoca el QR de la puerta del salón')

    # Pantalla de éxito post-guardado
    if st.session_state.get('registro_exitoso', False):
        st.success('✅ **Registro de asistencia guardado correctamente.**')
        if st.button('🔄 Escanear otra aula', type='primary', use_container_width=True):
            st.session_state['registro_exitoso'] = False
            if 'escanner_aula_auto' in st.session_state:
                del st.session_state['escanner_aula_auto']
            st.rerun()
        return

    with st.container():
        num_aula_detectado = qrcode_scanner(key='escanner_aula_auto')

    if not num_aula_detectado:
        st.info('🔍 Buscando código QR... Mantén la cámara fija frente al código.')
        return

    num_aula = str(num_aula_detectado).strip()
    st.success(f'✅ **Aula detectada: {num_aula}**')
    
    fecha_act, hora_act, hora_corta, dia_semana = obtener_contexto_tiempo_mexico()

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

        if not res_clase:
            st.warning(
                f'ℹ️ No hay clase programada en este momento ({hora_corta} hrs.) '
                f'para el día de hoy en el **Aula {num_aula}**.'
            )
            return

        # Ficha del docente
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

        # Validación anti-duplicados
        query_existe = text("""
            SELECT idaccion, hora 
            FROM asistencia_prefectura 
            WHERE idmaestro = :idmaestro 
              AND idmateria = :idmateria 
              AND fecha = :fecha
        """)

        with engine.connect() as conn:
            registro_existente = conn.execute(
                query_existe,
                {
                    'idmaestro': res_clase.idmaestro,
                    'idmateria': res_clase.idmateria,
                    'fecha': fecha_act
                }
            ).fetchone()

        if registro_existente:
            accion_nombre = DICCIONARIO_ACCIONES.get(registro_existente.idaccion, 'REGISTRADO')
            st.warning(
                f'⚠️ **Esta clase ya fue registrada hoy.**\n\n'
                f'* **Estatus registrado:** {accion_nombre}\n'
                f'* **Hora de registro:** {registro_existente.hora}'
            )
            
            if st.button('🔄 Escanear otra aula', type='primary', use_container_width=True):
                if 'escanner_aula_auto' in st.session_state:
                    del st.session_state['escanner_aula_auto']
                st.rerun()
            return

        st.session_state['datos_clase_actual'] = {
            'idmaestro': res_clase.idmaestro,
            'idmateria': res_clase.idmateria
        }

        # Botones de captura
        st.subheader('⚡ Registrar Estatus en el Aula:')

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
            if st.button('🟢 1. ASISTENCIA', use_container_width=True, type='primary'):
                id_accion_elegida = 1
        with col2:
            if st.button('🔴 2. FALTA', use_container_width=True):
                id_accion_elegida = 2
        with col3:
            if st.button('🟡 3. RETARDO', use_container_width=True):
                id_accion_elegida = 3
        with col4:
            if st.button('🔵 4. COMISIÓN', use_container_width=True):
                id_accion_elegida = 4

        # Guardado en DB
        if id_accion_elegida:
            clase = st.session_state.get('datos_clase_actual')
            
            query_insert = text("""
                INSERT INTO asistencia_prefectura (idmaestro, idmateria, fecha, hora, idaccion)
                VALUES (:idmaestro, :idmateria, :fecha, :hora, :idaccion)
            """)

            with engine.begin() as conn:
                conn.execute(
                    query_insert,
                    {
                        'idmaestro': clase['idmaestro'],
                        'idmateria': clase['idmateria'],
                        'fecha': fecha_act,
                        'hora': hora_act,
                        'idaccion': id_accion_elegida
                    },
                )

            st.balloons()
            st.session_state['registro_exitoso'] = True
            
            if 'datos_clase_actual' in st.session_state:
                del st.session_state['datos_clase_actual']
            if 'escanner_aula_auto' in st.session_state:
                del st.session_state['escanner_aula_auto']
                
            st.rerun()

    except Exception as err:
        st.error(f'⚠️ Error en la consulta o guardado: {err}')


# ==============================================================================
# MÓDULO 2: NOTAS Y OBSERVACIONES DE PREFECTURA
# ==============================================================================
def modulo_agregar_notas(engine):
    st.subheader('📝 Registro de Notas y Observaciones')
    fecha_act, _, _, _ = obtener_contexto_tiempo_mexico()

    try:
        # Consultar capturas registradas el día de hoy
        query_registros = text("""
            SELECT 
                a.id,
                a.hora,
                m.nombrecorto AS maestro,
                mat.nombre AS materia,
                a.idaccion,
                n.comentario
            FROM asistencia_prefectura a
            INNER JOIN maestros m ON a.idmaestro = m.idmaestro
            INNER JOIN materia mat ON a.idmateria = mat.idmateria
            LEFT JOIN asistencia_prefectura_notas n ON a.id = n.id
            WHERE a.fecha = :fecha
            ORDER BY a.hora DESC
        """)

        with engine.connect() as conn:
            df_registros = pd.read_sql_query(query_registros, conn, params={'fecha': fecha_act})

        if df_registros.empty:
            st.info(f'ℹ️ No hay capturas registradas el día de hoy ({fecha_act}).')
            return

        # Preparar la lista para el desplegable (Selectbox)
        df_registros['estatus_txt'] = df_registros['idaccion'].map(DICCIONARIO_ACCIONES)
        df_registros['etiqueta'] = (
            df_registros['hora'].astype(str) + " - " + 
            df_registros['maestro'] + " (" + 
            df_registros['estatus_txt'] + ")"
        )

        opciones = dict(zip(df_registros['id'], df_registros['etiqueta']))

        id_seleccionado = st.selectbox(
            '📌 Selecciona el registro para agregar/modificar nota:',
            options=list(opciones.keys()),
            format_func=lambda x: opciones[x]
        )

        # Obtener los datos del registro seleccionado
        registro = df_registros[df_registros['id'] == id_seleccionado].iloc[0]

        # Mostrar ficha de resumen del registro seleccionado
        st.markdown(f"""
            **Docente:** {registro['maestro']}  
            **Materia:** {registro['materia']}  
            **Hora de pase:** {registro['hora']} | **Estatus:** {registro['estatus_txt']}
        """)

        # Nota previa si existe
        comentario_previo = registro['comentario'] if pd.notna(registro['comentario']) else ''

        with st.form(key='form_nota'):
            nota_input = st.text_area(
                '💬 Comentario / Observación:',
                value=comentario_previo,
                placeholder='Ej. El docente andaba en baño / cambio de salón autorizado / llegó a las 8:15...'
            )
            btn_guardar_nota = st.form_submit_button('💾 Guardar Nota', type='primary', use_container_width=True)

            if btn_guardar_nota:
                if not nota_input.strip():
                    st.warning('⚠️ Escribe un comentario antes de guardar.')
                else:
                    # Inserción o actualización en la tabla asistencia_prefectura_notas
                    query_nota = text("""
                        IF EXISTS (SELECT 1 FROM asistencia_prefectura_notas WHERE id = :id)
                            UPDATE asistencia_prefectura_notas SET comentario = :comentario WHERE id = :id
                        ELSE
                            INSERT INTO asistencia_prefectura_notas (id, comentario) VALUES (:id, :comentario)
                    """)

                    with engine.begin() as conn:
                        conn.execute(query_nota, {'id': int(id_seleccionado), 'comentario': nota_input.strip()})

                    st.toast('✅ Nota guardada correctamente.', icon='📝')
                    st.success('✅ **Nota guardada/actualizada con éxito.**')
                    st.rerun()

    except Exception as err_nota:
        st.error(f'⚠️ Error al consultar o guardar la nota: {err_nota}')


# ==============================================================================
# APLICACIÓN PRINCIPAL
# ==============================================================================
def app_prefectura_auto_qr():
    engine = obtener_conexion()

    st.title('📋 Control Prefectura')

    # LOGIN GESTOR
    if 'gestor_autenticado' not in st.session_state:
        st.session_state['gestor_autenticado'] = False
        st.session_state['idGestor'] = None
        st.session_state['nombre'] = ''

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
                        st.error(f'⚠️ Error de conexión a la base de datos: {err_g}')
        st.stop()

    # BARRA SUPERIOR
    col_info, col_logout = st.columns([3, 1])
    with col_info:
        st.caption(f"👤 Prefecto: **{st.session_state['nombre']}**")
    with col_logout:
        if st.button('🔒 Salir', use_container_width=True):
            st.session_state['gestor_autenticado'] = False
            st.rerun()

    # MENÚ DE NAVEGACIÓN
    opcion_menu = st.radio(
        'Selecciona una opción:',
        ['📷 Escaneo QR', '📝 Agregar Notas'],
        horizontal=True
    )

    st.divider()

    if opcion_menu == '📷 Escaneo QR':
        modulo_escaneo_qr(engine)
    elif opcion_menu == '📝 Agregar Notas':
        modulo_agregar_notas(engine)


if __name__ == '__main__':
    app_prefectura_auto_qr()
