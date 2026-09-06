import asyncio
import logging
import httpx
from fastapi import FastAPI, HTTPException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sri_service")

app = FastAPI(title="SRI Ecuador Fast API")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-EC,es;q=0.9",
    "Referer": "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc"
}

SRI_BASE_URL = "https://srienlinea.sri.gob.ec/sri-catastro-sujeto-pasivo-servicio-internet/rest"

@app.get("/consultar/{ruc}")
async def consultar_ruc(ruc: str):
    clean_ruc = str(ruc).strip()
    if len(clean_ruc) not in (10, 13):
        raise HTTPException(status_code=400, detail="Identificación inválida (debe tener 10 o 13 dígitos)")

    search_ruc = clean_ruc if len(clean_ruc) == 13 else f"{clean_ruc}001"

    url_contribuyente = f"{SRI_BASE_URL}/ConsolidadoContribuyente/existePorNumeroRuc?numeroRuc={search_ruc}"
    url_establecimiento = f"{SRI_BASE_URL}/Establecimiento/consultarPorNumeroRuc?numeroRuc={search_ruc}"

    async with httpx.AsyncClient(headers=HEADERS, timeout=8.0, verify=False) as client:
        try:
            # Uso correcto de asyncio.gather para concurrencia
            res_contrib, res_estab = await asyncio.gather(
                client.get(url_contribuyente),
                client.get(url_establecimiento),
                return_exceptions=True
            )

            name = ""
            street = ""

            # 1. Procesar Razón Social / Nombre
            if isinstance(res_contrib, httpx.Response) and res_contrib.status_code == 200:
                data_c = res_contrib.json()
                if isinstance(data_c, list) and len(data_c) > 0:
                    data_c = data_c[0]
                if isinstance(data_c, dict):
                    name = (
                        data_c.get("razonSocial") or 
                        data_c.get("nombreCompleto") or 
                        data_c.get("nombreComercial") or ""
                    ).strip()

            # 2. Procesar Dirección Matriz
            if isinstance(res_estab, httpx.Response) and res_estab.status_code == 200:
                data_e = res_estab.json()
                est_list = data_e if isinstance(data_e, list) else [data_e]

                for est in est_list:
                    if isinstance(est, dict):
                        prov = est.get("provincia") or ""
                        cant = est.get("canton") or ""
                        parr = est.get("parroquia") or ""
                        calle = est.get("calle") or ""
                        num = est.get("numero") or ""
                        inter = est.get("interseccion") or ""

                        parts = [str(p).strip() for p in [prov, cant, parr, calle, num, inter] 
                                 if p and str(p).strip().upper() not in ("NONE", "NULL", "0", "SN", "S/N")]

                        if parts:
                            street = " / ".join(parts)
                            break
                        elif est.get("direccionCompleta"):
                            street = str(est.get("direccionCompleta")).strip()
                            break

            if not name:
                return {
                    "success": False,
                    "ruc": search_ruc,
                    "name": "",
                    "street": "",
                    "message": "No se encontraron datos para la identificación ingresada"
                }

            return {
                "success": True,
                "ruc": search_ruc,
                "name": name,
                "street": street
            }

        except Exception as e:
            logger.error(f"Error consultando SRI API REST para {search_ruc}: {str(e)}")
            return {
                "success": False,
                "ruc": search_ruc,
                "name": "",
                "street": "",
                "message": f"Error de conexión con el SRI: {str(e)}"
            }