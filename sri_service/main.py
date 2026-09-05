from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="SRI Service Ecuador")

@app.get("/consultar/{ruc}")
def consultar_ruc(ruc: str):
    ruc = ruc.strip()
    
    if not re.match(r"^\d{10}(\d{3})?$", ruc):
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": "Número de RUC o Cédula no válido"
        }

    # URL pública de consulta del SRI
    url = f"https://sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/existePorNumeroRuc?numeroRuc={ruc}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200 and response.text.strip():
            data = response.json()
            
            if data:
                # 1. Razón Social estricta (Prioridad a la ficha general)
                # No tomamos 'nombreComercial' como 'name' principal
                razon_social = (
                    data.get("razonSocial") or 
                    data.get("nombreCompleto") or 
                    data.get("nombre") or 
                    ""
                ).strip()

                # Sanitizar comillas dobles que rompen la respuesta JSON
                razon_social = razon_social.replace('"', '').replace("'", "")

                # 2. Nombre Comercial (si existe)
                nombre_comercial = (data.get("nombreComercial") or "").replace('"', '').strip()

                # 3. Dirección de la Matriz (Establecimiento 001)
                direccion = (
                    data.get("direccionMatriz") or 
                    data.get("direccionEstablecimiento") or 
                    ""
                ).replace('"', '').strip()

                # Fallback en caso de que razón social venga vacía
                final_name = razon_social if razon_social else nombre_comercial

                return {
                    "success": True,
                    "ruc": ruc,
                    "name": final_name.upper(),
                    "commercial_name": nombre_comercial.upper(),
                    "street": direccion.upper()
                }

        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": "No se encontraron registros en el SRI"
        }

    except Exception as e:
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": f"Error en la consulta: {str(e)}"
        }