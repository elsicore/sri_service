from fastapi import FastAPI
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

    # Endpoint plural usando el parámetro plural 'numeroRucs'
    url = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/obtenerPorNumerosRuc?numeroRucs={ruc}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://srienlinea.sri.gob.ec/"
    }

    try:
        response = requests.get(url, headers=headers, timeout=12)
        
        if response.status_code == 200 and response.text.strip():
            raw_data = response.json()
            
            # Desempaquetar lista
            data = None
            if isinstance(raw_data, list) and len(raw_data) > 0:
                data = raw_data[0]
            elif isinstance(raw_data, dict):
                data = raw_data

            if data and isinstance(data, dict):
                # 1. Razón Social principal (Prioridad)
                razon_social = (
                    data.get("razonSocial") or 
                    data.get("nombreCompleto") or 
                    ""
                ).replace('"', '').replace("'", "").strip()

                # 2. Nombre Comercial
                nombre_comercial = (
                    data.get("nombreComercial") or ""
                ).replace('"', '').replace("'", "").strip()

                # 3. Dirección Matriz
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