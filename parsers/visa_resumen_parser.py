import pdfplumber
import pandas as pd
import re
import requests
from datetime import datetime

MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def transform_usd_to_ars(data):
    usd_data = requests.get("https://dolarapi.com/v1/dolares/blue").json()
    usd_to_ars = (usd_data["compra"] + usd_data["venta"]) / 2
    data['monto'] = data.apply(lambda row: row['monto'] * usd_to_ars if "usd" in row['nombre'].lower() else row['monto'], axis=1)
    return data

def get_consumos(text):
    # Dividir el texto en líneas
    lines = text.split("\n")

    # Eliminar líneas vacías
    lines = [line for line in lines if line.strip()]
    lines = lines[::-1]
    consumos = []
    append_line = False
    for line in lines:
        if all(w in line for w in ("Tarjeta", "Total Consumos de")):
            append_line = True
            continue
        if append_line:
            if all(w in line for w in ("Fecha", "Comprobante Referencia")) or all(w in line for w in ("_______________")):
                append_line = False
            else:
                consumos.append(line)
    return consumos[::-1]


def parse_consumo(consumo):
    consumo_dict = {}
    pattern_cuotas = r'^C\.\d{2}/\d{2}$'
    parts = consumo.split()[::-1]
    parts = [p for p in parts if len(p)>1]
    consumo_dict["monto"] = float(parts.pop(0).replace(".", "").replace(",", "."))
    if re.match(pattern_cuotas, parts[0]):
        consumo_dict["cuotas"] = parts.pop(0).replace("C.", "")
    else:
        consumo_dict["cuotas"] = ""
    consumo_name = []
    for i in range(len(parts)-2):
        consumo_name.append(parts[i])
        if parts[i+1].isdigit() and len(parts[i+1])==6 and parts[i+2].isdigit() and len(parts[i+2])==2:
            consumo_dict["day"] = parts[i+2]
            consumo_dict["id"] = str(parts[i+1])
            if parts[-1].isdigit() and len(parts[-1]) == 2 and isinstance(parts[-2], str) and parts[-2][0].isupper():
                consumo_dict["month"] = parts[-2].replace(".", "")
                consumo_dict["year"] = parts[-1]
            break
            
    consumo_dict["nombre"] = ("-").join(consumo_name[::-1])
    return consumo_dict

def get_month(month):
    for i, m in enumerate(MONTHS):
        if month.lower() in m:
            return i+1

def get_consumos_from_file(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:

        consumos = []
        for page in pdf.pages:
            text = page.extract_text()
            if cons := get_consumos(text):
                consumos.extend(cons)
        return consumos[::-1]

def create_df_from_pdf(pdf_path):
    consumos_list = [parse_consumo(c) for c in get_consumos_from_file(pdf_path)]
    year, month = None, None
    for consumo in consumos_list[::-1]:
        if consumo.get("year"):
            month = get_month(consumo.get("month"))
            year = consumo.get("year")

        consumo["date"] = datetime.strptime(f"{year}-{month}-{consumo.get('day')}", "%y-%m-%d")

    df = pd.DataFrame(consumos_list)
    df['date'] = pd.to_datetime(df['date'])
    df.drop(columns=["month", "year", "day"], inplace=True)
    df["monto"] = df["monto"].astype(float)
    df = transform_usd_to_ars(df)
    return df

def chech_total_amounts():
    #TODO sumar todos los gastos y comprobar con el total a pagar, esto evidencia que no se ha omitido ningun gasto
    pass
