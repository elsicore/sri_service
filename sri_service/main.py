import logging
from fastapi import FastAPI, HTTPException
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sri_service")

app = FastAPI(title="SRI Ecuador Fast API")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc",
    "Origin": "https://srienlinea.sri.gob.ec"
}

@app.get("/")
def home():
    return {"status": "ok", "service": "SRI Ecuador Lookup API"}

@app.get("/consultar/{ruc}")
async def consultar_ruc(ruc: str):
    clean_ruc = str(ruc).strip()
    if len(clean_ruc) not in (10, 13):
        raise HTTPException(status_code=400, detail="Identificación debe tener 10 o 13 dígitos")

    search_ruc = clean_ruc if len(clean_ruc) == 13 else f"{clean_ruc}001"
    
    # Endpoint principal REST del SRI
    url_ruc = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/existePorNumeroRuc?numeroRuc={search_ruc}"
    
    async with httpx.AsyncClient(headers=HEADERS, timeout=12.0, verify=False) as client:
        try:
            # 1. Obtener datos del contribuyente
            res_ruc = await client.get(url_ruc)
            if res_ruc.status_code != 200:
                logger.warning(f"SRI RUC HTTP status: {res_ruc.status_code}")
                return {"success": False, "message": f"El SRI no devolvió un código 200 ({res_ruc.status_code})."}

            data_ruc = res_ruc.json()
            if not data_ruc:
                return {"success": False, "message": "No se encontraron datos para la identificación ingresada."}

            razon_social = (
                data_ruc.get("razonSocial") or 
                data_ruc.get("nombreComercial") or 
                data_ruc.get("nombreCompleto") or ""
            ).strip()

            # 2. Consultar establecimientos para obtener la dirección matriz
            url_est = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/Establecimiento/consultarPorNumeroRuc?numeroRuc={search_ruc}"
            res_est = await client.get(url_est)
            
            direccion = ""
            if res_est.status_code == 200:
                try:
                    establecimientos = res_est.json()
                    if isinstance(establecimientos, list) and len(establecimientos) > 0:
                        # Buscar establecimiento matriz (tipo MAT) o el primero abierto
                        matriz = next((e for e in establecimientos if e.get("tipoEstablecimiento") == "MAT"), establecimientos[0])
                        direccion = (
                            matriz.get("direccionCompleta") or 
                            matriz.get("direccion") or 
                            f"{matriz.get('calle', '')} {matriz.get('numero', '')} {matriz.get('interseccion', '')}"
                        ).strip()
                except Exception as e:
                    logger.warning(f"Error parseando establecimientos: {e}")

            return {
                "success": True,
                "ruc": search_ruc,
                "name": razon_social,
                "street": direccion
            }

        except httpx.TimeoutException:
            logger.error(f"Timeout llamando a la API del SRI para {search_ruc}")
            return {"success": False, "message": "El servidor del SRI no respondió a tiempo (Timeout)."}
        except Exception as e:
            logger.error(f"Error en consulta SRI: {str(e)}")
            return {"success": False, "message": f"Error conectando con el SRI: {str(e)}"}