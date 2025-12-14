# Usa un'immagine Python ufficiale come base
FROM python:3.14.2-slim

# Imposta la directory di lavoro nel container
WORKDIR /xml_invoice_converter_app

# Copia i file dei requisiti
COPY requirements.txt .

# Installa le dipendenze
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il codice sorgente
COPY . .

# Espone la porta 8502 per Streamlit
EXPOSE 8502

# Configura Streamlit per accettare connessioni da qualsiasi IP
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_PORT=8502
ENV TZ=Europe/Rome
ENV DOCKER_CONTAINER=true

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl --fail http://localhost:8502/_stcore/health || exit 1

# Comando per avviare l'applicazione tramite run.py
CMD ["python", "run.py"]