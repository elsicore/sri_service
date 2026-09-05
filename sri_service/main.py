from fastapi import FastAPI, HTTPException
import requests
import re

app = FastAPI(title="SRI Service Ecuador")

@app.get("/consultar/{ruc}")
def consultar_ruc(ruc: str):
    ruc = ruc.strip()
    
    # Validar que tenga 10 (Cédula) o 13 (RUC) dígitos
    if not re.match(r"^\d{10}(\d{3})?$", ruc):
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": "Número de RUC o Cédula no válido"
        }

    # Endpoint oficial activo del SRI en Línea (con subdominio srienlinea)
    url = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/obtenerPorNumerosRuc?numeroRuc={ruc}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://srienlinea.sri.gob.ec/"
    }

    try:
        response = requests.get(url, headers=headers, timeout=8)
        
        if response.status_code == 200 and response.text.strip():
            raw_data = response.json()
            
            # El SRI devuelve una lista de objetos: extraemos la primera posición
            if isinstance(raw_data, list) and len(raw_data) > 0:
                data = raw_data[0]
            elif isinstance(raw_data, dict):
                data = raw_data
            else:
                data = None
            
            if data and isinstance(data, dict):
                # 1. Mapeo jerárquico del Nombre (Priorizando Razón Social sobre Comercial)
                # Se eliminan comillas dobles y simples para no romper el cliente de Odoo
                nombre = (
                    data.get("razonSocial") or 
                    data.get("nombreComercial") or 
                    data.get("nombre") or 
                    ""
                ).replace('"', '').replace("'", "").strip()

                # 2. Mapeo de la Dirección Matriz / Establecimiento
                direccion = (
                    data.get("direccionMatriz") or 
                    data.get("direccionEstablecimiento") or 
                    ""
                ).replace('"', '').replace("'", "").strip()

                # Si aún viene sin nombre pero existió en el SRI
                if not nombre:
                    clase = data.get("claseContribuyente", "")
                    nombre = f"CONTRIBUYENTE SRI ({clase})" if clase else "CONTRIBUYENTE SRI"

                return {
                    "success": True,
                    "ruc": ruc,
                    "name": nombre.upper(),
                    "street": direccion.upper()
                }

        # Si el SRI no devuelve datos o status != 200
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": "No se encontraron registros en el SRI para la identificación ingresada"
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