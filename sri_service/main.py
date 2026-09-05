from fastapi import FastAPI, HTTPException
import requests
import re

app = FastAPI(title="SRI Service Ecuador")

@app.get("/consultar/{ruc}")
def consultar_ruc(ruc: str):
    ruc = ruc.strip()
    
    # Validar que tenga 10 (Cedula) o 13 (RUC) digitos
    if not re.match(r"^\d{10}(\d{3})?$", ruc):
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": "Número de RUC o Cédula no válido"
        }

    # Endpoint oficial de consulta pública del SRI (Catastro Consolidado)
    url = f"https://sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/existePorNumeroRuc?numeroRuc={ruc}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }

    try:
        response = requests.get(url, headers=headers, timeout=8)
        
        if response.status_code == 200 and response.text.strip():
            data = response.json()
            
            if data:
                # 1. Mapeo jerárquico del Nombre: Razón Social -> Nombre Comercial -> Nombre Completo
                nombre = (
                    data.get("razonSocial") or 
                    data.get("nombreComercial") or 
                    data.get("nombre") or 
                    ""
                ).strip()

                # 2. Mapeo de la Dirección Matriz / Establecimiento
                direccion = (
                    data.get("direccionMatriz") or 
                    data.get("direccionEstablecimiento") or 
                    ""
                ).strip()

                # Si aún viene sin nombre pero existió en el SRI
                if not nombre:
                    # Intento secundario si la API devuelve estructura de persona natural
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