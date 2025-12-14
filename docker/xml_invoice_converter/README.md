# 📄 XML Invoice Converter

Applicazione web per convertire fatture elettroniche XML in formato B2B in file Excel, con funzionalità avanzate di raggruppamento e gestione contributi energetici.

## 🎯 Caratteristiche

- ✅ **Conversione XML → Excel**: Trasforma fatture XML B2B in formato Excel strutturato
- 📊 **Raggruppamento intelligente**: Aggrega dati per campi specifici
- ⚡ **Gestione contributi energetici**: Propaga automaticamente valori tra righe fattura
- 📝 **Logging automatico**: Traccia tutte le operazioni in file di log
- 🎨 **Interfaccia intuitiva**: UI moderna e user-friendly con Streamlit
- 🐳 **Docker ready**: Supporto completo per containerizzazione

## 📋 Prerequisiti

- Python 3.9 o superiore
- pip (package manager Python)
- Git (opzionale, per clonare il repository)

## 🚀 Installazione

### Metodo 1: Installazione Locale

1. **Clona il repository**
```bash
git clone https://github.com/In-dig0/xml-invoice-converter.git
cd xml-invoice-converter
```

2. **Crea un ambiente virtuale (raccomandato)**
```bash
python -m venv venv

# Windows
venv\scripts\activate

# Linux/Mac
source venv/bin/activate
```

3. **Installa le dipendenze**
```bash
pip install -r requirements.txt
```

4. **Avvia l'applicazione**
```bash
python run.py
```

L'applicazione sarà disponibile su `http://localhost:8502`

### Metodo 2: Docker

1. **Build dell'immagine**
```bash
docker-compose build
```

2. **Avvia il container**
```bash
docker-compose up
```

L'applicazione sarà disponibile su `http://localhost:8502`

## 📖 Utilizzo

### Interfaccia Web

1. **Carica il file XML**: Trascina o seleziona un file XML B2B
2. **Configura le opzioni**:
   - **Enable grouping**: Raggruppa i risultati per campi specifici
   - **Energy contribution management**: Gestisce la propagazione dei valori
3. **Clicca su "Run"**: Elabora il file
4. **Scarica l'Excel**: Clicca su "Download Excel"

### Campi di Raggruppamento

Quando attivi l'opzione "Enable grouping", i dati vengono raggruppati per:
- `T_filein` - Nome del file
- `T_num_doc` - Numero documento
- `T_data_doc` - Data documento
- `P_nrdisegno` - Numero disegno
- `P_commessa` - Numero commessa
- `P_nrddt` - Numero DDT
- `P_intento` - Intento

### Gestione Contributi Energetici

Quando attiva, questa opzione propaga automaticamente i valori di:
- Numero disegno
- Numero commessa  
- Numero DDT

dalle righe precedenti quando questi campi sono vuoti nella riga corrente.

## 📁 Struttura del Progetto

```
XML_INVOICE_CONVERTER/
├── src/
│   └── xml_invoice_converter.py    # Applicazione principale
├── logs/
│   └── app_usage.log               # Log delle operazioni
├── input/                          # Cartella per file XML di test
├── venv/                           # Ambiente virtuale Python
├── .gitignore                      # File Git ignore
├── docker-compose.yml              # Configurazione Docker Compose
├── Dockerfile                      # Dockerfile per containerizzazione
├── README.md                       # Questo file
├── requirements.txt                # Dipendenze Python
└── run.py                         # Script di avvio

```

## 🔧 Configurazione

### Variabili d'Ambiente

L'applicazione supporta le seguenti variabili d'ambiente:

- `PORT`: Porta su cui avviare il server (default: 8502)
- `DOCKER_CONTAINER`: Indica se l'app è in esecuzione in Docker

### File di Log

I log vengono salvati automaticamente in `logs/app_usage.log` con il formato:

```
YYYY-MM-DD HH:MM:SS | APP_NAME | APP_CODE | ACTION | FILENAME | STATUS | MESSAGE
```

Esempio:
```
2025-12-14 08:45:45 | XML_CONVERTER | XMLC_v2 | PROCESS | invoice.xml | COMPLETED | Processed with grouping=False, energy=False
2025-12-14 08:45:48 | XML_CONVERTER | XMLC_v2 | DOWNLOAD | invoice.xlsx | COMPLETED | Excel file downloaded
```

## 📊 Output Excel

Il file Excel generato contiene le seguenti colonne:

### Dati Testata (prefisso T_)
- `T_filein`: Nome file XML originale
- `T_piva_mitt`: Partita IVA mittente
- `T_ragsoc_mitt`: Ragione sociale mittente
- `T_num_doc`: Numero documento
- `T_data_doc`: Data documento
- `T_importo_doc`: Importo totale documento

### Dati Righe (prefisso P_)
- `P_nr_linea`: Numero linea
- `P_codart`: Codice articolo
- `P_desc_linea`: Descrizione
- `P_qta`: Quantità
- `P_um`: Unità di misura
- `P_przunit`: Prezzo unitario
- `P_prezzo_tot`: Prezzo totale
- `P_codiva`: Codice IVA
- `P_nrdisegno`: Numero disegno
- `P_commessa`: Numero commessa
- `P_nrddt`: Numero DDT
- `P_intento`: Intento

## 🛠️ Sviluppo

### Requisiti di Sviluppo

```bash
pip install -r requirements.txt
```

### Struttura del Codice

Il codice è organizzato in classi principali:

- **`XMLInvoiceParser`**: Parser per file XML fatture
- **`UsageLogger`**: Gestione logging applicazione
- **`ExcelExporter`**: Esportazione dati in Excel

### Best Practices

- Usa `dataclass` per strutture dati
- Type hints completi
- Docstrings per documentazione
- Logging strutturato
- Gestione errori robusta

### Testing

Per testare l'applicazione, posiziona file XML di esempio nella cartella `input/` e caricali tramite l'interfaccia.

## 📝 Dipendenze

```
streamlit>=1.52.1
pandas>=2.0.0
xmltodict>=0.13.0
xlsxwriter>=3.1.0
```

Versione completa in `requirements.txt`

## 🐛 Troubleshooting

### L'applicazione non si avvia

```bash
# Verifica l'installazione di Python
python --version

# Reinstalla le dipendenze
pip install -r requirements.txt --force-reinstall
```

### Errore "File not found"

Assicurati che il file XML sia in formato B2B valido e che il percorso sia corretto.

### Log non vengono creati

Verifica che la cartella `logs/` esista e che l'applicazione abbia i permessi di scrittura.

## 🤝 Contribuire

I contributi sono benvenuti! Per contribuire:

1. Fai un fork del progetto
2. Crea un branch per la tua feature (`git checkout -b feature/AmazingFeature`)
3. Commit delle modifiche (`git commit -m 'Add some AmazingFeature'`)
4. Push sul branch (`git push origin feature/AmazingFeature`)
5. Apri una Pull Request

## 📄 Licenza

Questo progetto è distribuito sotto licenza MIT. Vedi il file `LICENSE` per maggiori dettagli.

## 👤 Autore

**Riccardo Baravelli**
- GitHub: [@tuousername](https://github.com/In-dig0)

## 🙏 Ringraziamenti

- [Streamlit](https://streamlit.io) - Framework per l'interfaccia web
- [Pandas](https://pandas.pydata.org) - Gestione dati
- [xmltodict](https://github.com/martinblech/xmltodict) - Parsing XML

## 📚 Changelog

### Version 2.0 (2025-12-14)
- ✨ Refactoring completo del codice
- 🎨 Nuova interfaccia utente migliorata
- 📝 Sistema di logging su file
- 🐳 Supporto Docker
- 🔧 Gestione contributi energetici
- 📊 Export Excel con formattazione

### Version 1.0
- 🎉 Release iniziale
- ⚙️ Conversione base XML → Excel

---

**Nota**: Per supporto o segnalazione bug, apri una [issue](https://github.com/tuousername/xml-invoice-converter/issues) su GitHub.

