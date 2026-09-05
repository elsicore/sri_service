from fastapi import FastAPI
import requests
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

    # Endpoint correcto que retorna el DTO completo del contribuyente
    url = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/obtenerPorNumeroRuc?numeroRuc={ruc}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200 and response.text.strip():
            data = response.json()
            
            # Verificamos que sea un diccionario y no un booleano ni un valor nulo
            if isinstance(data, dict):
                razon_social = (
                    data.get("razonSocial") or 
                    data.get("nombreCompleto") or 
                    ""
                ).replace('"', '').replace("'", "").strip()

                nombre_comercial = (
                    data.get("nombreComercial") or ""
                ).replace('"', '').replace("'", "").strip()

                direccion = (
                    data.get("direccionMatriz") or 
                    data.get("direccionEstablecimiento") or 
                    ""
                ).replace('"', '').replace("'", "").strip()

                final_name = razon_social if razon_social else nombre_comercial

                if final_name:
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
            "message": "No se encontraron registros en el SRI para esta identificación."
        }

    except Exception as e:
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": f"Error al consultar el SRI: {str(e)}"
        }