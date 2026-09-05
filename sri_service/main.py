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
        # Lanzar Chromium con configuraciones que eviten bloqueos en Render
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

        # Ocultar propiedad navigator.webdriver
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        try:
            # 1. Cargar la página
            await page.goto(
                "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc",
                wait_until="networkidle",
                timeout=30000
            )

            # 2. Escribir el RUC en el input
            input_selector = 'input[placeholder="1700000000001"], input[id*="txtRuc"], input[type="text"]'
            await page.wait_for_selector(input_selector, timeout=15000)
            await page.fill(input_selector, search_ruc)

            # 3. Hacer clic en el botón "Consultar"
            btn_consultar = page.locator('button:has-text("Consultar"), input[value="Consultar"]')
            await btn_consultar.first.click()

            # Esperar a que renderice la tarjeta con la Razón Social
            await page.wait_for_selector('text="Razón social"', timeout=15000)

            # 4. Extraer la Razón Social
            razon_social = ""
            # Buscar el bloque que contiene "Razón social" y tomar el texto continuo
            card = page.locator('div:has-text("Razón social")')
            if await card.count() > 0:
                full_text = await card.first.inner_text()
                lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                for idx, line in enumerate(lines):
                    if "RAZÓN SOCIAL" in line.upper() and idx + 1 < len(lines):
                        razon_social = lines[idx + 1]
                        break

            # 5. Hacer clic en "Mostrar establecimientos" (como en el video)
            btn_est = page.locator('button:has-text("Mostrar establecimientos")')
            direccion = ""

            if await btn_est.count() > 0 and await btn_est.first.is_visible():
                await btn_est.first.click()
                
                # Esperar a que la tabla "Establecimiento matriz" se cargue en pantalla
                await page.wait_for_selector('text="Establecimiento matriz"', timeout=10000)
                await page.wait_for_timeout(1000) # Breve pausa para asegurar el renderizado de celdas

                # 6. Extraer la Ubicación del Establecimiento Abierto / Matriz
                rows = page.locator('table tr')
                row_count = await rows.count()
                for i in range(row_count):
                    row_text = await rows.nth(i).inner_text()
                    if "ABIERTO" in row_text.upper():
                        cols = rows.nth(i).locator('td')
                        if await cols.count() >= 3:
                            # En la tabla del SRI, la 3ra columna (índice 2) contiene la ubicación/dirección
                            direccion = await cols.nth(2).inner_text()
                            break

            await browser.close()

            final_name = razon_social.strip().replace('\n', ' ')
            final_street = direccion.strip().replace('\n', ' ')

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
                "message": "No se pudieron obtener los datos completos del contribuyente."
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