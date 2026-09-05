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
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage",
                "--blink-settings=imagesEnabled=false"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Bloquear solo imágenes y fuentes
        await page.route("**/*.{png,jpg,jpeg,svg,woff,woff2}", lambda route: route.abort())

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
                wait_until="domcontentloaded",
                timeout=25000
            )

            # 1. Llenar campo RUC
            input_selector = 'input[id*="txtRuc"], input[type="text"]'
            await page.wait_for_selector(input_selector, timeout=15000)
            await page.fill(input_selector, search_ruc)

            # 2. Hacer clic en Consultar
            btn_consultar = page.locator('button:has-text("Consultar"), input[value="Consultar"]')
            if await btn_consultar.count() > 0:
                await btn_consultar.first.click()
            else:
                await page.keyboard.press("Enter")

            # Esperar a que cargue la información
            await page.wait_for_timeout(3000)

            # 3. Extraer Nombre / Razón Social real
            razon_social = ""
            # Intentar primero desde respuestas JSON de red
            razon_social = (
                captured_data.get("razonSocial") or 
                captured_data.get("nombreCompleto") or 
                captured_data.get("nombreComercial") or ""
            )

            # Si no vino en red, extraer del DOM filtrando textos estáticos de la interfaz
            if not razon_social:
                labels = page.locator('span, div, label')
                count = await labels.count()
                for i in range(count):
                    txt = await labels.nth(i).inner_text()
                    txt_clean = txt.strip()
                    if "RAZON SOCIAL" in txt_clean.upper() or "NOMBRES" in txt_clean.upper():
                        # Obtener el valor contiguo o siguiente
                        if i + 1 < count:
                            val = await labels.nth(i + 1).inner_text()
                            if val and "CONSULTAR" not in val.upper() and len(val) > 3:
                                razon_social = val
                                break

            # 4. Desplegar la tabla de establecimientos si no está visible
            btn_est = page.locator('button:has-text("Ver establecimientos"), button:has-text("Mostrar establecimientos")')
            if await btn_est.count() > 0 and await btn_est.first.is_visible():
                await btn_est.first.click()
                await page.wait_for_timeout(2000)

            # 5. Extraer Dirección desde la tabla "Ubicación de establecimiento"
            ubicacion_dom = ""
            try:
                # Selector enfocado en la tabla de establecimientos visible en tu imagen
                rows = page.locator('table tr')
                row_count = await rows.count()
                for i in range(row_count):
                    row_text = await rows.nth(i).inner_text()
                    if "ABIERTO" in row_text.upper():
                        cols = rows.nth(i).locator('td')
                        col_count = await cols.count()
                        if col_count >= 3:
                            # La columna 3 (índice 2) contiene la ubicación
                            ubicacion_dom = await cols.nth(2).inner_text()
                            break
            except Exception as e:
                logger.warning(f"No se pudo extraer dirección del DOM: {str(e)}")

            await browser.close()

            # Sanitización de variables finales
            final_name = str(razon_social).strip().replace('\n', ' ')
            
            final_street = ubicacion_dom.strip().replace('\n', ' ')
            if not final_street and "establecimientos_list" in captured_data:
                est = captured_data["establecimientos_list"][0]
                final_street = str(est.get("direccionCompleta") or est.get("direccion") or "").strip()

            if not final_street:
                final_street = str(captured_data.get("direccionMatriz", "")).strip()

            if final_name and final_name.upper() != "CONSULTAR INFORMACIÓN DEL CONTRIBUYENTE":
                return {
                    "success": True,
                    "ruc": clean_ruc,
                    "name": final_name,
                    "street": final_street
                }
            
            return {
                "success": False, 
                "ruc": clean_ruc,
                "name": "",
                "street": "",
                "message": "No se pudieron obtener los datos completos del contribuyente."
            }

        except Exception as e:
            await browser.close()
            logger.error(f"Error procesando RUC {search_ruc}: {str(e)}")
            return {
                "success": False, 
                "ruc": clean_ruc,
                "name": "",
                "street": "",
                "message": f"Error conectando con el SRI: {str(e)}"
            }