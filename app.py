import streamlit as st
import PyPDF2
import io
import re
import spacy
from spacy.language import Language
from spacy.tokens import Doc
import subprocess
import sys
import os

@st.cache_resource
def load_spacy_model():
    """Carga el modelo de spaCy o usa uno más pequeño si el grande falla."""
    try:
        # Primero intentar cargar el modelo grande
        return spacy.load("es_core_news_lg")
    except OSError:
        try:
            # Si falla, intentar descargar el modelo mediano
            st.warning("Descargando modelo de lenguaje español (puede tardar unos minutos)...")
            subprocess.run([sys.executable, "-m", "spacy", "download", "es_core_news_md"], 
                         check=True, capture_output=True)
            return spacy.load("es_core_news_md")
        except (subprocess.CalledProcessError, OSError):
            st.error("No se pudo cargar el modelo de lenguaje. Usando modelo pequeño.")
            # Si todo falla, usar el modelo pequeño
            subprocess.run([sys.executable, "-m", "spacy", "download", "es_core_news_sm"], 
                         check=True, capture_output=True)
            return spacy.load("es_core_news_sm")

# Configuración de la página
st.set_page_config(
    page_title="Extractor de Documentos Notariales",
    layout="wide"
)

class DocumentExtractor:
    def __init__(self):
        """Inicializa el extractor de documentos."""
        self.nlp = load_spacy_model()
        self.label_map = {
            'PER': 'NOMBRE',  # Personas
            'LOC': 'DIR',     # Ubicaciones
            'ORG': 'ORG',     # Organizaciones
            'MISC': 'MISC'    # Otros
        }
    
    def _extract_entities_with_spacy(self, text: str) -> dict:
        """Extrae entidades usando spaCy."""
        entities = {'NOMBRE': [], 'DIR': [], 'ORG': [], 'MISC': []}
        
        # Procesar el texto
        doc = self.nlp(text)
        
        # Extraer entidades
        for ent in doc.ents:
            if ent.label_ in self.label_map:
                category = self.label_map[ent.label_]
                # Solo añadir si el texto tiene más de 2 caracteres y no es solo números
                if len(ent.text.strip()) > 2 and not ent.text.strip().replace('.', '').replace(',', '').isdigit():
                    entity = {
                        'text': ent.text.strip(),
                        'score': 1.0,  # spaCy no proporciona scores
                        'start': ent.start_char,
                        'end': ent.end_char
                    }
                    
                    # Si es una dirección, intentar obtener la dirección completa
                    if category == 'DIR':
                        entity = self._extract_full_address(text, entity)
                    
                    entities[category].append(entity)
        
        return entities

    def _extract_full_address(self, text, entity):
        """Extrae la dirección completa incluyendo números."""
        # Obtener el texto antes y después de la dirección
        start = entity['start']
        end = entity['end']
        
        # Buscar números y extensiones comunes después de la dirección
        address_pattern = r'(?i)(?:' + re.escape(entity['text']) + r')\s*(?:,\s*)?(?:n[úu](?:m(?:ero)?)?\.?\s*)?(\d+(?:\s*(?:-|,)?\s*\d*)?(?:\s*(?:º|ª|bis|ter|[A-Z]|piso|planta|escalera|puerta)\s*\.?\s*\d*)*)'
        
        # Buscar en los siguientes 50 caracteres después de la dirección
        search_text = text[start:end + 50]
        match = re.search(address_pattern, search_text)
        
        if match:
            # Combinar la dirección base con el número
            full_address = entity['text'] + ' ' + match.group(1)
            return {
                'text': full_address,
                'score': entity['score'],
                'start': start,
                'end': end + len(match.group(1))
            }
        return entity

    def _extract_parties(self, reunidos_text):
        """Extrae información de las partes del contrato."""
        parties = {
            "VENDEDOR": {"NOMBRE": "No encontrado", "DNI": "No encontrado", "DIR": "No encontrada"},
            "COMPRADOR": {"NOMBRE": "No encontrado", "DNI": "No encontrado", "DIR": "No encontrada"}
        }
        
        if not reunidos_text:
            return parties

        # Patrón para DNI
        dni_pattern = r'\b[0-9]{8}[A-Z]\b'
        
        try:
            # Intentar dividir el texto en secciones
            if "REUNIDOS" in reunidos_text:
                main_text = reunidos_text.split("REUNIDOS", 1)[1]
            else:
                main_text = reunidos_text

            if "EXPONEN" in main_text:
                main_text = main_text.split("EXPONEN", 1)[0]

            # Dividir entre vendedor y comprador
            if "De otra parte" in main_text:
                parts = main_text.split("De otra parte", 1)
            elif "Por otra parte" in main_text:
                parts = main_text.split("Por otra parte", 1)
            else:
                # Si no encontramos el separador explícito, intentamos dividir por párrafos
                parts = [p.strip() for p in main_text.split('\n\n') if p.strip()]
                if len(parts) < 2:
                    # Si no hay párrafos claros, tomamos la primera y segunda mitad del texto
                    mid = len(main_text) // 2
                    parts = [main_text[:mid], main_text[mid:]]
        except Exception as e:
            st.warning(f"Error dividiendo el texto: {str(e)}")
            parts = []

        if len(parts) >= 2:
            # Procesar vendedor
            vendor_entities = self._extract_entities_with_spacy(parts[0])
            if vendor_entities['NOMBRE']:
                # Tomar el nombre más largo (probablemente el más completo)
                best_name = max(vendor_entities['NOMBRE'], key=lambda x: len(x['text']))
                parties["VENDEDOR"]["NOMBRE"] = best_name['text']
            
            if vendor_entities['DIR']:
                # Tomar la dirección más larga
                best_loc = max(vendor_entities['DIR'], key=lambda x: len(x['text']))
                parties["VENDEDOR"]["DIR"] = best_loc['text']
            
            # DNI con regex (más preciso para este caso específico)
            dni_match = re.search(dni_pattern, parts[0])
            if dni_match:
                parties["VENDEDOR"]["DNI"] = dni_match.group()
            
            # Procesar comprador
            buyer_entities = self._extract_entities_with_spacy(parts[1])
            if buyer_entities['NOMBRE']:
                best_name = max(buyer_entities['NOMBRE'], key=lambda x: len(x['text']))
                parties["COMPRADOR"]["NOMBRE"] = best_name['text']
            
            if buyer_entities['DIR']:
                best_loc = max(buyer_entities['DIR'], key=lambda x: len(x['text']))
                parties["COMPRADOR"]["DIR"] = best_loc['text']
            
            dni_match = re.search(dni_pattern, parts[1])
            if dni_match:
                parties["COMPRADOR"]["DNI"] = dni_match.group()
        else:
            # Si no pudimos dividir el texto, procesar todo junto
            all_entities = self._extract_entities_with_spacy(reunidos_text)
            if all_entities['NOMBRE']:
                names = sorted(all_entities['NOMBRE'], key=lambda x: len(x['text']), reverse=True)
                if len(names) >= 2:
                    parties["VENDEDOR"]["NOMBRE"] = names[0]['text']
                    parties["COMPRADOR"]["NOMBRE"] = names[1]['text']
            
            if all_entities['DIR']:
                locs = sorted(all_entities['DIR'], key=lambda x: len(x['text']), reverse=True)
                if len(locs) >= 2:
                    parties["VENDEDOR"]["DIR"] = locs[0]['text']
                    parties["COMPRADOR"]["DIR"] = locs[1]['text']
            
            # Buscar DNIs en todo el texto
            dni_matches = re.finditer(dni_pattern, reunidos_text)
            dni_list = [m.group() for m in dni_matches]
            if len(dni_list) >= 2:
                parties["VENDEDOR"]["DNI"] = dni_list[0]
                parties["COMPRADOR"]["DNI"] = dni_list[1]
        
        return parties

    def _extract_section(self, text, section_name):
        """Extrae una sección específica del texto."""
        pattern = f"{section_name}(.*?)(?:EXPONEN|CLÁUSULAS|CLAUSULAS|FIRMAN|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _extract_contract_details(self, exponen_text, clausulas_text, full_text):
        """Extrae detalles del contrato."""
        details = {}
        
        # Extraer fecha (combinando regex)
        fecha_pattern = r"(?:En .+?, a|Madrid,?\s+a)\s+(\d{1,2}\s+de\s+[^\d]+\s+de\s+\d{4})"
        fecha_match = re.search(fecha_pattern, full_text, re.IGNORECASE)
        if fecha_match:
            details["FECHA"] = fecha_match.group(1).strip()
        
        # Extraer objeto del contrato
        objeto_pattern = r"consiste en\s+([^\.]+)"
        objeto_match = re.search(objeto_pattern, exponen_text, re.IGNORECASE)
        if objeto_match:
            details["OBJETO"] = objeto_match.group(1).strip()
        
        # Extraer precio y condiciones de pago
        precio_total_pattern = r"(?:precio|importe).+?(\d+(?:\.\d+)?)\s*(?:EUR|EUROS?|€)"
        precio_match = re.search(precio_total_pattern, clausulas_text, re.IGNORECASE)
        if precio_match:
            details["PRECIO"] = f"{precio_match.group(1)}€"
            
            # Buscar condiciones de pago
            pago_pattern = r"serán abonados de la siguiente forma:.*?(?=\.\s+[A-ZÁÉÍÓÚÑ])"
            pago_match = re.search(pago_pattern, clausulas_text, re.IGNORECASE | re.DOTALL)
            if pago_match:
                condiciones = pago_match.group(0)
                condiciones = re.sub(r'\s+', ' ', condiciones)
                condiciones = re.sub(r'(?:[\n\r]+\s*)?-\s*', '\n- ', condiciones)
                details["CONDICIONES_PAGO"] = condiciones.strip()
        
        # Extraer plazo de garantía
        garantia_pattern = r"(?:garantía|garantiza).+?(\d+\s+(?:meses?|años?|días?)[^\.]+)"
        garantia_match = re.search(garantia_pattern, clausulas_text, re.IGNORECASE)
        if garantia_match:
            details["GARANTIA"] = garantia_match.group(1).strip()
        
        return details

    def extract_information(self, text):
        """Extrae toda la información relevante del documento."""
        
        # Normalizar el texto
        text = re.sub(r'\s+', ' ', text)
        
        # Extraer secciones principales
        reunidos_text = self._extract_section(text, "REUNIDOS")
        exponen_text = self._extract_section(text, "EXPONEN")
        clausulas_text = self._extract_section(text, "CLÁUSULAS")
        
        # Extraer información de las partes
        parties = self._extract_parties(reunidos_text)
        
        # Extraer detalles del contrato
        contract_details = self._extract_contract_details(exponen_text, clausulas_text, text)
        
        # Combinar toda la información
        result = {**parties}
        if contract_details:
            result.update(contract_details)
        
        return result

def extract_text_from_pdf(pdf_file):
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

@st.cache_resource
def get_extractor():
    return DocumentExtractor()

def main():
    st.title("Extractor de Información de Documentos Notariales")
    st.write("Esta aplicación extrae información relevante de documentos notariales.")
    
    # Sidebar para cargar archivo
    with st.sidebar:
        st.header("Cargar Documento")
        uploaded_file = st.file_uploader("Selecciona un archivo PDF", type="pdf")
    
    # Área principal
    if uploaded_file is not None:
        # Extraer texto del PDF
        text = extract_text_from_pdf(uploaded_file)
        
        # Mostrar texto extraído en un expander
        with st.expander("Ver texto extraído"):
            st.text(text)
        
        # Extraer información
        extractor = get_extractor()
        info = extractor.extract_information(text)
        
        # Mostrar resultados
        st.header("Información Extraída")
        
        # Mostrar fecha del contrato
        if "FECHA" in info:
            st.write("**Fecha del contrato:**", info["FECHA"])
        
        # Crear columnas para vendedor y comprador
        col1, col2 = st.columns(2)
        
        # Mostrar información del vendedor
        with col1:
            st.subheader("Vendedor")
            if "VENDEDOR" in info:
                vendedor = info["VENDEDOR"]
                st.write("**Nombre:**", vendedor.get("NOMBRE", "No encontrado"))
                st.write("**DNI:**", vendedor.get("DNI", "No encontrado"))
                st.write("**Dirección:**", vendedor.get("DIR", "No encontrada"))
            else:
                st.write("No se encontró información del vendedor")
        
        # Mostrar información del comprador
        with col2:
            st.subheader("Comprador")
            if "COMPRADOR" in info:
                comprador = info["COMPRADOR"]
                st.write("**Nombre:**", comprador.get("NOMBRE", "No encontrado"))
                st.write("**DNI:**", comprador.get("DNI", "No encontrado"))
                st.write("**Dirección:**", comprador.get("DIR", "No encontrada"))
            else:
                st.write("No se encontró información del comprador")
        
        # Mostrar información adicional
        st.subheader("Detalles del Contrato")
        if "OBJETO" in info:
            st.write("**Objeto del contrato:**", info["OBJETO"])
        if "PRECIO" in info:
            st.write("**Precio:**", info["PRECIO"])
            if "CONDICIONES_PAGO" in info:
                st.write("**Condiciones de pago:**")
                st.code(info["CONDICIONES_PAGO"])
        if "GARANTIA" in info:
            st.write("**Garantía:**", info["GARANTIA"])

if __name__ == "__main__":
    main()
