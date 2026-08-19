import urllib.parse
import pyodbc

# --- ESTA LÍNEA ES LA QUE FALTA ---
import streamlit as st
from sqlalchemy import create_engine


@st.cache_resource
def obtener_conexion():
  drivers_instalados = pyodbc.drivers()
  driver_elegido = 'SQL Server'

  for d in [
      'ODBC Driver 18 for SQL Server',
      'ODBC Driver 17 for SQL Server',
      'SQL Server Native Client 11.0',
      'SQL Server',
  ]:
    if d in drivers_instalados:
      driver_elegido = d
      break

  # Credenciales de respaldo / Somee
  server = 'CBTis139.mssql.somee.com'
  database = 'CBTis139'
  username = 'TovarLara_SQLLogin_1'
  password = '1hmetvyyiv'

  try:
    if 'db_credentials' in st.secrets:
      creds = st.secrets['db_credentials']
      server = creds.get('SERVER', server)
      database = creds.get('DATABASE', database)
      username = creds.get('UID', username)
      password = creds.get('PWD', password)
  except Exception:
    pass

  connection_string = (
      f'DRIVER={{{driver_elegido}}};'
      f'SERVER={server};'
      f'DATABASE={database};'
      f'UID={username};'
      f'PWD={password};'
      'TrustServerCertificate=yes;'
  )

  params = urllib.parse.quote_plus(connection_string)
  return create_engine(f'mssql+pyodbc:///?odbc_connect={params}')