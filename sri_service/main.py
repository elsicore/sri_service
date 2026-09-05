import logging
from fastapi import FastAPI, HTTPException
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sri_service")

app = FastAPI(title="SRI Ecuador Fast API")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9",
    "Origin": "https://srienlinea.sri.gob.ec",
    "Referer": "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc"
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
    
    # Endpoints del SRI
    url_completo = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ContribuyenteCompleto/consultarPorRuc/{search_ruc}"
    url_est = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/Establecimiento/consultarPorNumeroRuc?numeroRuc={search_ruc}"
    url_consolidado = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/obtenerPorNumeroRuc?numeroRuc={search_ruc}"

    async with httpx.AsyncClient(headers=HEADERS, timeout=12.0, verify=False) as client:
        try:
            razon_social = ""
            direccion = ""

            # 1. Intentar con el endpoint de ContribuyenteCompleto (El más fiable para Razón Social)
            try:
                res_comp = await client.get(url_completo)
                if res_comp.status_code == 200:
                    data_comp = res_comp.json()
                    if isinstance(data_comp, dict):
                        razon_social = (
                            data_comp.get("razonSocial") or 
                            data_comp.get("nombreComercial") or 
                            data_comp.get("nombreCompleto") or ""
                        ).strip()
            except Exception as e:
                logger.warning(f"Error en ContribuyenteCompleto: {e}")

            # 2. Consultar Establecimientos (para obtener la dirección Matriz y fallback de nombre)
            try:
                res_est = await client.get(url_est)
                if res_est.status_code == 200:
                    establecimientos = res_est.json()
                    if isinstance(establecimientos, list) and len(establecimientos) > 0:
                        matriz = next((e for e in establecimientos if e.get("tipoEstablecimiento") == "MAT"), establecimientos[0])
                        
                        # Si no conseguimos la razón social antes, la sacamos del establecimiento
                        if not razon_social:
                            razon_social = (
                                matriz.get("nombreFantasiaComercial") or 
                                matriz.get("nombreComercial") or 
                                matriz.get("razonSocial") or ""
                            ).strip()

                        direccion = (
                            matriz.get("direccionCompleta") or 
                            matriz.get("direccion") or 
                            f"{matriz.get('calle', '')} {matriz.get('numero', '')} {matriz.get('interseccion', '')}"
                        ).strip()
            except Exception as e:
                logger.warning(f"Error en Establecimientos: {e}")

            # 3. Tercer fallback si aún no hay nombre (ConsolidadoContribuyente)
            if not razon_social:
                try:
                    res_cons = await client.get(url_consolidado)
                    if res_cons.status_code == 200:
                        data_cons = res_cons.json()
                        if isinstance(data_cons, dict):
                            razon_social = (
                                data_cons.get("razonSocial") or 
                                data_cons.get("nombreComercial") or ""
                            ).strip()
                except Exception as e:
                    logger.warning(f"Error en ConsolidadoContribuyente: {e}")

            if razon_social or direccion:
                return {
                    "success": True,
                    "ruc": search_ruc,
                    "name": razon_social,
                    "street": direccion
                }

            return {"success": False, "message": "No se encontraron datos para la identificación ingresada."}

        except httpx.TimeoutException:
            logger.error(f"Timeout llamando a la API del SRI para {search_ruc}")
            return {"success": False, "message": "El servidor del SRI no respondió a tiempo (Timeout)."}
        except Exception as e:
            logger.error(f"Error en consulta SRI: {str(e)}")
            return {"success": False, "message": f"Error conectando con el SRI: {str(e)}"}