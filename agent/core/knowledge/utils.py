import unicodedata
import re

def normalize_key(text: str) -> str:
    """Normaliza una cadena para ser usada como key de JSON (sin tildes, ñ, espacios, etc)"""
    # 1. Quitar tildes y caracteres latinos
    text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
    # 2. Quedarse solo con alfanuméricos y guiones
    text = re.sub(r'[^a-zA-Z0-9\s_-]', '', text)
    # 3. CamelCase o snake_case?
    # Simplemente quitar espacios y mantener mayúsculas para respetar el estilo existente.
    return "".join(text.split())
