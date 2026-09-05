from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="SRI Web Scraper Service")

@app.get("/consultar/{ruc}")
def consultar_ruc(ruc: str):
    ruc = ruc.strip()
    
    # Validar formato Cédula / RUC
    if not re.match(r"^\d{10}(\d{3})?$", ruc):
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": "Número de RUC o Cédula no válido"
        }

    url_web = "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc"

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9",
    })

    try:
        # Paso 1: Petición GET para iniciar la sesión JSF y obtener javax.faces.ViewState
        res_get = session.get(url_web, timeout=12)
        if res_get.status_code != 200:
            return {
                "success": False,
                "ruc": ruc,
                "name": "",
                "street": "",
                "message": f"Error conectando con la vista del SRI (HTTP {res_get.status_code})"
            }

        soup_get = BeautifulSoup(res_get.text, "html.parser")
        view_state_input = soup_get.find("input", {"name": "javax.faces.ViewState"})

        if not view_state_input or not view_state_input.get("value"):
            return {
                "success": False,
                "ruc": ruc,
                "name": "",
                "street": "",
                "message": "No se pudo obtener el token ViewState de JSF."
            }

        view_state = view_state_input["value"]

        # Paso 2: Petición POST simulando la acción del botón "Consultar"
        payload = {
            "frmConsultaRuc": "frmConsultaRuc",
            "frmConsultaRuc:txtRuc": ruc,
            "frmConsultaRuc:btnConsultar": "",
            "javax.faces.ViewState": view_state
        }

        res_post = session.post(url_web, data=payload, timeout=15)
        soup_post = BeautifulSoup(res_post.text, "html.parser")

        # Paso 3: Extraer la información desde los componentes JSF/PrimeFaces
        # Intentar buscar por IDs directos de PrimeFaces o clases del HTML devuelto
        razon_social_elem = (
            soup_post.find(id=re.compile(r".*razonSocial.*")) or
            soup_post.find("span", class_="ui-outputtext")
        )
        
        # Buscar en celdas/tablas de la vista si no está en un ID directo
        nombre = ""
        direccion = ""

        # Recorremos los elementos de texto en la vista
        textos = [elem.get_text(strip=True) for elem in soup_post.find_all(["td", "span", "label"])]
        
        for i, texto in enumerate(textos):
            if "Razón Social" in texto or "Nombres" in texto:
                if i + 1 < len(textos):
                    nombre = textos[i + 1]
            if "Dirección" in texto or "Matriz" in texto:
                if i + 1 < len(textos):
                    direccion = textos[i + 1]

        # Sanitizar valores
        nombre = nombre.replace('"', '').replace("'", "").strip()
        direccion = direccion.replace('"', '').replace("'", "").strip()

        if nombre and nombre.upper() != "Razón Social".upper():
            return {
                "success": True,
                "ruc": ruc,
                "name": nombre.upper(),
                "street": direccion.upper()
            }

        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": "El RUC consultado no devolvió datos en la pantalla del SRI."
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": "Tiempo de espera agotado al consultar la web del SRI."
        }
    except Exception as e:
        return {
            "success": False,
            "ruc": ruc,
            "name": "",
            "street": "",
            "message": f"Error al procesar la vista web del SRI: {str(e)}"
        }