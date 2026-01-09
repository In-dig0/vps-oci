# Standard library imports
import os
import logging
from dotenv import load_dotenv
import argparse
import sys
import io
import time
from datetime import datetime

# Third-party imports
import pandas as pd
#from pkg_resources import safe_name
import xmltodict
from zoneinfo import ZoneInfo
from nicegui import ui, app, nicegui
import defusedxml.ElementTree as ET
import hashlib

# Logger setup
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
MAX_LINES_PER_INVOICE = int(os.getenv('MAX_LINES_PER_INVOICE', 10000))
MAX_XML_DEPTH = int(os.getenv('MAX_XML_DEPTH', 50))
MAX_FILE_SIZE_MB = float(os.getenv('MAX_FILE_SIZE_MB', 1))
APP_NAME = os.getenv('APP_NAME', 'XML_CONVERTER').upper()
APP_CODE = os.getenv('APP_CODE', 'XIC').upper()
APP_VERSION = os.getenv('APP_VERSION', '0.0.1')
PROCESSING_TIMEOUT = int(os.getenv('PROCESSING_TIMEOUT', 30))
LOG_FILE = f'logs/{APP_CODE.lower()}_usage.log'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
TIMEZONE = ZoneInfo("Europe/Rome")

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='XML Invoice Converter - NiceGUI',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--host', type=str, default='0.0.0.0', 
                       help='Server host address')
    parser.add_argument('--port', type=int, default=8502, 
                       help='Server port number')
    parser.add_argument('--reload', action='store_true', 
                       help='Enable auto-reload on code changes')
    parser.add_argument('--show', action='store_true', 
                       help='Open browser automatically on startup')
    return parser.parse_args()

# --- FUNZIONI DI SUPPORTO PER L'UPLOAD ---
    
def get_xml_depth(element, level=1):
    """Calcola la profondità dell'albero XML (Punto 6)."""
    if not list(element):
        return level
    return max(get_xml_depth(child, level + 1) for child in element)


async def handle_upload(e, upload_widget, rows_label, notification_box, notification_icon, notification_label):
    """
    Esegue l'upload del file, valida il file e restituisce i dati.
    Ritorna: (successo: bool, contenuto: bytes, nome: str, righe: int)
    """

    # 1. INIZIALIZZAZIONE SICURA (Punto di partenza critico)
    safe_filename = "file_sconosciuto.xml"
    file_hash = "n/a"
    num_items = 0

    try:
        # 2. RECUPERO NOME FILE REALE
        raw_name = None
        
        if hasattr(e, 'name'):
            raw_name = e.name
        elif hasattr(e, 'filename'):
            raw_name = e.filename
        else:
            buffer_obj = getattr(e, 'content', getattr(e, 'file', None))
            if buffer_obj:
                raw_name = getattr(buffer_obj, 'filename', getattr(buffer_obj, 'name', None))

        if raw_name:
            safe_filename = os.path.basename(str(raw_name))
        
        # Accesso sicuro al buffer
        buffer = getattr(e, 'content', getattr(e, 'file', None))
        if not buffer:
            logger.error(f"UPLOAD FAILED | Nome rilevato: {safe_filename} | Buffer not found")
            
            notification_icon.props('name=error color=negative')
            notification_label.set_text("Errore: impossibile leggere il contenuto del file")
            notification_box.classes('border-red-500 bg-red-100 dark:bg-red-900/40 opacity-100', remove='opacity-0')
            notification_box.set_visibility(True)
            
            return False, None, safe_filename, num_items

        # Lettura contenuto e calcolo Hash
        byte_content = await buffer.read()
        file_hash = hashlib.sha256(byte_content).hexdigest()

        # Parsing Protetto (Anti-XML Bomb)
        root = ET.fromstring(byte_content)
        detail_lines = root.findall('.//{*}DettaglioLinee')
        num_items = len(detail_lines)

        # Controllo Tag (gestisce p:FatturaElettronica)
        if 'FatturaElettronica' not in root.tag:
            error_msg = f'Invalid structure -> missing tag FatturaElettronica'
            
            notification_icon.props('name=error color=negative')
            notification_label.set_text(error_msg)
            notification_box.classes('border-red-500 bg-red-100 dark:bg-red-900/40 opacity-100', remove='opacity-0')
            notification_box.set_visibility(True)
            
            logger.warning(f"UPLOAD REJECTED | File: {safe_filename} | Hash: {file_hash} | Cause: {error_msg}")
            return False, None, safe_filename, num_items

        # Verifica Profondità dell'XML
        depth = get_xml_depth(root)
        if depth > MAX_XML_DEPTH:
            error_msg = f'XML too deep -> {depth} levels (Max {MAX_XML_DEPTH})'
            
            notification_icon.props('name=error color=negative')
            notification_label.set_text(error_msg)
            notification_box.classes('border-red-500 bg-red-100 dark:bg-red-900/40 opacity-100', remove='opacity-0')
            notification_box.set_visibility(True)
            
            logger.warning(f"UPLOAD REJECTED | File: {safe_filename} | Hash: {file_hash} | Cause: {error_msg}")
            return False, None, safe_filename, num_items

        # CONTROLLO RISPETTO AL LIMITE
        if num_items > MAX_LINES_PER_INVOICE:
            error_msg = f'Limit exceeded -> {num_items} lines (Max {MAX_LINES_PER_INVOICE})'
            
            notification_icon.props('name=error color=negative')
            notification_label.set_text(error_msg)
            notification_box.classes('border-red-500 bg-red-100 dark:bg-red-900/40 opacity-100', remove='opacity-0')
            notification_box.set_visibility(True)
            
            logger.warning(f"UPLOAD REJECTED | File: {safe_filename} | Hash: {file_hash} | Cause: {error_msg}")
            return False, None, safe_filename, num_items

        # Se num_items è 0, facciamo un controllo di sicurezza
        if num_items == 0:
            notification_icon.props('name=warning color=warning')
            notification_label.set_text('Attention: No <DettaglioLinee> tag found in the file')
            notification_box.classes('border-yellow-500 bg-yellow-100 dark:bg-yellow-900/30', 
                         remove='border-green-500 bg-green-50 border-red-500 bg-red-50')
            notification_box.set_visibility(True)

        # SUCCESSO: AGGIORNAMENTO UI E LOG
        rows_label.set_text(f'File: {safe_filename} ({num_items} lines)')
        
        notification_icon.props('name=check_circle color=positive')
        notification_label.set_text(f'File "{safe_filename}" validated successfully! ({num_items} lines)')
        notification_box.classes('border-green-500 bg-green-100 dark:bg-green-900/40 opacity-100', 
                                 remove='opacity-0 border-red-500 bg-red-100 border-yellow-500 bg-yellow-100')
        notification_box.set_visibility(True)
        
        logger.info(f"UPLOAD SUCCESS | File: {safe_filename} | Hash: {file_hash} | Lines: {num_items}")
        return True, byte_content, safe_filename, num_items
    
    except Exception as ex:
        error_msg = f"{type(ex).__name__}: {str(ex)}"
        
        notification_icon.props('name=error color=negative')
        notification_label.set_text(f'Technical error: {str(ex)}')
        notification_box.classes('border-red-500 bg-red-100 dark:bg-red-900/40 opacity-100', remove='opacity-0')
        notification_box.set_visibility(True)       
        logger.error(f"UPLOAD ERROR: {safe_filename} | Detail: {error_msg}")
        return False, None, safe_filename, 0


# --- FUNZIONI DI PARSING XML ---

DEFAULT_VALUE = "**"
DEFAULT_NUMERIC = "0"

def extract_nested_value(data, path, default=None):
    """Estrae valore da struttura dictionary annidata."""
    current = data
    try:
        for key in path:
            current = current[key]
        return str(current) if current is not None else (default or DEFAULT_VALUE)
    except (KeyError, TypeError):
        return default or DEFAULT_VALUE


def extract_invoice_data(xml_dict, root_tag):
    """Estrae dati di testata fattura."""
    header = xml_dict[root_tag]["FatturaElettronicaHeader"]
    body = xml_dict[root_tag]["FatturaElettronicaBody"]
    general_data = body["DatiGenerali"]["DatiGeneraliDocumento"]
    
    invoice_data = {
        'supplier_vat': extract_nested_value(
            header, ["CedentePrestatore", "DatiAnagrafici", "IdFiscaleIVA", "IdCodice"]
        ),
        'supplier_name': extract_nested_value(
            header, ["CedentePrestatore", "DatiAnagrafici", "Anagrafica", "Denominazione"]
        ),
        'doc_number': extract_nested_value(general_data, ["Numero"]),
        'doc_date': extract_nested_value(general_data, ["Data"]),
        'doc_amount': extract_nested_value(
            general_data, ["ImportoTotaleDocumento"], DEFAULT_NUMERIC
        )
    }
    
    return invoice_data


def process_attachments(attachments, manage_energy, previous_values):
    """Processa gli allegati di riga."""
    result = {
        'drawing_number': DEFAULT_VALUE,
        'order_number': DEFAULT_VALUE,
        'ddt_number': DEFAULT_VALUE,
        'intent': DEFAULT_VALUE
    }
    
    if not attachments:
        return apply_energy_management(result, manage_energy, previous_values)
    
    if isinstance(attachments, dict):
        attachments = [attachments]
    
    mapping = {
        "DISEGNO": 'drawing_number',
        "COMMESSA": 'order_number',
        "N01": 'ddt_number',
        "INTENTO": 'intent'
    }
    
    for attachment in attachments:
        if isinstance(attachment, dict) and "TipoDato" in attachment:
            tipo = attachment["TipoDato"]
            if tipo in mapping:
                field = mapping[tipo]
                result[field] = attachment.get("RiferimentoTesto", DEFAULT_VALUE)
    
    return apply_energy_management(result, manage_energy, previous_values)


def apply_energy_management(result, manage_energy, previous_values):
    """Applica logica energy contribution management."""
    if manage_energy:
        for field in ['drawing_number', 'order_number', 'ddt_number']:
            if result[field] == DEFAULT_VALUE:
                result[field] = previous_values[field]
    
    for field in ['drawing_number', 'order_number', 'ddt_number']:
        if result[field] != DEFAULT_VALUE:
            previous_values[field] = result[field]
    
    return result


def parse_line(line, manage_energy, previous_values):
    """Analizza singola riga fattura."""
    article_code = DEFAULT_VALUE
    if isinstance(line.get("CodiceArticolo"), dict):
        article_code = line["CodiceArticolo"].get("CodiceValore", DEFAULT_VALUE)
    
    attachments = line.get("AltriDatiGestionali", [])
    attachment_data = process_attachments(attachments, manage_energy, previous_values)
    
    line_data = {
        'line_number': str(line.get("NumeroLinea", DEFAULT_VALUE)),
        'article_code': article_code,
        'description': line.get("Descrizione", DEFAULT_VALUE),
        'quantity': str(line.get("Quantita", DEFAULT_NUMERIC)),
        'unit': line.get("UnitaMisura", DEFAULT_VALUE),
        'unit_price': str(line.get("PrezzoUnitario", DEFAULT_NUMERIC)),
        'total_price': str(line.get("PrezzoTotale", DEFAULT_NUMERIC)),
        'vat_code': str(line.get("AliquotaIVA", DEFAULT_NUMERIC)),
        'drawing_number': attachment_data['drawing_number'],
        'order_number': attachment_data['order_number'],
        'ddt_number': attachment_data['ddt_number'],
        'intent': attachment_data['intent']
    }
    
    return line_data


def extract_lines_data(xml_dict, root_tag, manage_energy):
    """Estrae dati righe fattura."""
    lines = xml_dict[root_tag]["FatturaElettronicaBody"]["DatiBeniServizi"]["DettaglioLinee"]
    
    if not isinstance(lines, list):
        lines = [lines]
    
    previous_values = {
        'drawing_number': DEFAULT_VALUE,
        'order_number': DEFAULT_VALUE,
        'ddt_number': DEFAULT_VALUE
    }
    
    result = []
    for line in lines:
        line_data = parse_line(line, manage_energy, previous_values)
        result.append(line_data)
    
    return result


def create_dataframe(invoice_data, lines_data, filename):
    """Crea DataFrame dai dati parsati."""
    if not lines_data:
        return pd.DataFrame()
    
    num_lines = len(lines_data)
    
    data = {
        'T_filein': [filename] * num_lines,
        'T_piva_mitt': [invoice_data['supplier_vat']] * num_lines,
        'T_ragsoc_mitt': [invoice_data['supplier_name']] * num_lines,
        'T_num_doc': [invoice_data['doc_number']] * num_lines,
        'T_data_doc': [invoice_data['doc_date']] * num_lines,
        'T_importo_doc': [invoice_data['doc_amount']] * num_lines,
        'P_nr_linea': [line['line_number'] for line in lines_data],
        'P_codart': [line['article_code'] for line in lines_data],
        'P_desc_linea': [line['description'] for line in lines_data],
        'P_qta': [line['quantity'] for line in lines_data],
        'P_um': [line['unit'] for line in lines_data],
        'P_przunit': [line['unit_price'] for line in lines_data],
        'P_prezzo_tot': [line['total_price'] for line in lines_data],
        'P_codiva': [line['vat_code'] for line in lines_data],
        'P_nrdisegno': [line['drawing_number'] for line in lines_data],
        'P_commessa': [line['order_number'] for line in lines_data],
        'P_nrddt': [line['ddt_number'] for line in lines_data],
        'P_intento': [line['intent'] for line in lines_data]
    }
    
    df = pd.DataFrame(data)
    
    # Conversione colonne numeriche
    numeric_cols = ['T_importo_doc', 'P_qta', 'P_przunit', 'P_prezzo_tot']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    return df


def apply_grouping(df):
    """Applica grouping al DataFrame."""
    grouping_fields = [
        "T_filein", "T_num_doc", "T_data_doc",
        "P_nrdisegno", "P_commessa", "P_nrddt", "P_intento"
    ]
    
    df_grouped = df.groupby(grouping_fields, as_index=False).agg({
        "P_prezzo_tot": "sum"
    })
    df_grouped = df_grouped.rename(columns={"P_prezzo_tot": "P_importo"})
    df_grouped["P_importo"] = df_grouped["P_importo"].round(2)
    
    return df_grouped


def convert_xml_to_df(xml_content, filename, use_grouping, manage_energy):
    """
    Logica di conversione da XML a DataFrame Pandas.
    Viene chiamata al click sul bottone RUN.
    """
    logger.info(f"Avvio conversione | Grouping: {use_grouping} | Energy: {manage_energy}")
    
    try:
        # Parse XML con xmltodict
        xml_dict = xmltodict.parse(xml_content.decode('utf-8'))
        root_tag = next(iter(xml_dict))
        
        # Estrazione dati testata
        invoice_data = extract_invoice_data(xml_dict, root_tag)
        
        # Estrazione dati righe
        lines_data = extract_lines_data(xml_dict, root_tag, manage_energy)
        
        # Creazione DataFrame
        df = create_dataframe(invoice_data, lines_data, filename)
        
        # Applicazione grouping se richiesto
        if use_grouping and not df.empty:
            df = apply_grouping(df)
        
        logger.info(f"Conversion completed | Lines: {len(df)}")
        return df
        
    except Exception as e:
        logger.error(f"Error during conversion: {e}", exc_info=True)
        raise


def create_excel_buffer(df, sheet_name="Invoice"):
    """Crea file Excel in memory buffer."""
    buffer = io.BytesIO()
    
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]
        
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })
        
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
    
    buffer.seek(0)
    return buffer.getvalue()


def log_usage(filename, status="COMPLETED", message="", action="PROCESS", file_hash=""):
    """Log application usage."""
    try:
        timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        
        log_line = (
            f"{timestamp} | {APP_NAME} | {APP_CODE} | {action} | "
            f"{filename} | {status} | {message} | {file_hash}\n"
        )
        
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_line)
        
    except Exception as e:
        logger.error(f"Error logging usage: {e}", exc_info=True)

# Funzione per ottenere la data di modifica del file
def get_last_update():
    """Ottiene la data di ultima modifica del file principale."""
    try:
        file_path = 'src/xml_invoice_converter.py'
        if os.path.exists(file_path):
            timestamp = os.path.getmtime(file_path)
            return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
        return 'N/A'
    except Exception as e:
        logger.error(f"Error getting last update date: {e}")
        return 'N/A'

if __name__ in {"__main__", "__mp_main__"}:

    # Mappa stringhe → livelli logging
    LOG_LEVELS = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }

    log_level = LOG_LEVELS.get(LOG_LEVEL, logging.INFO)

    # Configurazione logging
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(LOG_FILE),
                logging.StreamHandler()
            ]
        )

  
    args = parse_arguments()
    
    # Log di startup
    if not hasattr(app.storage.general, '_startup_logged'):
        logger.info(f"Starting {APP_NAME} on host {args.host}:{args.port}")
        logger.info(f'Environment: {"Docker" if os.path.exists("/.dockerenv") else "Local"}')
        app.storage.general._startup_logged = True

    # Detect environment
    in_docker = os.path.exists('/.dockerenv') or os.getenv('DOCKER_CONTAINER') == 'true'
    env_str = "Docker" if in_docker else "Local"
    env_badge = "🐳 Docker" if in_docker else "💻 Local"

# 1. Configurazione Dark Mode e Transizioni CSS
    dark_mode = ui.dark_mode()
    
    ui.add_head_html('''
        <style>
            * {
                transition: background-color 0.5s ease, color 0.2s ease;
            }
        </style>
    ''')

    def update_body_style(is_dark):
        color = '#121212' if is_dark else '#e8e9ea'
        ui.query('body').style(f'background-color: {color}')
        ui.query('.q-notification').classes('dark:text-white')

    # Inizializzazione sfondo
    update_body_style(dark_mode.value)

    # 2. Controlli fuori dalla card (alto a destra)
    with ui.row().classes('w-full justify-end p-4'):
        with ui.row().classes('items-center gap-2 p-2 rounded-lg'):
            ui.icon('dark_mode').bind_visibility_from(dark_mode, 'value', backward=lambda v: not v)
            ui.icon('light_mode').bind_visibility_from(dark_mode, 'value')
            ui.switch(value=dark_mode.value, 
                      on_change=lambda e: (dark_mode.set_value(e.value), update_body_style(e.value))
            ).props('color=primary')

    # 3. Card principale
    mycol1 = '#2980B9'  # Custom color
    mycol2 = '#888B8A'  # Custom color
    #with ui.card().classes('w-full max-w-4xl mx-auto shadow-lg border border-gray-200'):
    with ui.card().classes('w-full max-w-4xl mx-auto shadow-lg border border-gray-200 mt-1'):
        ui.label(f'📄 {APP_NAME}').classes('text-3xl font-bold').style(f'color: {mycol1}')
        ui.label('A secure web application for converting Italian B2B XML invoices (FatturaPA format) to Excel spreadsheets.').classes('text-lg text-yellow-600')
        ui.separator()
        
        with ui.row().classes('gap-6 items-center'):
            with ui.row().classes('items-center gap-1'):
                ui.icon('info', size='sm').classes('text-gray-500')
                ui.label(f'Version: {APP_VERSION}').classes('text-sm font-bold')
            
            with ui.row().classes('items-center gap-1'):
                ui.icon('update', size='sm').classes('text-gray-500')
                ui.label(f'Updated: {get_last_update()}').classes('text-sm')

        # --- SEZIONE FRAMEWORK PULITA ---
        with ui.expansion('📦 Framework versions').classes('w-full border-t border-gray-100 mt-2'):
            with ui.column().classes('gap-3 p-4'):
                label_style = 'font-weight: bold; text-decoration: underline; font-family: monospace; display: inline-block;'

                with ui.row().classes('items-center gap-3'):
                    try:
                        nicegui_version = nicegui.__version__
                    except:
                        nicegui_version = 'installed'
                    # Icona NiceGUI locale con sfondo bianco
                    with ui.element('div').classes('p-1 bg-white rounded'):
                        ui.image('assets/icons/nicegui_logo.png').classes('w-5 h-5')
                    ui.html(f'<span style="{label_style}">NiceGUI</span>: {nicegui_version}', sanitize=False)

                with ui.row().classes('items-center gap-3'):
                    # Icona Python locale
                    ui.image('assets/icons/python_logo.svg').classes('w-6 h-6')
                    ui.html(f'<span style="{label_style}">Python</span>: {sys.version.split()[0]}', sanitize=False)

                with ui.row().classes('items-center gap-3'):
                    # Icona Pandas locale
                    ui.image('assets/icons/pandas_logo.svg').classes('w-6 h-6')
                    ui.html(f'<span style="{label_style}">Pandas</span>: {pd.__version__}', sanitize=False)

                with ui.row().classes('items-center gap-3'):
                    ui.icon('public', color='blue').classes('text-2xl')
                    ui.html(f'<span style="{label_style}">Environment</span>: {env_badge}', sanitize=False)
                
                # Link GitHub con icona locale
                ui.separator().classes('my-2')
                with ui.row().classes('items-center gap-3'):
                    ui.image('assets/icons/github_logo.svg').classes('w-6 h-6 dark:invert')
                    ui.link(
                        'View on GitHub', 
                        'https://github.com/In-dig0/vps-oci/tree/main/docker/xml_invoice_converter_app',
                        new_tab=True
                    ).classes('text-blue-600 hover:text-blue-800 dark:text-blue-400 font-bold underline')
    
    # --- STATO DELL'APPLICAZIONE ---
    app_state = {
        'xml_content': None, 
        'xml_filename': None,
        'dataframe': None,
        'file_hash': None
    }

    # --- UI: CARD UPLOAD ---
    with ui.card().classes('w-full max-w-4xl mx-auto shadow-lg mt-4 border border-gray-200'):
        with ui.row().classes('items-center gap-2'):
            ui.label('📥UPLOAD B2B XML INVOICE').classes('text-xl font-bold').style(f'color: {mycol1}')

            with ui.icon('info', color='grey').classes('cursor-help text-lg'):
                ui.tooltip(f'''
                    CONSTRAINTS FOR UPLOADING XML FILES:
                    - Only .xml files
                    - Size: max {MAX_FILE_SIZE_MB} MB
                    - Document lines: max {MAX_LINES_PER_INVOICE}
                    - XML depth: max {MAX_XML_DEPTH} levels
                ''').classes('bg-slate-800 text-white p-2 shadow-xl')

        rows_label = ui.label('File: none (0 rows)').classes('text-sm italic text-gray-500 mb-2')

        upload_widget = ui.upload(
            label='Seleziona XML',
            auto_upload=True,
            max_files=1,
            max_file_size=MAX_FILE_SIZE_MB * 1024 * 1024,
        ).props('accept=.xml color=blue-grey border-dashed shadow-inner').classes('w-full')
        
        # Area notifiche integrata
        notification_box = ui.card().classes('w-full mt-2 border-l-4')
        notification_box.set_visibility(False)
        with notification_box:
            with ui.row().classes('items-center gap-2 w-full'):
                notification_icon = ui.icon('check_circle', size='md')
                notification_label = ui.label('').classes('flex-grow font-medium')
        
        # Bottone per cancellare il file caricato
        with ui.row().classes('w-full justify-end mt-2'):
            clear_btn = ui.button('🗑️ Reset file', on_click=lambda: clear_upload()) \
                    .props('outline size=sm color=negative') \
                    .classes('px-10 font-bold bg-white dark:bg-slate-800 transition-colors hover:scale-105')
            clear_btn.set_visibility(False)

    # --- UI: CARD PARAMETRI ---
    with ui.card().classes('w-full max-w-4xl mx-auto shadow-lg mt-4 border border-gray-200'):
        with ui.row().classes('items-center gap-2'):    
            ui.label('⚙️ PROCESSING PARAMETERS').classes('text-xl font-bold').style(f'color: {mycol1}')

        with ui.column().classes('w-full gap-4'):
    # Switch grouping con tooltip inline
            with ui.row().classes('items-center gap-2'):
                group_sw = ui.switch('Enable grouping').props('color=primary')
                ui.icon('info').classes('text-sm text-gray-500 cursor-help').tooltip(
                    'Group output by fields: T_filein, T_num_doc, T_data_doc, P_nrdisegno, P_commessa, P_nrddt, P_intento'
                                                                                ) 
                group_sw.disable()
            
            with ui.row().classes('items-center gap-2'):
                energy_sw = ui.switch('Energy contribution management').props('color=primary')
                ui.icon('info').classes('text-sm text-gray-500 cursor-help').tooltip(
                    'Propagate drawing number, order number, and DDT number from previous lines when empty'
                                                                                )
                energy_sw.disable()
            
            ui.separator()
            
            run_btn = ui.button('🔥 RUN CONVERSION').classes('w-full py-4').props('color=primary size=lg')
            run_btn.disable()

    # --- UI: CARD RISULTATI (inizialmente vuota) ---
    result_container = ui.column().classes('w-full max-w-4xl mx-auto mt-4')

# --- FUNZIONE DI RESET COMPLETO ---
    def clear_upload():
        """Cancella il file caricato e resetta l'interfaccia"""
        logger.info(f"FILE CLEARED BY USER | File: {app_state['xml_filename']}")        
        app_state['xml_content'] = None
        app_state['xml_filename'] = None
        app_state['dataframe'] = None
        app_state['file_hash'] = None
        rows_label.set_text('File: none (0 lines)')
        upload_widget.reset()
        clear_btn.set_visibility(False)
        notification_box.set_visibility(False)
        notification_box.classes(add='opacity-0', remove='opacity-100')
        group_sw.disable()
        energy_sw.disable()
        run_btn.disable()
        result_container.clear()


# --- FUNZIONE DI ELABORAZIONE ---
    def on_run_click():
        """Elabora il file XML caricato."""
        result_container.clear()
        
        if not app_state['xml_content']:
            ui.notify('Nessun file caricato', type='warning')
            return
        
        # Mostra spinner
        with result_container:
            with ui.card().classes('w-full shadow-lg border border-gray-200'):
                ui.label('⏳ Elaborazione in corso...').classes('text-lg font-bold')
                ui.spinner(size='lg')
        
        try:
            start_time = time.time()
            
            # Conversione XML -> DataFrame
            df = convert_xml_to_df(
                app_state['xml_content'],
                app_state['xml_filename'],
                group_sw.value,
                energy_sw.value
            )
            
            processing_time = time.time() - start_time
            
            # Salva DataFrame nello stato
            app_state['dataframe'] = df
            
            if df.empty:
                result_container.clear()
                with result_container:
                    ui.notify('⚠️ Nessun dato estratto dal file XML', type='warning')
                return
            
            # Log elaborazione
            log_usage(
                filename=app_state['xml_filename'],
                status="COMPLETED",
                message=f"Processed in {processing_time:.2f}s, grouping={group_sw.value}, energy={energy_sw.value}",
                action="PROCESS",
                file_hash=app_state['file_hash'][:16] if app_state['file_hash'] else ""
            )
            
            # Mostra risultati
            result_container.clear()
            
            with result_container:
                with ui.card().classes('w-full shadow-lg border border-gray-200'):
                    ui.label('📊 OUTPUT DATAFRAME').classes('text-xl font-bold text-primary mb-4')
                    
                    # Statistiche
                    with ui.row().classes('gap-4 mb-4'):
                        with ui.card().classes('p-4'):
                            ui.label('Documents').classes('text-sm text-gray-600')
                            ui.label(str(df['T_num_doc'].nunique())).classes('text-2xl font-bold text-blue-600')
                        
                        with ui.card().classes('p-4'):
                            ui.label('Total Lines').classes('text-sm text-gray-600')
                            ui.label(str(len(df))).classes('text-2xl font-bold text-green-600')
                        
                        with ui.card().classes('p-4'):
                            ui.label('Processing Time').classes('text-sm text-gray-600')
                            ui.label(f'{processing_time:.2f}s').classes('text-2xl font-bold text-purple-600')
                    
                    ui.separator()
                    
                    # Tabella dati con paginazione
                    columns = [{'name': col, 'label': col, 'field': col, 'align': 'left'} for col in df.columns]
                    rows = df.to_dict('records')
                    
                    ui.table(
                        columns=columns,
                        rows=rows,
                        row_key='T_num_doc',
                        pagination={'rowsPerPage': 20, 'sortBy': 'P_nr_linea'}
                    ).classes('w-full')
                    
                    ui.separator()
                    
                    # Bottone download Excel
                    def download_excel():
                        excel_data = create_excel_buffer(df)
                        filename_out = app_state['xml_filename'].replace(".xml", ".xlsx")
                        
                        # Log download
                        log_usage(
                            filename=filename_out,
                            status="COMPLETED",
                            message="Excel file downloaded",
                            action="DOWNLOAD",
                            file_hash=app_state['file_hash'][:16] if app_state['file_hash'] else ""
                        )
                        
                        ui.download(excel_data, filename_out)
                        ui.notify('✅ Excel file downloaded successfully!', type='positive')
                    
                    ui.button('⬇️ DOWNLOAD EXCEL FILE', on_click=download_excel).classes('w-full py-4').props('color=primary size=lg')
                
                # Footer con timestamp
                with ui.card().classes('w-full shadow-lg border border-gray-200 mt-4'):
                    timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
                    ui.label('📋 PROCESS LOG').classes('font-bold text-lg mb-2')
                    ui.label(f'✅ Elaboration completed successfully at {timestamp}').classes('text-green-600')
        
        except Exception as e:
            logger.error(f"Error during elaboration: {e}", exc_info=True)
            result_container.clear()
            with result_container:
                with ui.card().classes('w-full shadow-lg border border-red-500'):
                    ui.label('❌ ERROR').classes('text-xl font-bold text-red-600 mb-2')
                    ui.label(f'An error occurred during processing:').classes('mb-2')
                    ui.label(str(e)).classes('text-sm font-mono bg-red-50 p-3 rounded')
                ui.notify(f'❌ Errore: {str(e)}', type='negative')


# --- LOGICA DI COORDINAMENTO ---
    async def process_file(e):
        # 1. Estrae i dati dall'evento
        success, content, name, rows = await handle_upload(
            e, upload_widget, rows_label, notification_box, notification_icon, notification_label
        )
        
        # 2. Mostra sempre il bottone "Rimuovi file"
        clear_btn.set_visibility(True)
        
        # 3. Test e attivazione UI
        if success:
            app_state['xml_content'] = content
            app_state['xml_filename'] = name
            app_state['file_hash'] = hashlib.sha256(content).hexdigest()
            
            # Abilita la card parametri
            group_sw.enable()
            energy_sw.enable()
            run_btn.enable()
            
            # Collega l'azione al tasto RUN
            run_btn.on('click', on_run_click, [])
        else:
            # Se fallisce, disabilita i parametri
            group_sw.disable()
            energy_sw.disable()
            run_btn.disable()

    # Collega l'evento upload
    upload_widget.on_upload(process_file)

    ui.run(
        title=APP_NAME,
        host=args.host,
        port=args.port,
        reload=args.reload,
        show=args.show,
        dark=False
    )