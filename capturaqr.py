import streamlit as st
from streamlit_qrcode_scanner import qrcode_scanner

st.set_page_config(
    page_title='Prueba Escáner QR',
    page_icon='📷',
    layout='centered'
)

st.title('📷 Prueba de Escaneo de Aula')
st.caption('Apunta la cámara del dispositivo al código QR de la puerta.')

# Componente que activa la cámara y lee el QR en tiempo real
codigo_detectado = qrcode_scanner(key='escanner_aula')

if codigo_detectado:
    st.success(f'✅ ¡Código QR detectado con éxito!')
    st.metric(label='Número de Aula:', value=f'Aula {codigo_detectado}')
else:
    st.info('🔍 Buscando código QR... Por favor, enfoca la etiqueta.')