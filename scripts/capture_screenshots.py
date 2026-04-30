"""
Captura screenshots do dashboard Streamlit com dados sintéticos.

Uso:
    python scripts/capture_screenshots.py

Requer:
    pip install playwright
    python -m playwright install chromium
"""
import subprocess
import sys
import time
import zipfile
import tempfile
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


STREAMLIT_PORT = 8765
STREAMLIT_URL = f"http://localhost:{STREAMLIT_PORT}"

# Where to save screenshots
OUT_DIR = Path(__file__).parent.parent / "docs" / "screenshots"

# Synthetic ZIP created by generate_synthetic_pdfs.py
ZIP_PATH = Path(__file__).parent / "synthetic_data" / "exames_sinteticos.zip"


def start_streamlit() -> subprocess.Popen:
    dashboard = Path(__file__).parent.parent / "src" / "dashboard.py"
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(dashboard),
         "--server.port", str(STREAMLIT_PORT),
         "--server.headless", "true",
         "--server.fileWatcherType", "none",
         "--global.developmentMode", "false"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    # Wait for Streamlit to be ready
    print("  Aguardando Streamlit inicializar...", end="", flush=True)
    for _ in range(30):
        time.sleep(1)
        print(".", end="", flush=True)
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"Streamlit encerrou inesperadamente:\n{err.decode()}")
        # Try to reach it
        try:
            import urllib.request
            urllib.request.urlopen(STREAMLIT_URL, timeout=2)
            break
        except Exception:
            pass
    print(" pronto!")
    return proc


def capture(page, path: Path, full_page=True) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  Salvo: {path.relative_to(Path(__file__).parent.parent)}")


def click_tab(page, partial_text: str) -> None:
    """Click a Streamlit tab by partial text match."""
    # Streamlit tabs use role=tab
    page.get_by_role("tab").filter(has_text=partial_text).first.click()
    time.sleep(1.5)


def select_exam(page, exam_name: str) -> None:
    """Select an exam in the st.selectbox inside tab4."""
    # Open the selectbox
    selectbox = page.locator("[data-testid='stSelectbox']").first
    selectbox.click()
    time.sleep(0.5)
    # The dropdown options appear in a listbox
    page.get_by_role("option", name=exam_name).click()
    time.sleep(1.5)


def main():
    print("Gerando PDFs sintéticos...")
    import importlib.util, types

    gen_path = Path(__file__).parent / "generate_synthetic_pdfs.py"
    spec = importlib.util.spec_from_file_location("gen_pdfs", gen_path)
    gen_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen_mod)
    gen_mod.main()

    print("\nIniciando Streamlit...")
    proc = start_streamlit()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()

            # ── 1. Tela inicial (sem dados)
            print("\n[1/6] Tela inicial...")
            page.goto(STREAMLIT_URL, wait_until="networkidle", timeout=30_000)
            time.sleep(2)
            capture(page, OUT_DIR / "01_tela_inicial.png")

            # ── 2. Upload + barra de progresso
            print("\n[2/6] Upload + progresso...")
            page.goto(STREAMLIT_URL, wait_until="networkidle", timeout=30_000)
            time.sleep(1)

            # Upload ZIP
            file_input = page.locator("input[type='file']")
            file_input.set_input_files(str(ZIP_PATH))
            time.sleep(1.5)

            # Screenshot with file selected (before processing)
            capture(page, OUT_DIR / "02a_arquivo_selecionado.png", full_page=False)

            # Click "Processar" button — use filter for reliability
            processar_btn = page.locator("button").filter(has_text="Processar").first
            processar_btn.click()
            print("  Botão Processar clicado")
            time.sleep(0.8)

            # Try to capture progress bar
            for _ in range(20):
                time.sleep(0.3)
                try:
                    page.locator("[data-testid='stProgress']").wait_for(timeout=200)
                    capture(page, OUT_DIR / "02b_progresso.png", full_page=False)
                    print("  Barra de progresso capturada")
                    break
                except PWTimeout:
                    pass

            # Wait for success message (✅ arquivo(s)) OR tabs to appear
            print("  Aguardando conclusão do processamento...", end="", flush=True)
            done = False
            for _ in range(90):
                time.sleep(1)
                print(".", end="", flush=True)
                try:
                    # Look for success indicator (arquivo(s) text) or tabs
                    page.locator("text=arquivo(s)").first.wait_for(timeout=400)
                    done = True
                    break
                except PWTimeout:
                    pass
                try:
                    page.get_by_role("tab").first.wait_for(timeout=400)
                    done = True
                    break
                except PWTimeout:
                    pass
            print(f" {'ok!' if done else 'timeout — continuando mesmo assim'}")

            # Debug screenshot: see what's on screen
            capture(page, OUT_DIR / "_debug_apos_processamento.png")

            if not done:
                print("  AVISO: Processamento pode não ter concluído. Verifique _debug_apos_processamento.png")

            time.sleep(1)

            # ── 3. Aba Evolução por Exame
            print("\n[3/6] Aba Evolução por Exame...")
            try:
                click_tab(page, "Evolu")
                capture(page, OUT_DIR / "03_evolucao.png")
            except PWTimeout:
                print("  AVISO: tab Evolução não encontrada")
                capture(page, OUT_DIR / "03_evolucao_erro.png")

            # ── 4. Aba Tabela Completa
            print("\n[4/6] Aba Tabela Completa...")
            try:
                click_tab(page, "Tabela")
                capture(page, OUT_DIR / "04_tabela.png")
            except PWTimeout:
                print("  AVISO: tab Tabela não encontrada")

            # ── 5. Aba Dados Brutos
            print("\n[5/6] Aba Dados Brutos...")
            try:
                click_tab(page, "Brutos")
                capture(page, OUT_DIR / "05_dados_brutos.png")
            except PWTimeout:
                print("  AVISO: tab Dados Brutos não encontrada")

            # ── 6. Aba Análise por Exame
            print("\n[6/6] Aba Análise por Exame (GLICOSE)...")
            try:
                click_tab(page, "lise")  # "Análise"
                time.sleep(1)
                select_exam(page, "GLICOSE")
                capture(page, OUT_DIR / "06_analise_glicose.png")
            except Exception as e:
                print(f"  AVISO: {e}")
                capture(page, OUT_DIR / "06_analise_erro.png")

            # Bonus: LDL
            print("\n[bonus] Análise LDL-COLESTEROL...")
            try:
                click_tab(page, "lise")
                time.sleep(0.5)
                select_exam(page, "LDL-COLESTEROL")
                capture(page, OUT_DIR / "07_analise_ldl.png")
            except Exception as e:
                print(f"  AVISO: {e}")

            browser.close()

    finally:
        print("\nEncerrando Streamlit...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    print(f"\nScreenshots salvos em: {OUT_DIR}")


if __name__ == "__main__":
    main()
