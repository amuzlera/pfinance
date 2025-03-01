import sqlite3
import plotly.express as px

def generate_distinct_colors(n=15):
    colors = px.colors.qualitative.Plotly
    if n <= len(colors):
        return colors[:n]
    else:
        return colors * (n // len(colors)) + colors[:n % len(colors)]


def get_data_from_db(table_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {table_name} (
            tag_name TEXT,
            keywords TEXT,
            id TEXT PRIMARY KEY
        )
    ''')
    cursor.execute(f'SELECT tag_name, keywords FROM {table_name}')
    rows = cursor.fetchall()
    conn.close()
    data_map = {}
    for row in rows:
        tag_name, keywords = row
        data_map[tag_name] = keywords.split(',')
    return data_map


SPREADSHEET_NAME = 'finanzas'
CREDENTIALS_FILE = 'client_secret.json'
DB_NAME = "movimientos.db"
TAGS_NAMES_MAP = get_data_from_db('tags')
ALIAS_NAMES_MAP = get_data_from_db('alias')
VALID_EXTENSIONS = (".xlsx", ".xls", ".pdf", ".db", ".json")
TAGS_COLORS_MAP = {tag: color for tag, color in zip(TAGS_NAMES_MAP.keys(), generate_distinct_colors(len(TAGS_NAMES_MAP)))}
TAGS_COLORS_MAP["otros"] = "gray" # por que si
