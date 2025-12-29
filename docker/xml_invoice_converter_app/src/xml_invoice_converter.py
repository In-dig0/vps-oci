"""
XML Invoice Converter - NiceGUI WebApp
Converts XML B2B invoices to Excel format with logging capabilities.
"""

import io
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import xmltodict
from zoneinfo import ZoneInfo
from nicegui import ui, app

# Configuration
APP_NAME = "XML_CONVERTER"
APP_CODE = "XMLC_v2"
TIMEZONE = ZoneInfo("Europe/Rome")
VERSION = "2.0"

# Log configuration
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "app_usage.log"

# Setup logging
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class InvoiceData:
    """Data class for invoice information."""
    filename: str
    supplier_vat: str
    supplier_name: str
    doc_number: str
    doc_date: str
    doc_amount: str


@dataclass
class LineData:
    """Data class for invoice line information."""
    line_number: str
    article_code: str
    description: str
    quantity: str
    unit: str
    unit_price: str
    total_price: str
    vat_code: str
    drawing_number: str
    order_number: str
    ddt_number: str
    intent: str


class XMLInvoiceParser:
    """Parser for XML B2B invoices."""
    
    DEFAULT_VALUE = "**"
    DEFAULT_NUMERIC = "0"
    
    def __init__(self):
        self._reset_state()
    
    def _reset_state(self) -> None:
        """Reset parser internal state."""
        self._previous_values = {
            'drawing_number': self.DEFAULT_VALUE,
            'order_number': self.DEFAULT_VALUE,
            'ddt_number': self.DEFAULT_VALUE
        }
    
    def parse(
        self, 
        content: bytes,
        filename: str,
        enable_grouping: bool = False,
        manage_energy_contribution: bool = False
    ) -> pd.DataFrame:
        """Parse XML invoice file and return DataFrame."""
        try:
            self._reset_state()
            xml_dict = xmltodict.parse(content.decode('utf-8'))
            root_tag = next(iter(xml_dict))
            
            invoice_data = self._extract_invoice_data(xml_dict, root_tag)
            invoice_data.filename = filename
            
            lines_data = self._extract_lines_data(
                xml_dict, 
                root_tag, 
                manage_energy_contribution
            )
            
            df = self._create_dataframe(invoice_data, lines_data)
            
            if enable_grouping and not df.empty:
                df = self._apply_grouping(df)
            
            return df
            
        except Exception as e:
            logger.error(f"Error parsing XML file: {e}", exc_info=True)
            raise
    
    def _extract_nested_value(
        self, 
        data: Dict, 
        path: List[str], 
        default: Optional[str] = None
    ) -> str:
        """Extract value from nested dictionary structure."""
        current = data
        try:
            for key in path:
                current = current[key]
            return str(current) if current is not None else (default or self.DEFAULT_VALUE)
        except (KeyError, TypeError):
            return default or self.DEFAULT_VALUE
    
    def _extract_invoice_data(self, xml_dict: Dict, root_tag: str) -> InvoiceData:
        """Extract invoice header and document data."""
        header = xml_dict[root_tag]["FatturaElettronicaHeader"]
        body = xml_dict[root_tag]["FatturaElettronicaBody"]
        general_data = body["DatiGenerali"]["DatiGeneraliDocumento"]
        
        return InvoiceData(
            filename="",
            supplier_vat=self._extract_nested_value(
                header, ["CedentePrestatore", "DatiAnagrafici", "IdFiscaleIVA", "IdCodice"]
            ),
            supplier_name=self._extract_nested_value(
                header, ["CedentePrestatore", "DatiAnagrafici", "Anagrafica", "Denominazione"]
            ),
            doc_number=self._extract_nested_value(general_data, ["Numero"]),
            doc_date=self._extract_nested_value(general_data, ["Data"]),
            doc_amount=self._extract_nested_value(
                general_data, ["ImportoTotaleDocumento"], self.DEFAULT_NUMERIC
            )
        )
    
    def _extract_lines_data(
        self, 
        xml_dict: Dict, 
        root_tag: str,
        manage_energy: bool
    ) -> List[LineData]:
        """Extract invoice lines data."""
        lines = xml_dict[root_tag]["FatturaElettronicaBody"]["DatiBeniServizi"]["DettaglioLinee"]
        
        if not isinstance(lines, list):
            lines = [lines]
        
        result = []
        for line in lines:
            line_data = self._parse_line(line, manage_energy)
            result.append(line_data)
        
        return result
    
    def _parse_line(self, line: Dict, manage_energy: bool) -> LineData:
        """Parse single invoice line."""
        article_code = self.DEFAULT_VALUE
        if isinstance(line.get("CodiceArticolo"), dict):
            article_code = line["CodiceArticolo"].get("CodiceValore", self.DEFAULT_VALUE)
        
        attachments = line.get("AltriDatiGestionali", [])
        attachment_data = self._process_attachments(attachments, manage_energy)
        
        return LineData(
            line_number=str(line.get("NumeroLinea", self.DEFAULT_VALUE)),
            article_code=article_code,
            description=line.get("Descrizione", self.DEFAULT_VALUE),
            quantity=str(line.get("Quantita", self.DEFAULT_NUMERIC)),
            unit=line.get("UnitaMisura", self.DEFAULT_VALUE),
            unit_price=str(line.get("PrezzoUnitario", self.DEFAULT_NUMERIC)),
            total_price=str(line.get("PrezzoTotale", self.DEFAULT_NUMERIC)),
            vat_code=str(line.get("AliquotaIVA", self.DEFAULT_NUMERIC)),
            drawing_number=attachment_data['drawing_number'],
            order_number=attachment_data['order_number'],
            ddt_number=attachment_data['ddt_number'],
            intent=attachment_data['intent']
        )
    
    def _process_attachments(
        self, 
        attachments: Any, 
        manage_energy: bool
    ) -> Dict[str, str]:
        """Process line attachments."""
        result = {
            'drawing_number': self.DEFAULT_VALUE,
            'order_number': self.DEFAULT_VALUE,
            'ddt_number': self.DEFAULT_VALUE,
            'intent': self.DEFAULT_VALUE
        }
        
        if not attachments:
            return self._apply_energy_management(result, manage_energy)
        
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
                    result[field] = attachment.get("RiferimentoTesto", self.DEFAULT_VALUE)
        
        return self._apply_energy_management(result, manage_energy)
    
    def _apply_energy_management(
        self, 
        result: Dict[str, str], 
        manage_energy: bool
    ) -> Dict[str, str]:
        """Apply energy contribution management logic."""
        if manage_energy:
            for field in ['drawing_number', 'order_number', 'ddt_number']:
                if result[field] == self.DEFAULT_VALUE:
                    result[field] = self._previous_values[field]
        
        for field in ['drawing_number', 'order_number', 'ddt_number']:
            if result[field] != self.DEFAULT_VALUE:
                self._previous_values[field] = result[field]
        
        return result
    
    def _create_dataframe(
        self, 
        invoice: InvoiceData, 
        lines: List[LineData]
    ) -> pd.DataFrame:
        """Create DataFrame from parsed data."""
        if not lines:
            return pd.DataFrame()
        
        data = {
            'T_filein': [invoice.filename] * len(lines),
            'T_piva_mitt': [invoice.supplier_vat] * len(lines),
            'T_ragsoc_mitt': [invoice.supplier_name] * len(lines),
            'T_num_doc': [invoice.doc_number] * len(lines),
            'T_data_doc': [invoice.doc_date] * len(lines),
            'T_importo_doc': [invoice.doc_amount] * len(lines),
            'P_nr_linea': [line.line_number for line in lines],
            'P_codart': [line.article_code for line in lines],
            'P_desc_linea': [line.description for line in lines],
            'P_qta': [line.quantity for line in lines],
            'P_um': [line.unit for line in lines],
            'P_przunit': [line.unit_price for line in lines],
            'P_prezzo_tot': [line.total_price for line in lines],
            'P_codiva': [line.vat_code for line in lines],
            'P_nrdisegno': [line.drawing_number for line in lines],
            'P_commessa': [line.order_number for line in lines],
            'P_nrddt': [line.ddt_number for line in lines],
            'P_intento': [line.intent for line in lines]
        }
        
        df = pd.DataFrame(data)
        
        numeric_cols = ['T_importo_doc', 'P_qta', 'P_przunit', 'P_prezzo_tot']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        return df
    
    def _apply_grouping(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply grouping to DataFrame."""
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


class UsageLogger:
    """Logger for application usage tracking."""
    
    def __init__(self, log_file: Path = LOG_FILE):
        self.log_file = log_file
    
    def log_usage(
        self,
        filename: str,
        status: str = "COMPLETED",
        message: str = "",
        action: str = "PROCESS"
    ) -> None:
        """Log application usage."""
        try:
            timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            
            log_line = (
                f"{timestamp} | {APP_NAME} | {APP_CODE} | {action} | "
                f"{filename} | {status} | {message}\n"
            )
            
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_line)
            
        except Exception as e:
            logger.error(f"Error logging usage: {e}", exc_info=True)


class ExcelExporter:
    """Excel file exporter."""
    
    @staticmethod
    def create_excel_buffer(
        df: pd.DataFrame, 
        sheet_name: str = "Invoice"
    ) -> bytes:
        """Create Excel file in memory buffer."""
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


# Global state
class AppState:
    def __init__(self):
        self.df = None
        self.uploaded_file_name = None
        self.uploaded_file_content = None
        self.enable_grouping = False
        self.manage_energy = False


state = AppState()
parser = XMLInvoiceParser()
usage_logger = UsageLogger()

# Detect environment
in_docker = os.path.exists('/.dockerenv') or os.getenv('DOCKER_CONTAINER') == 'true'
env_badge = "🐳 Docker" if in_docker else "💻 Local"

# Configure dark mode
dark_mode = ui.dark_mode()

# Set background and card colors with CSS that responds to dark mode
ui.add_head_html('''
<style>
    /* Light mode */
    body {
        background-color: #ffffff !important;
        transition: background-color 0.3s ease;
    }
    
    /* Dark mode */
    .body--dark {
        background-color: #121212 !important;
    }
    
    /* Light mode cards */
    .q-card {
        background-color: #f5f5f5 !important;
    }
    
    /* Dark mode cards */
    .body--dark .q-card {
        background-color: #1e1e1e !important;
    }
</style>
''')

# Dark mode toggle in top right corner
with ui.row().classes('w-full justify-end mb-2'):
    ui.button(
        icon='dark_mode', 
        on_click=dark_mode.toggle
    ).props('flat round').tooltip('Toggle dark/light mode')

# Header card
with ui.card().classes('w-full mb-4'):
    ui.label('📄 XML Invoice Converter').classes('text-3xl font-bold text-primary')
    ui.label('Convert XML B2B invoices to Excel format').classes('text-xl text-yellow-600')
    ui.separator()
    
    with ui.row().classes('gap-4'):
        ui.label(f'Version: {VERSION}').classes('text-sm')
        ui.label('Powered by NiceGUI').classes('text-sm')
    
    # Framework versions
    import sys
    try:
        import nicegui
        nicegui_version = nicegui.__version__
    except:
        nicegui_version = 'installed'
    
    with ui.expansion('📦 Framework versions', icon='info').classes('w-full'):
        ui.label(f'😊 NiceGUI: {nicegui_version}')
        ui.label(f'🐍 Python: {sys.version.split()[0]}')
        ui.label(f'📊 Pandas: {pd.__version__}')
        ui.label(f'🌍 Environment: {env_badge}')

# Input section
with ui.card().classes('w-full mb-4'):
    ui.label('📥 INPUT PARAMETERS').classes('text-lg font-bold text-primary mb-2')
    
    upload_result = ui.label('No file uploaded').classes('text-sm text-gray-500 mb-2')
    
    # Container per l'upload widget
    upload_container = ui.row().classes('w-full')
    
    def reset_upload():
        """Reset upload state."""
        state.uploaded_file_content = None
        state.uploaded_file_name = None
        upload_result.text = 'No file uploaded'
        upload_result.classes('text-sm text-gray-500 mb-2', remove='text-green-600')
        result_container.clear()
        # Ricrea l'upload widget
        upload_container.clear()
        with upload_container:
            ui.upload(
                label='Select XML invoice B2B file',
                on_multi_upload=handle_upload_complete,
                auto_upload=True,
                multiple=False,
                max_files=1
            ).props('accept=".xml"').classes('w-full')
        logger.info("Upload reset")
    
    async def handle_upload_complete(e):
        try:
            logger.info(f"Upload event received")
            
            if hasattr(e, 'files') and e.files:
                file_upload = e.files[0]
                state.uploaded_file_name = file_upload.name
                
                if hasattr(file_upload, 'read'):
                    state.uploaded_file_content = await file_upload.read()
                elif hasattr(file_upload, 'content'):
                    state.uploaded_file_content = file_upload.content
                else:
                    logger.error("Cannot read file content")
                    ui.notify('Unable to read file content', type='negative')
                    return
                
                upload_result.text = f'✅ File uploaded: {state.uploaded_file_name} ({len(state.uploaded_file_content)} bytes)'
                upload_result.classes('text-sm text-green-600 mb-2', remove='text-gray-500')
                result_container.clear()
                logger.info(f"File uploaded successfully: {state.uploaded_file_name}, size: {len(state.uploaded_file_content)}")
                
                # Sostituisci l'upload con un'area info + pulsante reset
                upload_container.clear()
                with upload_container:
                    with ui.row().classes('w-full items-center gap-2'):
                        ui.label(f'📎 {state.uploaded_file_name}').classes('flex-grow font-bold')
                        ui.button(
                            icon='close',
                            on_click=reset_upload
                        ).props('flat round color=negative').tooltip('Remove file and select another')
            else:
                logger.error("No files found in event")
                ui.notify('Unable to process uploaded file - no files', type='negative')
                return
            
        except Exception as ex:
            logger.error(f"Error handling upload: {ex}", exc_info=True)
            ui.notify(f'Error: {str(ex)}', type='negative')
    
    # Initial upload widget
    with upload_container:
        ui.upload(
            label='Select XML invoice B2B file',
            on_multi_upload=handle_upload_complete,
            auto_upload=True,
            multiple=False,
            max_files=1
        ).props('accept=".xml"').classes('w-full')
    
    # Options
    ui.separator()
    
    with ui.row().classes('items-center gap-2'):
        grouping_switch = ui.switch(
            'Enable grouping',
            value=False,
            on_change=lambda e: setattr(state, 'enable_grouping', e.value) or update_energy_switch()
        )
        ui.icon('info').classes('text-sm text-gray-500').tooltip(
            'Group output by fields: T_filein, T_num_doc, T_data_doc, P_nrdisegno, P_commessa, P_nrddt, P_intento'
        )
    
    with ui.row().classes('items-center gap-2'):
        energy_switch = ui.switch(
            'Energy contribution management',
            value=False,
            on_change=lambda e: setattr(state, 'manage_energy', e.value)
        )
        energy_switch.visible = False
        energy_icon = ui.icon('info').classes('text-sm text-gray-500')
        energy_icon.tooltip(
            'Propagate drawing number, order number, and DDT number from previous lines when empty'
        )
        energy_icon.visible = False
    
    def update_energy_switch():
        energy_switch.visible = state.enable_grouping
        energy_icon.visible = state.enable_grouping
        if not state.enable_grouping:
            state.manage_energy = False
            energy_switch.value = False
    
    # Run button at the bottom
    ui.separator()
    ui.button('🔥 Run', on_click=lambda: process_file()).classes('w-full')

# Results container
result_container = ui.column().classes('w-full')

def process_file():
    """Process the uploaded XML file."""
    result_container.clear()
    
    logger.info(f"Process file called. File name: {state.uploaded_file_name}, Content exists: {state.uploaded_file_content is not None}")
    
    if not state.uploaded_file_content:
        ui.notify('Please upload a file first', type='warning')
        logger.warning("No file content available")
        return
    
    with result_container:
        with ui.card().classes('w-full'):
            ui.label('⏳ Processing XML file...').classes('text-lg')
            ui.spinner(size='lg')
    
    try:
        # Parse XML
        df = parser.parse(
            state.uploaded_file_content,
            state.uploaded_file_name,
            state.enable_grouping,
            state.manage_energy
        )
        
        state.df = df
        
        if df.empty:
            result_container.clear()
            with result_container:
                ui.notify('⚠️ No data extracted from XML file', type='warning')
            return
        
        # Log processing
        usage_logger.log_usage(
            filename=state.uploaded_file_name,
            status="COMPLETED",
            message=f"Processed with grouping={state.enable_grouping}, energy={state.manage_energy}",
            action="PROCESS"
        )
        
        # Display results
        result_container.clear()
        
        with result_container:
            with ui.card().classes('w-full mb-4'):
                ui.label('📊 OUTPUT DATAFRAME').classes('text-lg font-bold text-primary mb-4')
                
                with ui.row().classes('gap-4 mb-4'):
                    with ui.card():
                        ui.label('Header Count').classes('text-sm text-gray-600')
                        ui.label(str(df['T_num_doc'].nunique())).classes('text-2xl font-bold')
                    
                    with ui.card():
                        ui.label('Record Count').classes('text-sm text-gray-600')
                        ui.label(str(len(df))).classes('text-2xl font-bold')
                
                # Display table with pagination
                columns = [{'name': col, 'label': col, 'field': col} for col in df.columns]
                rows = df.to_dict('records')
                
                ui.table(
                    columns=columns,
                    rows=rows,
                    row_key='T_num_doc',
                    pagination={'rowsPerPage': 20, 'sortBy': 'T_num_doc'}
                ).classes('w-full')
                
                # Export button
                ui.separator()
                
                def download_excel():
                    exporter = ExcelExporter()
                    excel_data = exporter.create_excel_buffer(df)
                    filename_out = state.uploaded_file_name.replace(".xml", ".xlsx")
                    
                    # Log download
                    usage_logger.log_usage(
                        filename=filename_out,
                        status="COMPLETED",
                        message=f"Excel file downloaded",
                        action="DOWNLOAD"
                    )
                    
                    ui.download(excel_data, filename_out)
                    ui.notify('✅ File downloaded successfully', type='positive')
                
                ui.button('⬇️ Download Excel', on_click=download_excel).classes('w-full')
            
            # Footer
            with ui.card().classes('w-full'):
                timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
                ui.label('📋 APP LOG').classes('font-bold mb-2')
                ui.label(f'✅ App terminated successfully at {timestamp}').classes('text-green-600')
        
    except Exception as e:
        logger.error(f"Error processing file: {e}", exc_info=True)
        result_container.clear()
        with result_container:
            ui.notify(f'❌ Error processing XML file: {str(e)}', type='negative')


# Run the application
if __name__ in {"__main__", "__mp_main__"}:
    import argparse
    
    # Parse command line arguments
    parser_args = argparse.ArgumentParser(description='XML Invoice Converter - NiceGUI')
    parser_args.add_argument('--host', type=str, default='0.0.0.0', help='Server host')
    parser_args.add_argument('--port', type=int, default=8502, help='Server port')
    parser_args.add_argument('--reload', action='store_true', help='Enable auto-reload')
    parser_args.add_argument('--show', action='store_true', help='Open browser automatically')
    
    args = parser_args.parse_args()
    
    logger.info(f"Starting XML Invoice Converter on {args.host}:{args.port}")
    
    ui.run(
        title='XML Invoice Converter',
        host=args.host,
        port=args.port,
        reload=args.reload,
        show=args.show,
        dark=False  # Start in light mode
    )