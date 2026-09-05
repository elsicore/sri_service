from fastapi import FastAPI
import requests
import re

app = FastAPI(title="SRI Service Ecuador")

@app.get("/consultar/{ruc}")
def consultar_ruc(ruc: str):
    ruc = ruc.strip()
    
    # Validar formato: Cédula (10 dígitos) o RUC (13 dígitos)
    if not re.match(r"^\d{10}(\d{3})?$", ruc):
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": "Número de RUC o Cédula no válido"
        }

    # Endpoint oficial del catastro en srienlinea
    url = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/obtenerPorNumerosRuc?numeroRuc={ruc}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://srienlinea.sri.gob.ec/"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200 and response.text.strip():
            raw_data = response.json()
            
            # Desempaquetar lista si viene con elementos
            data = None
            if isinstance(raw_data, list) and len(raw_data) > 0:
                data = raw_data[0]
            elif isinstance(raw_data, dict):
                data = raw_data

            if data and isinstance(data, dict):
                # Extraer y sanitizar comillas de la Razón Social / Nombre Completo
                nombre = (
                    data.get("razonSocial") or 
                    data.get("nombreComercial") or 
                    data.get("nombre") or 
                    ""
                ).replace('"', '').replace("'", "").strip()

                # Extraer y sanitizar la dirección
                direccion = (
                    data.get("direccionMatriz") or 
                    data.get("direccionEstablecimiento") or 
                    ""
                ).replace('"', '').replace("'", "").strip()

                if not nombre:
                    clase = data.get("claseContribuyente", "")
                    nombre = f"CONTRIBUYENTE SRI ({clase})" if clase else "CONTRIBUYENTE SRI"

                return {
                    "success": True,
                    "ruc": ruc,
                    "name": nombre.upper(),
                    "street": direccion.upper()
                }

        # Si el SRI respondió pero la lista vino vacía o con estatus diferente a 200
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": "No se encontraron registros en el SRI para esta identificación."
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": "Tiempo de espera agotado al conectar con el SRI"
        }
    except Exception as e:
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": f"Error en el servicio SRI: {str(e)}"
        }