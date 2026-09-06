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

        api_direccion = ""
        api_razon_social = ""

        # 1. Interceptar peticiones de red (captura background de datos del SRI)
        async def intercept_response(response):
            nonlocal api_direccion, api_razon_social
            url_lower = response.url.lower()

            if "establecimiento" in url_lower:
                try:
                    res_json = await response.json()
                    est_list = res_json if isinstance(res_json, list) else [res_json]
                    
                    for est in est_list:
                        if isinstance(est, dict):
                            # Construir la dirección con las partes disponibles
                            prov = est.get("provincia") or ""
                            cant = est.get("canton") or ""
                            parr = est.get("parroquia") or ""
                            calle = est.get("calle") or ""
                            num = est.get("numero") or ""
                            inter = est.get("interseccion") or ""

                            parts = [str(p).strip() for p in [prov, cant, parr, calle, num, inter] 
                                     if p and str(p).strip().upper() not in ("NONE", "NULL", "0")]
                            
                            if parts:
                                api_direccion = " / ".join(parts)
                                break
                            elif est.get("direccionCompleta"):
                                api_direccion = str(est.get("direccionCompleta")).strip()
                                break
                            elif est.get("direccion"):
                                api_direccion = str(est.get("direccion")).strip()
                                break
                except Exception:
                    pass

            if "contribuyente" in url_lower:
                try:
                    res_json = await response.json()
                    c_data = res_json[0] if isinstance(res_json, list) and len(res_json) > 0 else res_json
                    if isinstance(c_data, dict):
                        api_razon_social = (
                            c_data.get("razonSocial") or 
                            c_data.get("nombreCompleto") or 
                            c_data.get("nombreComercial") or ""
                        )
                except Exception:
                    pass

        page.on("response", intercept_response)

        try:
            # 2. Navegar a la página
            await page.goto(
                "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc",
                wait_until="domcontentloaded",
                timeout=30000
            )

            # 3. Llenar e ingresar RUC
            input_selector = 'input[placeholder="1700000000001"], input[id*="txtRuc"], input[type="text"]'
            await page.wait_for_selector(input_selector, timeout=20000)
            await page.fill(input_selector, search_ruc)

            btn_consultar = page.locator('button:has-text("Consultar"), input[value="Consultar"]')
            await btn_consultar.first.click()

            await page.wait_for_selector('text=Razón social', timeout=15000)

            # 4. Extraer Razón Social del DOM si la red no lo tomó
            razon_social = api_razon_social
            if not razon_social:
                card = page.locator('div:has-text("Razón social")')
                if await card.count() > 0:
                    full_text = await card.first.inner_text()
                    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                    for idx, line in enumerate(lines):
                        if "RAZÓN SOCIAL" in line.upper() and idx + 1 < len(lines):
                            razon_social = lines[idx + 1]
                            break

            # 5. Clic en "Mostrar establecimientos"
            btn_est = page.locator('button:has-text("Mostrar establecimientos")')
            if await btn_est.count() > 0 and await btn_est.first.is_visible():
                await btn_est.first.click()
                await page.wait_for_timeout(2000)  # Dar tiempo a que cargue la tabla y la red

            # 6. Extraer Dirección de la tabla en el DOM si la red falló
            direccion_dom = api_direccion
            if not direccion_dom:
                # Buscar todas las celdas de las tablas que contengan la provincia/ciudad (en mayúsculas con comarcas)
                cells = page.locator('table tr td')
                cell_count = await cells.count()
                for i in range(cell_count):
                    text = await cells.nth(i).inner_text()
                    text_clean = text.strip()
                    # Las direcciones en el SRI contienen barras `/` separando provincia / cantón / parroquia / calle
                    if "/" in text_clean and len(text_clean) > 10:
                        direccion_dom = text_clean
                        break

            await browser.close()

            final_name = str(razon_social).strip().replace('\n', ' ')
            final_street = str(direccion_dom).strip().replace('\n', ' ')

            return {
                "success": True,
                "ruc": search_ruc,
                "name": final_name,
                "street": final_street
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