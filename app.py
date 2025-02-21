import sqlite3
import streamlit as st
import plotly.express as px
import pandas as pd
import os
from parsers.movimientos_mp_parser import parse_transactions_from_mp
from parsers.movimientos_santander_parser import parse_movimientos_santander
from parsers.visa_resumen_parser import create_df_from_pdf, parse_consumo
import requests
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import json
import calendar
from datetime import datetime
from time import sleep
import hashlib

DB_NAME = "movimientos.db"

if os.path.exists("tags.json"): 
    with open("tags.json", "r") as f:
        TAGS_NAMES_MAP = json.load(f)
else:
    TAGS_NAMES_MAP = {}

if os.path.exists("alias.json"):
    with open("alias.json", "r") as f:
        ALIAS_NAMES_MAP = json.load(f)
else:
    ALIAS_NAMES_MAP = {}

VALID_EXTENSIONS = (".xlsx", ".xls", ".pdf")

def generate_distinct_colors(n=15):
    colors = px.colors.qualitative.Plotly
    if n <= len(colors):
        return colors[:n]
    else:
        return colors * (n // len(colors)) + colors[:n % len(colors)]

TAGS_COLORS_MAP = {tag: color for tag, color in zip(TAGS_NAMES_MAP.keys(), generate_distinct_colors(len(TAGS_NAMES_MAP)))}
TAGS_COLORS_MAP["otros"] = "gray" # por que si
DATA_PATH = "files/edited_data.csv"

def save_to_db(df):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movimientos (
            date TEXT,
            monto REAL,
            id TEXT,
            nombre TEXT,
            categoria TEXT,
            alias TEXT,
            cuotas TEXT
                   
        )
    ''')

    existing_df = pd.read_sql_query('SELECT * FROM movimientos', conn)
    new_df = df[~df['id'].isin(existing_df['id'])]
    new_df.to_sql('movimientos', conn, if_exists='append', index=False)
    conn.commit()
    conn.close()

def read_from_db():
    if not os.path.exists(DB_NAME):
        return pd.DataFrame(columns=['date', 'monto', 'id', 'nombre', 'categoria', 'alias'])
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query('SELECT * FROM movimientos', conn)
    conn.close()
    return df

def load_db():
    df = read_from_db()
    if 'alias' not in df.columns:
        df['alias'] = ""

    print(df['monto'])
    df['date'] = pd.to_datetime(df['date'])
    df['monto'] = df['monto'].astype(float)
    df['alias'] = df['alias'].fillna('')
    return order_df(df)

def concat_by_id(df1, df2):
    '''preserves df1 data'''
    if df1.empty:
        return df2
    if df2.empty:
        return df1
    new_data = df2[~df2['id'].isin(df1['id'])]
    return pd.concat([df1, new_data])

def parse_from_files(df, uploaded_files):
    if uploaded_files:
        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name
            os.makedirs("files", exist_ok=True)
            file_path = os.path.join('files', file_name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            if "movimientos" in file_name:
                df = concat_by_id(df, parse_movimientos_santander(file_path))
            elif "Resumen de tarjeta de crédito" in file_name:
                df = concat_by_id(df, create_df_from_pdf(file_path))
            elif "download" in file_name:
                df = concat_by_id(df, parse_transactions_from_mp(file_path))
    return df

def load_data_from_files(uploaded_files):
    old_data = load_db()
    data = parse_from_files(old_data, uploaded_files)
    data['id'] = data['id'].astype(str)
    save_to_db(data)

def order_df(df):
    first_columns = ['date', 'alias', 'nombre', 'cuotas', 'monto']
    remaining_columns = [col for col in df.columns if col not in first_columns]
    column_order = first_columns + remaining_columns
    df = df.reindex(columns=column_order)
    return df

def color_rows(row):
    return ['background-color: {}'.format(TAGS_COLORS_MAP[row['categoria']])] * len(row)

def add_tags(data, tags_map, col_name, default_tag='otros'):
    for tag, keywords in tags_map.items():
        for keyword in keywords:
            data.loc[data['nombre'].str.contains(keyword, case=False), col_name] = tag
    data[col_name] = data[col_name].fillna(default_tag)

    return data

def transform_usd_to_ars(data):
    usd_data = requests.get("https://dolarapi.com/v1/dolares/blue").json()
    usd_to_ars = (usd_data["compra"] + usd_data["venta"]) / 2
    data['monto'] = data.apply(lambda row: row['monto'] * usd_to_ars if "usd" in row['nombre'].lower() else row['monto'], axis=1)
    return data

def generate_id(row):
    row_str = f"{row['date']}{row['nombre']}{row['categoria']}{row['alias']}"
    return hashlib.md5(row_str.encode()).hexdigest()

def add_expense_form():
    st.subheader("Agregar nuevo gasto")

    date = st.date_input("Fecha", value=datetime.now()).strftime('%Y-%m-%d 00:00:00')
    nombre = st.text_input("Nombre")
    categoria = st.selectbox("Categoría", options=list(TAGS_NAMES_MAP.keys()))
    alias = st.text_input("Alias")
    monto = st.text_input("monto")

    if st.button("Agregar gasto"):
        if date and nombre and categoria:
            new_row = {
                'date': date,
                'nombre': nombre,
                'categoria': categoria,
                'alias': alias,
                'monto': monto.replace('.', '').replace(',', '.')
            }
            new_row['id'] = generate_id(new_row)

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO movimientos (date, nombre, categoria, alias, monto, id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (new_row['date'], new_row['nombre'], new_row['categoria'], new_row['alias'], new_row['monto'], new_row['id']))
            conn.commit()
            conn.close()

            st.success("Gasto agregado con éxito.")
            st.rerun()
        else:
            st.error("Por favor, complete todos los campos.")

def draw_editable_table(df):
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(editable=True)
    grid_options = gb.build()

    response = AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.MODEL_CHANGED,
        fit_columns_on_grid_load=True
    )

    st.session_state.editable_data = response['data']

def edit_data(df):
    st.subheader("Editar Datos")
    col1, col2 = st.columns([1, 1])
                
    with col1:
        if st.button("Mostrar/Ocultar tabla editable"):
            if 'show_editable_table' not in st.session_state:
                st.session_state.show_editable_table = True
            else:
                st.session_state.show_editable_table = not st.session_state.show_editable_table

    if st.session_state.get('show_editable_table', False):
        draw_editable_table(df)

    with col2:
        if st.button("Guardar cambios"):
            if 'editable_data' in st.session_state:
                data = load_db()
                modified_df = st.session_state.editable_data
                modified_df['date'] = pd.to_datetime(modified_df['date'])
                modified_data = concat_by_id(modified_df, data)
                save_to_db(modified_data)
                st.rerun()




def create_date_selector():
    if 'month_index' not in st.session_state:
        st.session_state.month_index = datetime.now().month - 1
    if 'year' not in st.session_state:
        st.session_state.year = datetime.now().year

    # Function to cycle months
    def cycle_months(direction):
        if direction == 'prev':
            st.session_state.month_index = (st.session_state.month_index - 1) % 12
            if st.session_state.month_index == 11:
                st.session_state.year -= 1
        elif direction == 'next':
            st.session_state.month_index = (st.session_state.month_index + 1) % 12
            if st.session_state.month_index == 0:
                st.session_state.year += 1
        st.rerun()

    # Function to modify year
    def modify_year(direction):
        if direction == 'prev':
            st.session_state.year -= 1
        elif direction == 'next':
            st.session_state.year += 1
        st.rerun()

    # Display month and year carousel
    prev_month_button, month_label, next_month_button, prev_year_button, year_label, next_year_button = st.columns([1, 2, 1, 1, 1, 1])
    with prev_month_button:
        if st.button("←", key="prev_month"):
            cycle_months('prev')
    with month_label:
        st.write(f"### {calendar.month_name[st.session_state.month_index + 1]}")
    with next_month_button:
        if st.button("→", key="next_month"):
            cycle_months('next')
    with prev_year_button:
        if st.button("←", key="prev_year"):
            modify_year('prev')
    with year_label:
        st.write(f"### {st.session_state.year}")
    with next_year_button:
        if st.button("→", key="next_year"):
            modify_year('next')

def filter_data_by_date(data):
    return data[(data['date'].dt.month == st.session_state.month_index + 1) & (data['date'].dt.year == st.session_state.year)]

def pfinance_app():
    if uploaded_files := st.file_uploader("Subir archivos", type=VALID_EXTENSIONS, accept_multiple_files=True):
        load_data_from_files(uploaded_files)

    st.title("Gastos")
    create_date_selector()

    if 'selected_category' not in st.session_state:
        st.session_state.selected_category = "todos"

    data = load_db()
    data = add_tags(data, tags_map=TAGS_NAMES_MAP, col_name='categoria')
    data = add_tags(data, tags_map=ALIAS_NAMES_MAP, col_name='alias', default_tag="")
    data = filter_data_by_date(data)

    # Create buttons
    columns = st.columns(len(TAGS_NAMES_MAP) + 1)
    if columns[0].button("todos"):
        st.session_state.selected_category = "todos"

    for i, category in enumerate(TAGS_NAMES_MAP.keys(), start=1):
        if columns[i].button(category):
            st.session_state.selected_category = category


    if st.session_state.selected_category == "todos":
        grouped_data = data.groupby('categoria')['monto'].sum().reset_index()
        grouped_data['color'] = grouped_data['categoria'].map(TAGS_COLORS_MAP)
        filtered_data = grouped_data
        filter_column = 'categoria'
        total_amount = filtered_data['monto'].sum()
        fig = px.pie(filtered_data, names=filter_column, values='monto', title='Distribución de Gastos', color='categoria', color_discrete_map=TAGS_COLORS_MAP, hole=0.4)
        fig.add_annotation(text=f"${total_amount:,.0f}", x=0.5, y=0.5, font_size=20, showarrow=False)
        selected_point = st.plotly_chart(fig, use_container_width=True)
        styled_df = data.style.apply(color_rows, axis=1)

    else:
        filtered_data = data[data['categoria'] == st.session_state.selected_category]
        unique_names = filtered_data['nombre'].unique()
        unique_colors = px.colors.qualitative.Plotly
        name_color_map = {name: unique_colors[i % len(unique_colors)] for i, name in enumerate(unique_names)}
        filtered_data['label'] = filtered_data.apply(lambda row: row['alias'] if row['alias'] else row['nombre'], axis=1)
        filter_column = 'label'
        filtered_data['color'] = filtered_data['nombre'].map(name_color_map)
        total_amount = filtered_data['monto'].sum()
        fig = px.pie(filtered_data, names=filter_column, values='monto', title='Distribución de Gastos', color='nombre', color_discrete_map=name_color_map, hole=0.4)
        fig.add_annotation(text=f"${total_amount:,.0f}", x=0.5, y=0.5, font_size=20, showarrow=False)
        selected_point = st.plotly_chart(fig, use_container_width=True)
        styled_df = filtered_data.style.apply(lambda row: ['background-color: {}'.format(row['color'])] * len(row), axis=1)

    styled_df = styled_df.format({'monto': lambda x: f"${x:,.0f}"})
    styled_df.data['date'] = pd.to_datetime(styled_df.data['date']).dt.date

    height = len(styled_df.data) * 45
    width = 200 + len(styled_df.data.columns) * 150
    st.dataframe(styled_df, hide_index=True, column_config={"color": None, "id": None, "label": None, 'raw': None}, width=width)


    edit_data(styled_df.data)
    add_tags_form()
    add_expense_form()
    search_expense_panel()



def add_tags_form():
    st.subheader("Agregar nueva etiqueta o alias")

    # Buttons to select between tags and alias
    col1, col2 = st.columns(2)
    with col1:
        if st.button("tags"):
            st.session_state.selection = "tags"
    with col2:
        if st.button("alias"):
            st.session_state.selection = "alias"

    # Default to tags if not selected
    if 'selection' not in st.session_state:
        st.session_state.selection = "tags"

    if st.session_state.selection == "tags":
        tag_name = st.selectbox("Nombre de la etiqueta", options=list(TAGS_NAMES_MAP.keys()) + ["Agregar nueva etiqueta"])
        
        if tag_name == "Agregar nueva etiqueta":
            tag_name = st.text_input("Ingrese el nombre de la nueva etiqueta")
            TAGS_NAMES_MAP[tag_name] = []
        keywords = st.text_area("Palabras clave (separadas por comas)")

        if st.button("Agregar etiqueta"):
            if tag_name and keywords:
                new_keywords = [kw.strip() for kw in keywords.split(",")]
                TAGS_NAMES_MAP[tag_name].extend(new_keywords)

                with open("tags.json", "w") as f:
                    json.dump(TAGS_NAMES_MAP, f, indent=4)

                st.success(f"Etiqueta '{tag_name}' agregada con éxito.")
            else:
                st.error("Por favor, complete todos los campos.")
    elif st.session_state.selection == "alias":
        alias_name = st.text_input("Nombre alias")
        keywords = st.text_input("query para tagear alias segun nombre")

        if st.button("Agregar alias"):
            if alias_name and keywords:
                if alias_name not in ALIAS_NAMES_MAP:
                    ALIAS_NAMES_MAP[alias_name] = []
                new_keywords = [kw.strip() for kw in keywords.split(",")]
                ALIAS_NAMES_MAP[alias_name].extend(new_keywords)

                with open("alias.json", "w") as f:
                    json.dump(ALIAS_NAMES_MAP, f, indent=4)

                st.success(f"Alias '{alias_name}' agregado con éxito.")
            else:
                st.error("Por favor, complete todos los campos.")

def search_expense_panel():
    st.subheader("Buscar Gasto")

    search_option = st.selectbox("Buscar por", ["ID", "Nombre"])
    search_query = st.text_input("Ingrese el valor de búsqueda")

    if st.button("Buscar"):
        if search_option == "ID":
            query = f"SELECT * FROM movimientos WHERE id = '{search_query}'"
        else:
            query = f"SELECT * FROM movimientos WHERE nombre LIKE '%{search_query}%'"

        conn = sqlite3.connect(DB_NAME)
        result_df = pd.read_sql_query(query, conn)
        conn.close()

        st.session_state['search_results'] = result_df.to_dict('records')

    if 'search_results' in st.session_state:
        result_df = pd.DataFrame(st.session_state['search_results'])
        if not result_df.empty:
            st.write("Resultados de la búsqueda:")
            for index, row in result_df.iterrows():
                col1, col2 = st.columns([6, 1])
                with col1:
                    st.write(row.to_frame().T)
                with col2:
                    if st.button("Eliminar", key=f"delete_{row['id']}"):
                        delete_expense(row['id'])
                        with col1:
                            st.success(f"Gasto con ID {row['id']} eliminado.")
                        st.session_state['search_results'] = result_df[result_df['id'] != row['id']].to_dict('records')
                        sleep(2)
                        st.rerun()
        else:
            st.write("No se encontraron resultados.")

def delete_expense(expense_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM movimientos WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    pfinance_app()
