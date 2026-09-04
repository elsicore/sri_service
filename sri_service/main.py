import logging
from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sri_scraper")

app = FastAPI(title="SRI Ecuador Scraper API")

@app.get("/consultar/{ruc}")
async def consultar_ruc(ruc: str):
    clean_ruc = str(ruc).strip()
    if len(clean_ruc) not in (10, 13):
        raise HTTPException(status_code=400, detail="Identificación inválida")

    search_ruc = clean_ruc if len(clean_ruc) == 13 else f"{clean_ruc}001"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        captured_data = {}

        async def handle_response(response):
            if any(k in response.url for k in ["rest", "Obtener", "obtener", "establecimientos"]):
                try:
                    data = await response.json()
                    if isinstance(data, dict):
                        captured_data.update(data)
                    elif isinstance(data, list) and len(data) > 0:
                        captured_data["establecimientos_list"] = data
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            await page.goto(
                "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc",
                wait_until="networkidle",
                timeout=15000
            )

            # Llenar RUC y consultar
            input_selector = 'input[type="text"], input[name="ruc"]'
            await page.wait_for_selector(input_selector, timeout=5000)
            await page.fill(input_selector, search_ruc)

            btn_selector = 'button:has-text("Consultar")'
            await page.click(btn_selector)

            # Esperar a que renderice la respuesta inicial
            await page.wait_for_timeout(2000)

            # Desplegar la tabla de establecimientos si está el botón
            try:
                btn_est = page.locator('button:has-text("Ver establecimientos"), button:has-text("Mostrar establecimientos")')
                if await btn_est.count() > 0 and await btn_est.first.is_visible():
                    await btn_est.first.click()
                    await page.wait_for_timeout(1500)
            except Exception:
                pass

            # Extraer Razón Social del DOM
            razon_social = ""
            try:
                elem = page.locator('div:has-text("Razón social") + div, .razon-social, h3')
                if await elem.count() > 0:
                    razon_social = await elem.first.inner_text()
            except Exception:
                pass

            # Extraer la Ubicación del Establecimiento desde la celda de la tabla
            ubicacion_dom = ""
            try:
                # Busca en las filas de la tabla de establecimientos
                rows = page.locator('table tr')
                row_count = await rows.count()
                for i in range(1, row_count):
                    row_text = await rows.nth(i).inner_text()
                    # Si contiene el estado ABIERTO o es la primera fila de datos
                    if "ABIERTO" in row_text or i == 1:
                        cols = rows.nth(i).locator('td')
                        if await cols.count() >= 3:
                            # La columna 3 suele ser 'Ubicación de establecimiento' (índice 2)
                            ubicacion_dom = await cols.nth(2).inner_text()
                            break
            except Exception as e:
                logger.warning(f"No se pudo extraer dirección del DOM: {str(e)}")

            await browser.close()

            # Normalizar Nombre
            final_name = (
                captured_data.get("razonSocial") or 
                captured_data.get("nombreComercial") or 
                captured_data.get("nombreCompleto") or 
                razon_social
            )

            # Normalizar Dirección (prioriza la del establecimiento extraída del DOM o API)
            final_street = ubicacion_dom.strip().replace('\n', ' ')
            if not final_street and "establecimientos_list" in captured_data:
                est = captured_data["establecimientos_list"][0]
                final_street = str(est.get("direccionCompleta") or est.get("direccion") or "").strip()

            if not final_street:
                final_street = str(captured_data.get("direccionMatriz", "")).strip()

            if final_name:
                return {
                    "success": True,
                    "ruc": clean_ruc,
                    "name": str(final_name).strip().replace('\n', ' '),
                    "street": final_street,
                }
            
            return {"success": False, "message": "No se encontraron datos en el SRI."}

        except Exception as e:
            await browser.close()
            logger.error(f"Error procesando RUC {search_ruc}: {str(e)}")
            return {"success": False, "message": f"Error conectando con el SRI: {str(e)}"}