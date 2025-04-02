# Extractor de Documentos

Aplicación web desarrollada con Streamlit para extraer información de documentos legales, específicamente contratos de compraventa. Utiliza spaCy para el procesamiento del lenguaje natural y reconocimiento de entidades nombradas.

## Características

- Extracción de información de vendedor y comprador (nombres, DNIs, direcciones)
- Reconocimiento de detalles del contrato (objeto, precio, condiciones)
- Interfaz web amigable con Streamlit
- Procesamiento de archivos PDF
- Utiliza el modelo es_core_news_lg de spaCy para NER

## Requisitos

- Python 3.8+
- spaCy
- Streamlit
- PyPDF2
- Otros requisitos en requirements.txt

## Instalación

1. Clonar el repositorio:
```bash
git clone https://github.com/TomasPalazon/Extractor_documentos.git
cd Extractor_documentos
```

2. Instalar dependencias:
```bash
pip install -r requirements.txt
python -m spacy download es_core_news_lg
```

## Uso

Para ejecutar la aplicación:
```bash
streamlit run app.py
```

## Despliegue

La aplicación está desplegada en Streamlit Cloud y se puede acceder en: [URL de la aplicación]
