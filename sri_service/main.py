from fastapi import FastAPI
import requests
import re

app = FastAPI(title="SRI Service Ecuador")

@app.get("/consultar/{ruc}")
def consultar_ruc(ruc: str):
    ruc = ruc.strip()
    
    # Validar formato RUC/Cédula
    if not re.match(r"^\d{10}(\d{3})?$", ruc):
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": "Número de RUC o Cédula no válido"
        }

    # Endpoint exacto que respalda la pantalla de srienlinea
    url = f"https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/existePorNumeroRuc?numeroRuc={ruc}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200 and response.text.strip():
            raw_data = response.json()
            
            # El API del SRI retorna una lista de objetos o un objeto único
            if isinstance(raw_data, list) and len(raw_data) > 0:
                data = raw_data[0]
            elif isinstance(raw_data, dict):
                data = raw_data
            else:
                data = None

            if data:
                # 1. Extraer Razón Social principal (Persona Jurídica o Natural)
                razon_social = (
                    data.get("razonSocial") or 
                    data.get("nombreCompleto") or 
                    data.get("nombre") or 
                    ""
                )
                
                # Limpieza estricta de comillas dobles y sencillas ("PÉNTAGON" -> PÉNTAGON)
                razon_social = razon_social.replace('"', '').replace("'", "").strip()

                # 2. Nombre Comercial (del establecimiento)
                nombre_comercial = (
                    data.get("nombreComercial") or ""
                ).replace('"', '').replace("'", "").strip()

                # 3. Dirección de la Matriz / Establecimiento 001
                direccion = (
                    data.get("direccionMatriz") or 
                    data.get("direccionEstablecimiento") or 
                    ""
                ).replace('"', '').replace("'", "").strip()

                # La Razón Social siempre tiene prioridad sobre el Nombre Comercial
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