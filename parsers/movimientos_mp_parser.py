import pdfplumber
import pandas as pd
import re

def create_lines_list_from_text(text):
    lines = text.split("\n")
    transaction, transaction_part = [], []
    for i, l in enumerate(lines):
        if 'DETALLE DE MOVIMIENTOS' in l:
            lines = lines[i+1:]
            break

    for line in lines:
        transaction_part.append(line)
        if re.search(r'\d{2}-\d{2}-\d{4}', line):
            transaction.append(transaction_part)
            transaction_part = []
    return transaction

def extract_text_from_pdf(pdf_path):
   with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text()
        return text

def create_line_dict(line):
    if any('Transferencia enviada' in p for p in line) or any('Transferencia recibida' in p for p in line):
        date = get_date(line)
        monto = get_monto(line)
        id = get_id(line)
        name = get_name(line, id)
        return {'date': date, 'monto': monto, 'id': id, 'nombre': name}

def parse_df(df):
    df['date'] = pd.to_datetime(df['date'], format='%d-%m-%Y', errors='coerce')
    df['monto'] = (df['monto'].str.replace('.', '').str.replace(',', '.'))
    df['monto'] = (df['monto'].astype(float) * -1)
    return df

def parse_transactions_from_mp(pdf_path):
    text = extract_text_from_pdf(pdf_path)
    lines = create_lines_list_from_text(text)
    lines_dict = []
    for line in lines:
        line_dict = create_line_dict(line)
        if line_dict:
            lines_dict.append(line_dict)

    return parse_df(pd.DataFrame(lines_dict))



def get_monto(part):
    for line in part:
        if '$' in line:
            return line.split('$')[-2].strip()

def get_date(part):
    for line in part:
        match = re.search(r'\d{2}-\d{2}-\d{4}', line)
        if match:
            return match.group()

def get_id(part):
    for line in part:
        match = re.search(r'\d{8,}', line)
        if match:
            return match.group()

def get_name(part, id):
    elements_to_remove = [id, ',', '.']
    for line in part:
        if 'Transferencia enviada' in line or 'Transferencia recibida' in line:
            nombre = re.split('Transferencia enviada|Transferencia recibida', line)[-1]
            nombre = nombre.split('$')[0]  # a veces queda el monto en el nombre
            for elem in elements_to_remove:
                nombre = nombre.replace(elem, '')
            return nombre.strip()

if __name__ == "__main__":
    df = parse_transactions_from_mp("files/download_250217173554.pdf")
    print(df)
