import pandas as pd

EXCLUDE_ROWS_CONTAINING = ["tarjeta de credito", " tarjeta credito",  "Acreditacion de haberes", "Impuesto de sellos", "ley27743", "interes por", "Impuesto ley"]

def read_excel_and_extract_table(file_path):
    df = pd.read_excel(file_path, header=None, engine='openpyxl')
    df.dropna(how='all', inplace=True)
    df.dropna(axis=1, how='all', inplace=True)
    df.reset_index(drop=True, inplace=True)

    start_row, start_col = None, None
    for i in range(df.shape[0]):
        for j in range(df.shape[1]):
            if df.iat[i, j] == 'Fecha' and df.iat[i, j + 1] == 'Sucursal origen':
                start_row, start_col = i, j
                break
        if start_row is not None:
            break

    if start_row is None or start_col is None:
        raise ValueError("Table start not found")

    table_df = df.iloc[start_row:, start_col:start_col + 7]
    expected_columns = ['Fecha', 'Sucursal de Origen', 'Descripción', 'Referencia', 'Caja de Ahorro', 'Cuenta Corriente', 'Saldo']
    table_df.columns = expected_columns
    table_df.reset_index(drop=True, inplace=True)
    table_df = table_df.drop(0).reset_index(drop=True)

    return table_df

def parse_df(df):
    df['date'] = pd.to_datetime(df['Fecha'], errors='coerce')
    df = df[~df['Descripción'].str.contains('|'.join(EXCLUDE_ROWS_CONTAINING), na=False)]
    df['monto'] = (df['Caja de Ahorro'].astype(float) * -1)
    df['id'] = df['Referencia'].astype(str)
    df['nombre'] = df['Descripción'].str.replace('Compra con tarjeta de debito ', '').str.strip()
    df.drop(columns=['Sucursal de Origen', 'Cuenta Corriente', 'Saldo', 'Caja de Ahorro', 'Referencia', 'Fecha', 'Descripción'], inplace=True)
    df = df[~df['nombre'].str.contains("Transf", na=False)]
    df['origen'] = 'movimientos-santander'

    return df


def parse_movimientos_santander(file_path):
    table_df = read_excel_and_extract_table(file_path)
    df = parse_df(table_df)
    return df

