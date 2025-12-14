"""
XML Invoice Converter - Streamlit WebApp
Converts XML B2B invoices to Excel format with logging capabilities.
"""

import io
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
import xmltodict
from zoneinfo import ZoneInfo

# Configuration
APP_NAME = "XML_CONVERTER"
APP_CODE = "XMLC_v2"
TIMEZONE = ZoneInfo("Europe/Rome")
VERSION = "2.0"

# Log configuration - logs folder at project root level
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
        uploaded_file: Any,
        enable_grouping: bool = False,
        manage_energy_contribution: bool = False
    ) -> pd.DataFrame:
        """
        Parse XML invoice file and return DataFrame.
        
        Args:
            uploaded_file: Streamlit uploaded file object
            enable_grouping: Whether to group results by specific fields
            manage_energy_contribution: Whether to manage energy contributions
            
        Returns:
            DataFrame with parsed invoice data
        """
        try:
            self._reset_state()
            xml_dict = self._load_xml(uploaded_file)
            root_tag = next(iter(xml_dict))
            
            invoice_data = self._extract_invoice_data(xml_dict, root_tag)
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
            st.error(f"Error parsing XML: {str(e)}")
            return pd.DataFrame()
    
    def _load_xml(self, uploaded_file: Any) -> Dict:
        """Load and parse XML file."""
        content = io.StringIO(uploaded_file.getvalue().decode("utf-8")).read()
        return xmltodict.parse(content)
    
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
            filename="",  # Set later
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
        # Extract basic line data
        article_code = self.DEFAULT_VALUE
        if isinstance(line.get("CodiceArticolo"), dict):
            article_code = line["CodiceArticolo"].get("CodiceValore", self.DEFAULT_VALUE)
        
        # Extract attachments
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
        
        # Update previous values
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
        
        # Convert numeric columns
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
        """
        Log application usage.
        
        Args:
            filename: Name of the processed file
            status: Processing status
            message: Additional message
            action: Action type (PROCESS, DOWNLOAD, etc.)
        """
        try:
            timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            
            log_entry = {
                "timestamp": timestamp,
                "app_name": APP_NAME,
                "app_code": APP_CODE,
                "action": action,
                "filename": filename,
                "status": status,
                "message": message
            }
            
            # Create formatted log entry
            log_line = (
                f"{timestamp} | {APP_NAME} | {APP_CODE} | {action} | "
                f"{filename} | {status} | {message}\n"
            )
            
            # Append to log file
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
    ) -> io.BytesIO:
        """
        Create Excel file in memory buffer.
        
        Args:
            df: DataFrame to export
            sheet_name: Name of the Excel sheet
            
        Returns:
            BytesIO buffer containing Excel file
        """
        buffer = io.BytesIO()
        
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets[sheet_name]
            
            # Add formatting
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'border': 1
            })
            
            # Apply header format
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
        
        buffer.seek(0)
        return buffer


def initialize_session_state() -> None:
    """Initialize Streamlit session state variables."""
    defaults = {
        "clicked": False,
        "download_completed": False,
        "prev_grouping_opt": None,
        "prev_energy_mgmt": None,
        "process_logged": False
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_download_state() -> None:
    """Reset download state callback."""
    st.session_state.download_completed = False


def on_run_click() -> None:
    """Handle Run button click."""
    st.session_state.clicked = True
    st.session_state.download_completed = False
    st.session_state.process_logged = False


def check_parameter_changes(grouping: bool, energy: bool) -> None:
    """Check if parameters changed and reset state if needed."""
    if (st.session_state.prev_grouping_opt != grouping or 
        st.session_state.prev_energy_mgmt != energy):
        st.session_state.clicked = False
    
    st.session_state.prev_grouping_opt = grouping
    st.session_state.prev_energy_mgmt = energy


def display_header() -> None:
    """Display application header."""
    # Detect environment
    in_docker = os.path.exists('/.dockerenv') or os.getenv('DOCKER_CONTAINER') == 'true'
    env_badge = "🐳 Docker" if in_docker else "💻 Local"
    
    st.title(":blue[📄 XML Invoice Converter]")
    st.subheader(":yellow[Convert XML B2B invoices to Excel format]")
    
    # Application details
    st.markdown(f"**Version:** {VERSION}")
    st.markdown("Powered with Streamlit :streamlit:")
    
    # Framework versions expander
    with st.expander("📦 Framework versions"):
        st.markdown(f"- 🎈 **Streamlit:** {st.__version__}")
        st.markdown(f"- 🐍 **Python:** {sys.version.split()[0]}")
        st.markdown(f"- 📊 **Pandas:** {pd.__version__}")
        st.markdown(f"- 📝 **xlsxwriter:** installed")
        st.markdown(f"- 🔤 **xmltodict:** installed")
        st.markdown(f"- 🌍 **Environment:** {env_badge}")
    
    st.divider()


def display_footer() -> None:
    """Display application footer."""
    timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    
    st.divider()
    st.markdown("**📋 APP LOG**")
    st.success(f"✅ App terminated successfully at {timestamp}")


def main():
    """Main application function."""
    # Configure page
    st.set_page_config(
        page_title="XML Invoice Converter",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="auto"
    )
    
    # Initialize
    initialize_session_state()
    
    # Display header
    display_header()
    
    # Input section
    st.markdown(":blue-background[**📥 INPUT PARAMETERS**]")
    uploaded_file = st.file_uploader(
        "Select XML invoice B2B file:",
        type="xml",
        accept_multiple_files=False
    )
    
    # Options
    enable_grouping = st.toggle(
        "Enable grouping",
        help="Group output by fields: T_filein, T_num_doc, T_data_doc, P_nrdisegno, P_commessa, P_nrddt, P_intento"
    )
    
    manage_energy = False
    
    if enable_grouping:
        manage_energy = st.toggle(
            "Energy contribution management", 
            value=True,
            help="Propagate drawing number, order number, and DDT number from previous lines when empty"
        )
    
    # Check for parameter changes
    check_parameter_changes(enable_grouping, manage_energy)
    
    # Run button
    run_disabled = uploaded_file is None
    st.button(
        "🔥 Run",
        disabled=run_disabled,
        on_click=on_run_click,
        width="stretch"
    )
    
    # Process file
    if st.session_state.clicked and uploaded_file is not None:
        with st.spinner("Processing XML file..."):
            try:
                # Parse XML
                parser = XMLInvoiceParser()
                df = parser.parse(uploaded_file, enable_grouping, manage_energy)
                
                # Update filename in DataFrame
                if not df.empty:
                    df['T_filein'] = uploaded_file.name
                
                if df.empty:
                    st.warning("⚠️ No data extracted from XML file")
                    return
                
                # Display results
                st.divider()
                st.markdown(":blue-background[**📊 OUTPUT DATAFRAME**]")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Header Count", df['T_num_doc'].nunique())
                with col2:
                    st.metric("Record Count", len(df))
                
                st.dataframe(df, width="stretch", hide_index=True)
                
                # Export to Excel
                if len(df) > 0:
                    exporter = ExcelExporter()
                    excel_buffer = exporter.create_excel_buffer(df)
                    filename_out = uploaded_file.name.replace(".xml", ".xlsx")
                    
                    # Log processing completion (only once)
                    usage_logger = UsageLogger()
                    if not st.session_state.process_logged:
                        usage_logger.log_usage(
                            filename=uploaded_file.name,
                            status="COMPLETED",
                            message=f"Processed with grouping={enable_grouping}, energy={manage_energy}",
                            action="PROCESS"
                        )
                        st.session_state.process_logged = True
                    
                    download_clicked = st.download_button(
                        label="⬇️ Download Excel",
                        data=excel_buffer,
                        file_name=filename_out,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        on_click=reset_download_state,
                        disabled=st.session_state.download_completed,
                        width="stretch"
                    )
                    
                    if download_clicked:
                        st.success("✅ File downloaded successfully")
                        st.session_state.download_completed = True
                        
                        # Log download
                        usage_logger.log_usage(
                            filename=filename_out,
                            status="COMPLETED",
                            message=f"Excel file downloaded",
                            action="DOWNLOAD"
                        )
                
                # Display footer
                display_footer()
                
            except Exception as e:
                logger.error(f"Error processing file: {e}", exc_info=True)
                st.error(f"❌ Error processing XML file: {str(e)}")


if __name__ == "__main__":
    main()