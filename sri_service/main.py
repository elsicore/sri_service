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
    "Origin": "https://srienlinea.sri.gob.ec",
    "Referer": "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc"
}

SRI_BASE_URL = "https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest"

@app.get("/consultar/{ruc}")
async def consultar_ruc(ruc: str):
    clean_ruc = str(ruc).strip()
    if len(clean_ruc) not in (10, 13):
        raise HTTPException(status_code=400, detail="Identificación inválida (debe ser 10 o 13 dígitos)")

    # Construir RUC objetivo para probar RUC
    search_ruc = clean_ruc if len(clean_ruc) == 13 else f"{clean_ruc}001"

    url_contribuyente = f"{SRI_BASE_URL}/ConsolidadoContribuyente/obtenerPorNumerosRuc?ruc={search_ruc}"
    url_establecimiento = f"{SRI_BASE_URL}/Establecimiento/consultarPorNumeroRuc?numeroRuc={search_ruc}"
    url_persona = f"{SRI_BASE_URL}/Persona/obtenerPorIdentificacion?identificacion={clean_ruc[:10]}"

    async with httpx.AsyncClient(headers=HEADERS, timeout=10.0, verify=False) as client:
        try:
            # 1. Intento inicial: Consultar Catastro de RUC
            res_contrib, res_estab = await asyncio.gather(
                client.get(url_contribuyente),
                client.get(url_establecimiento),
                return_exceptions=True
            )

            name = ""
            street = ""

            # Extraer Nombre del RUC
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

            # Extraer Dirección del RUC
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

                        parts = [
                            str(p).strip() for p in [prov, cant, parr, calle, num, inter] 
                            if p and str(p).strip().upper() not in ("NONE", "NULL", "0", "SN", "S/N")
                        ]

                        if parts:
                            street = " / ".join(parts)
                            break
                        elif est.get("direccionCompleta"):
                            street = str(est.get("direccionCompleta")).strip()
                            break

            # 2. Fallback para Cédula (si no se encontró registro como RUC)
            if not name:
                logger.info(f"Buscando {clean_ruc[:10]} en catálogo de Persona / Cédulas...")
                res_persona = await client.get(url_persona)
                if res_persona.status_code == 200:
                    data_p = res_persona.json()
                    if isinstance(data_p, list) and len(data_p) > 0:
                        data_p = data_p[0]
                    if isinstance(data_p, dict):
                        name = (
                            data_p.get("nombreCompleto") or 
                            f"{data_p.get('apellidos', '')} {data_p.get('nombres', '')}"
                        ).strip()

            # Si ni como RUC ni como Cédula existe registro:
            if not name:
                return {
                    "success": False,
                    "ruc": clean_ruc,
                    "name": "",
                    "street": "",
                    "message": "No se encontraron registros para la identificación ingresada."
                }

            return {
                "success": True,
                "ruc": clean_ruc,
                "name": name,
                "street": street
            }

        except Exception as e:
            logger.error(f"Error procesando la identificación {clean_ruc}: {str(e)}")
            return {
                "success": False,
                "ruc": clean_ruc,
                "name": "",
                "street": "",
                "message": f"Error de comunicación con el SRI: {str(e)}"
            }