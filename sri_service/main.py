import logging
import requests
from fastapi import FastAPI, HTTPException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sri_scraper")

app = FastAPI(title="SRI Ecuador API")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
        # 1. Warm-up: Obtener cookies de sesión del SRI para evitar bloqueo 403 / respuesta vacía
        try:
            session.get(
                "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc",
                timeout=5
            )
        except Exception:
            pass

        # 2. Consultar la API de Contribuyente
        url_contrib = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/existePorNumeroRuc?numeroRuc={search_ruc}"
        resp_contrib = session.get(url_contrib, timeout=10)

        name = ""
        if resp_contrib.status_code == 200:
            data = resp_contrib.json()
            if isinstance(data, dict):
                name = (
                    data.get("razonSocial") or 
                    data.get("nombreCompleto") or 
                    data.get("nombreComercial") or ""
                )
            elif isinstance(data, list) and len(data) > 0:
                first = data[0]
                if isinstance(first, dict):
                    name = (
                        first.get("razonSocial") or 
                        first.get("nombreCompleto") or 
                        first.get("nombreComercial") or ""
                    )

        # 3. Consultar Establecimientos para extraer Dirección
        url_est = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/Establecimiento/consultarPorNumeroRuc?numeroRuc={search_ruc}"
        resp_est = session.get(url_est, timeout=10)

        street = ""
        if resp_est.status_code == 200:
            data_est = resp_est.json()
            if isinstance(data_est, list) and len(data_est) > 0:
                # Priorizar establecimiento Matriz o Abierto
                matriz = next(
                    (e for e in data_est if e.get("tipoEstablecimiento") == "MAT" or e.get("estado") == "ABI"),
                    data_est[0]
                )
                
                # Si no obtuvimos el nombre arriba, intentar sacarlo del nombre comercial del establecimiento
                if not name and matriz.get("nombreComercial"):
                    name = matriz.get("nombreComercial")

                # Armar dirección limpia
                prov = matriz.get("provincia") or ""
                cant = matriz.get("canton") or ""
                parr = matriz.get("parroquia") or ""
                calle = matriz.get("calle") or ""
                num = matriz.get("numero") or ""
                inter = matriz.get("interseccion") or ""

                parts = [p.strip() for p in [prov, cant, parr, calle, num, inter] if p and str(p).strip().upper() not in ("NONE", "NULL")]
                street = " / ".join(parts)

                if not street:
                    street = str(matriz.get("direccionCompleta") or matriz.get("direccion") or "").strip()

        if name:
            return {
                "success": True,
                "ruc": search_ruc,
                "name": str(name).strip(),
                "street": str(street).strip()
            }

        return {
            "success": False,
            "ruc": search_ruc,
            "name": "",
            "street": "",
            "message": "No se encontraron registros para el RUC ingresado."
        }

    except Exception as e:
        logger.error(f"Error consultando SRI API: {str(e)}")
        return {
            "success": False,
            "ruc": search_ruc,
            "name": "",
            "street": "",
            "message": f"Error de conexión con el SRI: {str(e)}"
        }