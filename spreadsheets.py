import pandas as pd
import json
import gspread
import plotly.express as px

from oauth2client.service_account import ServiceAccountCredentials


SPREADSHEET_NAME = 'finanzas'
CREDENTIALS_FILE = 'files/client_secret.json'


def get_data_from_spreadsheet():
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    with open(CREDENTIALS_FILE, 'r') as f:
        json_credentials = json.load(f)
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(json_credentials, scope)
    gclient = gspread.authorize(credentials)
    return gclient.open(SPREADSHEET_NAME)


def spreadsheet_to_pandas(sheet_name):
    sheet = get_data_from_spreadsheet().worksheet(sheet_name)
    data = sheet.get_all_values()
    headers = data.pop(0)
    df = pd.DataFrame(data, columns=headers).replace('', None)
    return df


def save_dataframe_to_spreadsheet(sheet_name, dataframe):
    sheet = get_data_from_spreadsheet()
    dataframe = dataframe.map(lambda x: x.strftime('%Y-%m-%d') if isinstance(x, pd.Timestamp) else x)
    dataframe = dataframe.replace([pd.NA, pd.NaT, float('inf'), float('-inf'), pd.NaT, pd.NA, float('nan')], None)

    try:
        worksheet = sheet.worksheet(sheet_name)
        renamed_sheet_name = f"{sheet_name}_backup"
        if renamed_sheet_name in [ws.title for ws in sheet.worksheets()]:
            sheet.del_worksheet(sheet.worksheet(renamed_sheet_name))
        sheet.duplicate_sheet(worksheet.id, new_sheet_name=renamed_sheet_name)
        sheet.del_worksheet(worksheet)
    except gspread.exceptions.WorksheetNotFound:
        pass

    try:
        worksheet = sheet.add_worksheet(title=sheet_name, rows=dataframe.shape[0] + 1, cols=dataframe.shape[1])
        worksheet.update([dataframe.columns.values.tolist()] + dataframe.values.tolist())
        if 'renamed_sheet_name' in locals():
            sheet.del_worksheet(sheet.worksheet(renamed_sheet_name))
    except Exception as e:
        if 'renamed_sheet_name' in locals():
            sheet.del_worksheet(worksheet)
            sheet.worksheet(renamed_sheet_name).update_title(sheet_name)
        raise e


def generate_distinct_colors(n=15):
    colors = px.colors.qualitative.Plotly
    if n <= len(colors):
        return colors[:n]
    else:
        return colors * (n // len(colors)) + colors[:n % len(colors)]


def get_data(sheet_name):
    df = spreadsheet_to_pandas(sheet_name=sheet_name)
    if df.empty:
        return {}
    data_map = df.set_index('tag_name')['keywords'].apply(lambda x: x.split(',')).to_dict()
    return data_map


def get_tags_colors_map(tags_names_map):
    tags_colors_map = {tag: color for tag, color in zip(tags_names_map.keys(), generate_distinct_colors(len(tags_names_map)))}
    tags_colors_map["otros"] = "gray"  # por que si
    return tags_colors_map


def get_tags_names_map():
    return get_data('tags')


def get_alias_names_map():
    return get_data('alias')