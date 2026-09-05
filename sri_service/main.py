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
        # Lanzar navegador Chromium con configuraciones para evitar la detección headless
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--blink-settings=imagesEnabled=false"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            locale="es-EC"
        )

        page = await context.new_page()

        # Ocultar la propiedad navigator.webdriver
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Bloquear solo imágenes y fuentes para mejorar el rendimiento
        await page.route("**/*.{png,jpg,jpeg,svg,woff,woff2}", lambda route: route.abort())

        captured_data = {}

        # Escuchar las respuestas JSON que emite el portal en segundo plano
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
            # 1. Navegar a la página de consulta
            await page.goto(
                "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc",
                wait_until="networkidle",
                timeout=30000
            )

            # 2. Esperar el input e ingresar el RUC
            input_selector = 'input[id*="txtRuc"], input[type="text"]'
            await page.wait_for_selector(input_selector, timeout=15000)
            await page.click(input_selector)
            await page.fill(input_selector, search_ruc)

            # 3. Disparar la consulta (clic en botón o Enter)
            btn_consultar = page.locator('button:has-text("Consultar"), input[value="Consultar"]')
            if await btn_consultar.count() > 0 and await btn_consultar.first.is_visible():
                await btn_consultar.first.click()
            else:
                await page.keyboard.press("Enter")

            # Esperar a que la red procese la petición AJAX
            await page.wait_for_load_state("networkidle", timeout=10000)

            # 4. Forzar el despliegue de establecimientos si la tabla está oculta
            try:
                btn_est = page.locator('button:has-text("Ver establecimientos"), button:has-text("Mostrar establecimientos")')
                if await btn_est.count() > 0 and await btn_est.first.is_visible():
                    await btn_est.first.click()
                    await page.wait_for_timeout(1500)
            except Exception:
                pass

            # 5. Lectura de Razón Social / Nombre
            razon_social = (
                captured_data.get("razonSocial") or 
                captured_data.get("nombreCompleto") or 
                captured_data.get("nombreComercial") or ""
            )

            if not razon_social:
                # Extraer del DOM si la respuesta interceptada en red no trajo la propiedad
                labels = page.locator('.ui-outputlabel, h3, .razon-social, td')
                count = await labels.count()
                for i in range(count):
                    txt = await labels.nth(i).inner_text()
                    txt_upper = txt.strip().upper()
                    if "RAZON SOCIAL" in txt_upper or "NOMBRES" in txt_upper:
                        if i + 1 < count:
                            val = await labels.nth(i + 1).inner_text()
                            if val and "CONSULTAR" not in val.upper():
                                razon_social = val
                                break

            # 6. Lectura de la Dirección de la tabla
            ubicacion_dom = ""
            try:
                rows = page.locator('table tr')
                row_count = await rows.count()
                for i in range(row_count):
                    row_text = await rows.nth(i).inner_text()
                    if "ABIERTO" in row_text.upper():
                        cols = rows.nth(i).locator('td')
                        if await cols.count() >= 3:
                            ubicacion_dom = await cols.nth(2).inner_text()
                            break
            except Exception as e:
                logger.warning(f"No se pudo extraer dirección del DOM: {str(e)}")

            await browser.close()

            # Formatear datos de salida
            final_name = str(razon_social).strip().replace('\n', ' ')
            final_street = str(ubicacion_dom).strip().replace('\n', ' ')

            if not final_street and "establecimientos_list" in captured_data:
                est = captured_data["establecimientos_list"][0]
                final_street = str(est.get("direccionCompleta") or est.get("direccion") or "").strip()

            if final_name and "CONSULTAR INFORMACIÓN" not in final_name.upper():
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
                "message": "No se encontraron datos en la interfaz del SRI."
            }

        except Exception as e:
            await browser.close()
            logger.error(f"Error en navegador simulado para RUC {search_ruc}: {str(e)}")
            return {
                "success": False,
                "ruc": search_ruc,
                "name": "",
                "street": "",
                "message": f"Error interactuando con el navegador: {str(e)}"
            }