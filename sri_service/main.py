from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="SRI Web Scraper")

@app.get("/consultar/{ruc}")
def consultar_ruc_web(ruc: str):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })

    url_pantalla = "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc"

    try:
        # Paso 1: Petición GET inicial para obtener el ViewState de JSF y la Cookie
        res_init = session.get(url_pantalla, timeout=10)
        soup_init = BeautifulSoup(res_init.text, "html.parser")
        
        view_state_elem = soup_init.find("input", {"name": "javax.faces.ViewState"})
        if not view_state_elem:
            return {"success": False, "message": "No se pudo obtener el ViewState de JSF"}
            
        view_state = view_state_elem.get("value")

        # Paso 2: POST simulando el formulario JSF
        payload = {
            "frmConsultaRuc": "frmConsultaRuc",
            "frmConsultaRuc:txtRuc": ruc.strip(),
            "frmConsultaRuc:btnConsultar": "",
            "javax.faces.ViewState": view_state
        }

        res_post = session.post(url_pantalla, data=payload, timeout=10)
        soup_result = BeautifulSoup(res_post.text, "html.parser")

        # Paso 3: Parsear la tabla HTML devuelta por el SRI
        # (Aquí se extrae la Razón Social y la Matriz de los divs/tablas de PrimeFaces)
        razon_social_elem = soup_result.find(id="frmConsultaRuc:razonSocial")
        razon_social = razon_social_elem.text.strip() if razon_social_elem else ""

        return {
            "success": True if razon_social else False,
            "ruc": ruc,
            "name": razon_social.upper()
        }

    except Exception as e:
        return {"success": False, "message": f"Error parseando JSF: {str(e)}"}