import camelot
import pandas as pd
from typing import List, Dict
import numpy as np
import logging

logger = logging.getLogger(__name__)

def extract_tables_from_pdf(pdf_bytes: bytes) -> List[Dict]:
    """
    Extrae tablas del PDF usando Camelot.
    Retorna una lista de dicts con:
    - page
    - df (pandas DataFrame)
    """
    import tempfile

    tables_data = []

    # Guardar PDF temporalmente (Camelot necesita archivo)
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()

        tables = camelot.read_pdf(tmp.name, pages="all")

        logger.info("[TABLE_EXTRACTOR] Nº tablas encontradas por Camelot: %d", len(tables))

        for idx, t in enumerate(tables):
            df_raw = t.df
            logger.info("[TABLE_EXTRACTOR] Tabla %d raw shape: %s", idx, df_raw.shape)
            logger.info("[TABLE_EXTRACTOR] Tabla %d raw head():\n%s", idx, df_raw.head())

            if df_raw.dropna(how="all").shape[0] <= 1:
                logger.info("[TABLE_EXTRACTOR] Tabla %d vacía, se ignora.", idx)
                continue
            # 👉 Limpiar celdas vacías y descartar tablas totalmente vacías
            header = df_raw.iloc[0].tolist()
            df_clean = df_raw.iloc[1:].reset_index(drop=True)
            df_clean.columns = header

            logger.info("[TABLE_EXTRACTOR] Tabla %d clean shape: %s", idx, df_clean.shape)
            logger.info("[TABLE_EXTRACTOR] Tabla %d clean head:\n%s", idx, df_clean.head())

            tables_data.append({
                "page": t.page,
                "df": df_clean,
                "index": idx,   # opcionalmente guardamos el índice
            })

    return tables_data
