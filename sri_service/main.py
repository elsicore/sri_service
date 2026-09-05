import logging
import requests
from fastapi import FastAPI, HTTPException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sri_scraper")

app = FastAPI(title="SRI Ecuador API")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9",
    "Origin": "https://srienlinea.sri.gob.ec",
    "Referer": "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc"
}

@app.get("/consultar/{ruc}")
def consultar_ruc(ruc: str):
    clean_ruc = str(ruc).strip()
    if len(clean_ruc) not in (10, 13):
        raise HTTPException(status_code=400, detail="Identificación inválida")

    search_ruc = clean_ruc if len(clean_ruc) == 13 else f"{clean_ruc}001"

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        # 1. Consultar Datos del Contribuyente
        url_contribuyente = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/existePorNumeroRuc?numeroRuc={search_ruc}"
        resp_contrib = session.get(url_contribuyente, timeout=10)

        name = ""
        if resp_contrib.status_code == 200:
            data_contrib = resp_contrib.json()
            if isinstance(data_contrib, dict):
                name = (
                    data_contrib.get("razonSocial") or 
                    data_contrib.get("nombreCompleto") or 
                    data_contrib.get("nombreComercial") or ""
                )

        # 2. Consultar Establecimientos para obtener la Dirección
        url_est = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/Establecimiento/consultarPorNumeroRuc?numeroRuc={search_ruc}"
        resp_est = session.get(url_est, timeout=10)

        street = ""
        if resp_est.status_code == 200:
            data_est = resp_est.json()
            if isinstance(data_est, list) and len(data_est) > 0:
                # Buscar el establecimiento matriz o el primero abierto
                matriz = next((e for e in data_est if e.get("tipoEstablecimiento") == "MAT" or e.get("estado") == "ABI"), data_est[0])
                
                direccion_parts = [
                    matriz.get("provincia"),
                    matriz.get("canton"),
                    matriz.get("parroquia"),
                    matriz.get("calle"),
                    matriz.get("numero"),
                    matriz.get("interseccion")
                ]
                # Filtrar valores nulos y concatenar
                street = " / ".join([str(p).strip() for p in direccion_parts if p and str(p).strip() != "None"])
                if not street:
                    street = str(matriz.get("direccionCompleta") or matriz.get("direccion") or "").strip()

        if name:
            return {
                "success": True,
                "ruc": clean_ruc,
                "name": str(name).strip(),
                "street": str(street).strip()
            }

        return {
            "success": False,
            "ruc": clean_ruc,
            "name": "",
            "street": "",
            "message": "No se encontraron registros para el RUC ingresado."
        }

    except Exception as e:
        logger.error(f"Error consultando SRI API: {str(e)}")
        return {
            "success": False,
            "ruc": clean_ruc,
            "name": "",
            "street": "",
            "message": f"Error de conexión con el SRI: {str(e)}"
        }