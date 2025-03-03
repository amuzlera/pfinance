import streamlit as st
import plotly.express as px
import pandas as pd
import os
from parsers.movimientos_mp_parser import parse_transactions_from_mp
from parsers.movimientos_santander_parser import parse_movimientos_santander
from parsers.visa_resumen_parser import create_df_from_pdf
from datetime import datetime, timedelta
from time import sleep
import hashlib
from streamlit_date_picker import date_range_picker, PickerType
from spreadsheets import get_alias_names_map, get_tags_colors_map, get_tags_names_map, save_dataframe_to_spreadsheet, spreadsheet_to_pandas, CREDENTIALS_FILE

MOVIMIENTOS = 'movimientos'
DB_NAME = "movimientos.db"
VALID_EXTENSIONS = (".xlsx", ".xls", ".pdf", ".db", ".json")


def load_db():
    df = spreadsheet_to_pandas(MOVIMIENTOS)
    if 'alias' not in df.columns:
        df['alias'] = ""

    df['date'] = pd.to_datetime(df['date'])
    df['monto'] = df['monto'].astype(float)
    df['alias'] = df['alias'].fillna('')
    st.session_state['movimientos'] = order_df(df)


def concat_by_id(df1, df2):
    '''preserves df1 data'''
    if df1.empty:
        return df2
    if df2.empty:
        return df1
    new_data = df2[~df2['id'].isin(df1['id'])]
    return pd.concat([df1, new_data])


def check_for_credentials(uploaded_files):
    if uploaded_files:
        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name
            os.makedirs("files", exist_ok=True)
            if file_name.endswith(".json"):
                with open(CREDENTIALS_FILE, "wb") as f:
                    f.write(uploaded_file.getbuffer())


def parse_from_files(df, uploaded_files):
    if uploaded_files:
        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name
            os.makedirs("files", exist_ok=True)
            
            file_path = os.path.join('files', file_name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            if file_name.endswith(".db"):
                with open(file_path, "rb") as f:
                    db_data = f.read()
                with open(DB_NAME, "wb") as f:
                    f.write(db_data)
                
            elif MOVIMIENTOS in file_name and file_name.endswith(".xlsx"):
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
    save_dataframe_to_spreadsheet(MOVIMIENTOS, data)
    # Eliminar archivos subidos después de procesarlos
    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name
        file_path = os.path.join('files', file_name)
        if os.path.exists(file_path):
            os.remove(file_path)


def order_df(df):
    first_columns = ['date', 'nombre', 'monto', 'cuotas', 'alias']
    remaining_columns = [col for col in df.columns if col not in first_columns]
    column_order = first_columns + remaining_columns
    df = df.reindex(columns=column_order)
    return df


def color_rows(row):
    return ['background-color: {}'.format(st.session_state.tags_colors_map[row['categoria']])] * len(row)


def add_tags(tags_map, col_name, default_tag='otros'):
    data = st.session_state.movimientos
    for tag, keywords in tags_map.items():
        for keyword in keywords:
            if tag == "ignore":
                data.loc[data['nombre'].str.lower() == keyword.lower(), col_name] = tag
            else:
                data.loc[data['nombre'].str.contains(keyword, case=False), col_name] = tag
    data[col_name] = data[col_name].fillna(default_tag)


def generate_id(row):
    row_str = f"{row['date']}{row['nombre']}{row['categoria']}{row['alias']}"
    return hashlib.md5(row_str.encode()).hexdigest()


def create_month_range_picker():
    default_start, default_end = datetime.now() - timedelta(days=30), datetime.now()
    refresh_value = timedelta(days=30)
    refresh_buttons = [{
                        'button_name': 'Refresh Last 1 Month',
                        'refresh_value': refresh_value
                    }]
    date_range_string = date_range_picker(picker_type=PickerType.month,
                                        start=default_start, end=default_end,
                                        key='month_range_picker',
                                        refresh_buttons=refresh_buttons)
    if date_range_string:
        st.session_state.start_datetime = date_range_string[0]
        st.session_state.end_datetime = date_range_string[1]


def create_custom_range_picker():
    default_start, default_end = datetime.now() - timedelta(days=1), datetime.now()        
    date_range_string = date_range_picker(picker_type=PickerType.date,
                                        start=default_start, end=default_end,
                                        key='date_range_picker')

    if date_range_string:
        st.session_state.start_datetime = date_range_string[0]
        st.session_state.end_datetime = date_range_string[1]


def filter_data_by_date():
    data = st.session_state.movimientos
    if 'start_datetime' in st.session_state and 'end_datetime' in st.session_state:
        start_date = st.session_state.start_datetime
        end_date = st.session_state.end_datetime
        st.session_state.movimientos = data[(data['date'] >= start_date) & (data['date'] <= end_date)]


def add_alias_form():
    st.write("### Alias")
    blank_row = {"alias_name": ["Insert name"], "keyword": "Insert keyword"}
    if 'inserting_row_alias' not in st.session_state:
        st.session_state.inserting_row_alias = False

    if st.button("Agregar alias"):
        st.session_state.inserting_row_alias = True

    if st.session_state.inserting_row_alias:
        st.session_state.row_to_insert_alias = st.data_editor(
            pd.DataFrame(blank_row, columns=['alias_name', 'keyword']),
            use_container_width=True,
            hide_index=True,
            column_config={
                "alias": st.column_config.SelectboxColumn(
                    "alias",
                    required=True,
                ),
                "str": st.column_config.SelectboxColumn(
                    "str",
                    required=True,
                ),
            },
        )

    if st.button("Confirmar alias"):
        if st.session_state.row_to_insert_alias is not blank_row:
            row = st.session_state.row_to_insert_alias
            tag_name = row['alias_name'][0].strip()
            keywords = row['keyword'].item().strip().split(',')
            if tag_name not in st.session_state.alias_names_map:
                st.session_state.alias_names_map[tag_name] = []
            st.session_state.alias_names_map[tag_name].extend(keywords)
            alias_name_map = [{'id': i, 'tag_name': k, 'keywords': ','.join(set(v))} for i, (k, v) in enumerate(st.session_state.alias_names_map.items())]
            try:
                save_dataframe_to_spreadsheet(sheet_name='alias', dataframe=pd.DataFrame(alias_name_map))
                st.success(f"Etiqueta '{tag_name}' agregada con éxito.")
                del st.session_state['inserting_row']
            except Exception as e:
                st.error(f"Error al guardar la etiqueta: {e}")


def add_tags_form():
    st.write("### Tags")
    blank_row = {"tag_name": ["Insert name"], "keywords": "Insert keywords"}
    if 'inserting_row' not in st.session_state:
        st.session_state.inserting_row = False

    if st.button("Agregar tags"):
        st.session_state.inserting_row = True

    if st.session_state.inserting_row:
        st.session_state.row_to_insert = st.data_editor(
            pd.DataFrame(blank_row, columns=['tag_name', 'keywords']),
            use_container_width=True,
            hide_index=True,
            column_config={
                "tags": st.column_config.SelectboxColumn(
                    "tags",
                    required=True,
                ),
                "query_str": st.column_config.SelectboxColumn(
                    "query_str",
                    required=True,
                ),
            },
        )

    if st.button("Confirmar"):
        if st.session_state.row_to_insert is not blank_row:
            row = st.session_state.row_to_insert
            tag_name = row['tag_name'][0].strip()
            keywords = row['keywords'].item().strip().split(',')
            if tag_name not in st.session_state.tags_names_map:
                st.session_state.tags_names_map[tag_name] = []
            st.session_state.tags_names_map[tag_name].extend(keywords)
            tags_name_map = [{'id': i, 'tag_name': k, 'keywords': ','.join(set(v))} for i, (k, v) in enumerate(st.session_state.tags_names_map.items())]
            try:
                save_dataframe_to_spreadsheet(sheet_name='tags', dataframe=pd.DataFrame(tags_name_map))
                st.success(f"Etiqueta '{tag_name}' agregada con éxito.")
                del st.session_state['inserting_row']
            except Exception as e:
                st.error(f"Error al guardar la etiqueta: {e}")


def search_expense_panel():
    st.subheader("Buscar Gasto")

    search_option = st.selectbox("Buscar por", ["ID", "Nombre", "tags", "alias"])
    table_map = {
        "ID": MOVIMIENTOS,
        "Nombre": MOVIMIENTOS,
        "tags": "tags",
        "alias": "alias"
    }
    search_query = st.text_input("Ingrese el valor de búsqueda")

    if st.button("Buscar"):
        result_df = spreadsheet_to_pandas(table_map[search_option])
        if search_option == "ID":
            result_df = result_df[result_df['id'] == search_query]
        elif search_option == "Nombre":
            result_df = result_df[result_df['nombre'].str.contains(search_query, case=False)]
        elif search_option == "tags" or search_option == "alias":
            result_df = result_df[result_df['tag_name'] == search_query]
        
        st.session_state['search_results'] = result_df.to_dict('records'), table_map[search_option]

    if 'search_results' in st.session_state:
        result_df_saved, table = st.session_state['search_results']
        result_df = pd.DataFrame(result_df_saved)
        if not result_df.empty:
            st.write("Resultados de la búsqueda:")
            for index, row in result_df.iterrows():
                col1, col2 = st.columns([6, 1])
                with col1:
                    st.write(row.to_frame().T)
                with col2:
                    if st.button("Eliminar", key=f"delete_{row['id']}"):
                        delete_expense(row['id'], table, result_df)
                        with col1:
                            st.success(f"Gasto con ID {row['id']} eliminado.")
                        st.session_state['search_results'] = result_df[result_df['id'] != row['id']].to_dict('records'), table
                        sleep(2)
                        st.rerun()
        else:
            st.write("No se encontraron resultados.")


def delete_expense(expense_id, table, df):
    df = df[df['id'] != expense_id]
    save_dataframe_to_spreadsheet(table, df)


def create_category_buttons():
    categories = ["todos"] + list(st.session_state.tags_names_map.keys())
    categories.remove("ignore")
    categories.append("otros")
    cols = st.columns(len(categories))

    for i, category in enumerate(categories):
        if cols[i].button(category):
            st.session_state.selected_category = category


def filter_ignore_tags():
    data = st.session_state.movimientos
    st.session_state.movimientos = data[data['categoria'] != 'ignore']


def pfinance_app():
    create_custom_range_picker()
    create_month_range_picker()
    if uploaded_files := st.file_uploader("Subir archivos", type=VALID_EXTENSIONS, accept_multiple_files=True):
        check_for_credentials(uploaded_files)
        load_data_from_files(uploaded_files)

    if os.path.exists(CREDENTIALS_FILE):
        st.session_state.tags_names_map = get_tags_names_map()
        st.session_state.alias_names_map = get_alias_names_map()
        st.session_state.tags_colors_map = get_tags_colors_map(st.session_state.tags_names_map)
    else:
        st.error("Por favor, suba el archivo de credenciales de Google Sheets.")
        return

    st.title("Categorias")

    if 'selected_category' not in st.session_state:
        st.session_state.selected_category = "todos"
        return

    load_db()
    add_tags(tags_map=st.session_state.tags_names_map, col_name='categoria')
    add_tags(tags_map=st.session_state.alias_names_map, col_name='alias', default_tag="")
    filter_data_by_date()
    filter_ignore_tags()
    create_category_buttons()
    
    data = st.session_state.movimientos
    st.write(f'### Distribucion de gastos entre: {st.session_state.start_datetime} y {st.session_state.end_datetime}')
    if st.session_state.selected_category == "todos":
        grouped_data = data.groupby('categoria')['monto'].sum().reset_index()
        grouped_data['color'] = grouped_data['categoria'].map(st.session_state.tags_colors_map)
        filtered_data = grouped_data
        filter_column = 'categoria'
        total_amount = filtered_data['monto'].sum()
        filtered_data_all_positive = filtered_data.copy()
        filtered_data_all_positive['monto'] = filtered_data_all_positive['monto'].abs()
        fig = px.pie(filtered_data_all_positive, names=filter_column, values='monto', color='categoria', color_discrete_map=st.session_state.tags_colors_map, hole=0.4)
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
        filtered_data_all_positive = filtered_data.copy()
        filtered_data_all_positive['monto'] = filtered_data_all_positive['monto'].abs()
        fig = px.pie(filtered_data_all_positive, names=filter_column, values='monto', color='nombre', color_discrete_map=name_color_map, hole=0.4)
        fig.add_annotation(text=f"${total_amount:,.0f}", x=0.5, y=0.5, font_size=20, showarrow=False)
        selected_point = st.plotly_chart(fig, use_container_width=True)
        styled_df = filtered_data.style.apply(lambda row: ['background-color: {}'.format(row['color'])] * len(row), axis=1)

    styled_df = styled_df.format({'monto': lambda x: f"${x:,.0f}"})
    styled_df.data['date'] = pd.to_datetime(styled_df.data['date']).dt.date
    width = 200 + len(styled_df.data.columns) * 150
    st.dataframe(styled_df, hide_index=True, column_config={"color": None, "id": None, "label": None, 'raw': None}, width=width)

    add_tags_form()
    add_alias_form()
    search_expense_panel()


if __name__ == "__main__":
    pfinance_app()
