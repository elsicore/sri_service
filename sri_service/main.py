import logging
import re
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
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="es-EC"
        )

        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Captura de datos en red como respaldo
        api_data = {}

        async def intercept_response(response):
            if "Establecimiento/consultarPorNumeroRuc" in response.url:
                try:
                    res_json = await response.json()
                    if isinstance(res_json, list) and len(res_json) > 0:
                        api_data["establecimientos"] = res_json
                except Exception:
                    pass
            elif "ConsolidadoContribuyente/existePorNumeroRuc" in response.url:
                try:
                    res_json = await response.json()
                    if isinstance(res_json, dict):
                        api_data["contribuyente"] = res_json
                except Exception:
                    pass

        page.on("response", intercept_response)

        try:
            # 1. Cargar la página del SRI
            await page.goto(
                "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc",
                wait_until="domcontentloaded",
                timeout=30000
            )

            # 2. Escribir RUC
            input_selector = 'input[placeholder="1700000000001"], input[id*="txtRuc"], input[type="text"]'
            await page.wait_for_selector(input_selector, timeout=20000)
            await page.fill(input_selector, search_ruc)

            # 3. Clic en "Consultar"
            btn_consultar = page.locator('button:has-text("Consultar"), input[value="Consultar"]')
            await btn_consultar.first.click()

            # Validar si apareció el bloque de resultados
            try:
                await page.wait_for_selector('text=Razón social', timeout=15000)
            except Exception:
                logger.warning("No se detectó la etiqueta 'Razón social' en el tiempo estándar.")

            # 4. Extraer Razón Social desde el DOM
            razon_social = ""
            if "contribuyente" in api_data:
                c_data = api_data["contribuyente"]
                razon_social = c_data.get("razonSocial") or c_data.get("nombreCompleto") or c_data.get("nombreComercial") or ""

            if not razon_social:
                card = page.locator('div:has-text("Razón social")')
                if await card.count() > 0:
                    full_text = await card.first.inner_text()
                    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                    for idx, line in enumerate(lines):
                        if "RAZÓN SOCIAL" in line.upper() and idx + 1 < len(lines):
                            razon_social = lines[idx + 1]
                            break

            # 5. Clic en "Mostrar establecimientos" con reintentos
            btn_est = page.locator('button:has-text("Mostrar establecimientos")')
            if await btn_est.count() > 0 and await btn_est.first.is_visible():
                await btn_est.first.click()

            # 6. Esperar la tabla con selector flexible (Regex)
            # Acepta que aparezca "Establecimiento", "MATRIZ", "ABIERTO" o la etiqueta de la tabla
            table_found = False
            try:
                await page.wait_for_selector(
                    'table, text=/Establecimiento|MATRIZ|ABIERTO/i',
                    timeout=15000
                )
                table_found = True
            except Exception:
                logger.warning("Timeout esperando renderizado del DOM para la tabla. Verificando red...")

            # 7. Extraer la Dirección
            direccion = ""

            # Intento A: Desde los datos capturados en red (Respaldo super rápido)
            if "establecimientos" in api_data:
                for est in api_data["establecimientos"]:
                    if est.get("estado") == "ABI" or est.get("tipoEstablecimiento") == "MAT":
                        prov = est.get("provincia") or ""
                        cant = est.get("canton") or ""
                        parr = est.get("parroquia") or ""
                        calle = est.get("calle") or ""
                        num = est.get("numero") or ""
                        inter = est.get("interseccion") or ""

                        parts = [p.strip() for p in [prov, cant, parr, calle, num, inter] if p and str(p).strip().upper() not in ("NONE", "NULL")]
                        direccion = " / ".join(parts)
                        if not direccion:
                            direccion = str(est.get("direccionCompleta") or est.get("direccion") or "").strip()
                        if direccion:
                            break

            # Intento B: Si la red no capturó, parsear la tabla visible en la pantalla
            if not direccion and table_found:
                rows = page.locator('table tr')
                row_count = await rows.count()
                for i in range(row_count):
                    row_text = await rows.nth(i).inner_text()
                    if "ABIERTO" in row_text.upper():
                        cols = rows.nth(i).locator('td')
                        if await cols.count() >= 3:
                            direccion = await cols.nth(2).inner_text()
                            break

            await browser.close()

            final_name = str(razon_social).strip().replace('\n', ' ')
            final_street = str(direccion).strip().replace('\n', ' ')

            if final_name:
                return {
                    "success": True,
                    "ruc": search_ruc,
                    "name": final_name,
                    "street": final_street
                }

            return {
                "success": False,
                "ruc": search_ruc,
                "name": "",
                "street": "",
                "message": "No se encontraron registros para el RUC ingresado."
            }

        except Exception as e:
            await browser.close()
            logger.error(f"Error scraping SRI para RUC {search_ruc}: {str(e)}")
            return {
                "success": False,
                "ruc": search_ruc,
                "name": "",
                "street": "",
                "message": f"Error interactuando con el navegador: {str(e)}"
            }