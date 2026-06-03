"""Interface grafica (Tkinter) para o pipeline BOM -> Jira.

Design / UX:
  - Paleta dark moderna (estilo IDE) com acento azul Jira.
  - Hierarquia visual clara: header (branding) -> entrada -> opcoes -> log -> rodape.
  - Feedback imediato: barra de progresso indeterminada + cor de status.
  - Affordances: botao primario destacado, secundarios neutros, "Finalizar" em tom de alerta.
  - Acessibilidade: atalhos (Ctrl+Enter inicia, Esc finaliza), tooltips, focus inicial na URL.
  - Console com cores por nivel (info / ok / aviso / erro).

Arquitetura:
  Playwright (sync API) so pode ser usado pela MESMA thread que o iniciou.
  Por isso usamos UMA UNICA thread worker persistente que detem o navegador
  e processa jobs enfileirados pela UI (pipeline, close, finalize).
"""

from __future__ import annotations

import os
import queue
import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk, scrolledtext, messagebox
from typing import Callable, Optional

# Garante que estamos no diretorio do script (importante quando lancado pelo .bat)
os.chdir(Path(__file__).parent)

import config
from sharepoint_io import download_bom, upload_bom
from step3_create_jira_ui import start_browser, close_browser
from main import load_filtered_bom, process_row, write_keys_to_bom


# ---------------------------------------------------------------------------
# Paleta de cores (dark theme, acento Jira blue)
# ---------------------------------------------------------------------------
class Theme:
    BG          = "#1E2330"   # fundo principal
    BG_ALT      = "#262C3B"   # painel
    BG_ELEVATED = "#2F3649"   # cartoes / input
    BORDER      = "#3A4358"
    TEXT        = "#E6E9F2"
    TEXT_MUTED  = "#9AA3B8"
    PRIMARY     = "#3B82F6"   # azul Jira-like
    PRIMARY_HOV = "#2563EB"
    DANGER      = "#EF4444"
    DANGER_HOV  = "#DC2626"
    WARNING     = "#F59E0B"
    SUCCESS     = "#10B981"
    INFO        = "#60A5FA"


# ---------------------------------------------------------------------------
# Redirect de stdout/stderr para a fila -> caixa de texto
# ---------------------------------------------------------------------------
class _QueueWriter:
    def __init__(self, q: "queue.Queue[str]"):
        self.q = q

    def write(self, text: str) -> int:
        if text:
            self.q.put(text)
        return len(text)

    def flush(self):
        pass


# ---------------------------------------------------------------------------
# Tooltip simples
# ---------------------------------------------------------------------------
class _Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tip, text=self.text, bg="#0F1320", fg=Theme.TEXT,
            relief="solid", borderwidth=1, padx=8, pady=4,
            font=("Segoe UI", 9),
        ).pack()

    def _hide(self, _):
        if self.tip:
            self.tip.destroy()
            self.tip = None


# ---------------------------------------------------------------------------
# Job do pipeline (executado na worker thread)
# ---------------------------------------------------------------------------
def _run_pipeline(share_url: str, test_mode: bool) -> None:
    config.TEST_MODE = bool(test_mode)
    print(f"[GUI] TEST_MODE = {config.TEST_MODE}")

    if share_url:
        start_browser()
        local_bom = Path("input") / "BOM_from_sharepoint.xlsx"
        download_bom(share_url, local_bom)
        config.BOM_FILE = str(local_bom)
    else:
        print(f"[GUI] Usando arquivo local: {config.BOM_FILE}")

    datasheet_root = Path(config.DATASHEET_ROOT)
    filtered = load_filtered_bom()
    print(f"Total de linhas a processar: {len(filtered)}")

    start_browser()

    keys_by_index: dict[int, str] = {}
    for df_idx, row in filtered.iterrows():
        key = process_row(row, datasheet_root)
        if key:
            keys_by_index[df_idx] = key

    print("\n" + "=" * 70)
    print("RESUMO DAS ISSUES CRIADAS")
    print("=" * 70)
    if keys_by_index:
        for df_idx, key in keys_by_index.items():
            line = filtered.loc[df_idx, config.COLUMN_LINE]
            pn = filtered.loc[df_idx, config.COLUMN_PART_NUMBER]
            print(f"  {key:<12}  Linha {line:<8}  {pn}")
    else:
        print("  (nenhuma issue criada)")

    try:
        write_keys_to_bom(keys_by_index)
    except Exception as exc:
        print(f"[ERRO] gravando keys na planilha: {exc}")

    if share_url and keys_by_index:
        try:
            upload_bom(share_url, Path(config.BOM_FILE))
        except Exception as exc:
            print(f"[ERRO] subindo a BOM para o SharePoint: {exc}")
    elif share_url:
        print("Nenhuma key gerada -> upload para o SharePoint nao realizado.")

    print("\n[GUI] Pipeline concluido. O navegador continua aberto para conferencia.")


# ---------------------------------------------------------------------------
# Janela principal
# ---------------------------------------------------------------------------
class App(tk.Tk):
    _STOP = object()

    def __init__(self):
        super().__init__()
        self.title("BOM -> Jira Automation")
        self.geometry("1000x680")
        # minsize baixa o suficiente para sempre caber header + opcoes + rodape
        self.minsize(560, 360)
        self.configure(bg=Theme.BG)

        self._log_queue: "queue.Queue[str]" = queue.Queue()
        self._job_queue: "queue.Queue" = queue.Queue()
        self._busy = False

        self._setup_style()
        self._build_widgets()
        self._bind_shortcuts()
        self._redirect_stdio()
        self.after(80, self._drain_queue)

        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

        # UX: foco inicial na URL
        self.after(150, lambda: self.url_entry.focus_set())
        self._print_welcome()

    # ---------------------------------------------------------- estilo
    def _setup_style(self):
        style = ttk.Style(self)
        # 'clam' permite customizar cores em widgets ttk
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # Frames / labels
        style.configure("TFrame", background=Theme.BG)
        style.configure("Card.TFrame", background=Theme.BG_ALT)
        style.configure("Header.TFrame", background=Theme.BG_ALT)

        style.configure("TLabel", background=Theme.BG, foreground=Theme.TEXT,
                        font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=Theme.BG_ALT, foreground=Theme.TEXT,
                        font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=Theme.BG_ALT, foreground=Theme.TEXT,
                        font=("Segoe UI Semibold", 16))
        style.configure("Subtitle.TLabel", background=Theme.BG_ALT,
                        foreground=Theme.TEXT_MUTED, font=("Segoe UI", 9))
        style.configure("FieldLabel.TLabel", background=Theme.BG_ALT,
                        foreground=Theme.TEXT_MUTED, font=("Segoe UI", 9, "bold"))
        style.configure("Status.TLabel", background=Theme.BG, foreground=Theme.TEXT_MUTED,
                        font=("Segoe UI", 9))

        # Entry
        style.configure("Modern.TEntry",
                        fieldbackground=Theme.BG_ELEVATED,
                        background=Theme.BG_ELEVATED,
                        foreground=Theme.TEXT,
                        bordercolor=Theme.BORDER,
                        lightcolor=Theme.BORDER,
                        darkcolor=Theme.BORDER,
                        insertcolor=Theme.TEXT,
                        padding=8)
        style.map("Modern.TEntry",
                  bordercolor=[("focus", Theme.PRIMARY)],
                  lightcolor=[("focus", Theme.PRIMARY)],
                  darkcolor=[("focus", Theme.PRIMARY)])

        # Checkbutton
        style.configure("Modern.TCheckbutton",
                        background=Theme.BG_ALT, foreground=Theme.TEXT,
                        focuscolor=Theme.BG_ALT, font=("Segoe UI", 10))
        style.map("Modern.TCheckbutton",
                  background=[("active", Theme.BG_ALT)],
                  foreground=[("active", Theme.TEXT)])

        # Botoes (3 variantes)
        for name, bg, hov, fg in [
            ("Primary.TButton", Theme.PRIMARY, Theme.PRIMARY_HOV, "#FFFFFF"),
            ("Secondary.TButton", Theme.BG_ELEVATED, Theme.BORDER, Theme.TEXT),
            ("Danger.TButton", Theme.DANGER, Theme.DANGER_HOV, "#FFFFFF"),
        ]:
            style.configure(name, background=bg, foreground=fg, borderwidth=0,
                            focusthickness=0, padding=(16, 8),
                            font=("Segoe UI Semibold", 10))
            style.map(name,
                      background=[("active", hov), ("disabled", "#3A4055")],
                      foreground=[("disabled", Theme.TEXT_MUTED)])

        # Progressbar
        style.configure("Modern.Horizontal.TProgressbar",
                        troughcolor=Theme.BG_ALT,
                        background=Theme.PRIMARY,
                        bordercolor=Theme.BG_ALT,
                        lightcolor=Theme.PRIMARY,
                        darkcolor=Theme.PRIMARY)

        # LabelFrame (log)
        style.configure("Card.TLabelframe", background=Theme.BG_ALT,
                        bordercolor=Theme.BORDER, relief="solid", borderwidth=1)
        style.configure("Card.TLabelframe.Label", background=Theme.BG_ALT,
                        foreground=Theme.TEXT_MUTED,
                        font=("Segoe UI Semibold", 9))

        # Separator
        style.configure("TSeparator", background=Theme.BORDER)

    # ------------------------------------------------------------ UI
    def _build_widgets(self):
        # ===== Header (branding) =====
        header = ttk.Frame(self, style="Header.TFrame", padding=(20, 14))
        header.pack(fill="x")
        title_row = ttk.Frame(header, style="Header.TFrame")
        title_row.pack(fill="x")
        ttk.Label(title_row, text="BOM -> Jira Automation",
                  style="Title.TLabel").pack(side="left")
        # "badge" de versao / modo
        self.mode_badge = tk.Label(title_row, text=" TEST MODE ",
                                   bg=Theme.WARNING, fg="#1E2330",
                                   font=("Segoe UI Semibold", 8), padx=6, pady=2)
        self.mode_badge.pack(side="right")
        ttk.Label(header,
                  text="Cria tickets MAT no Jira a partir da BOM e atualiza a planilha.",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # ===== Rodape (empacotado ANTES do body para nunca sumir quando a
        # janela encolhe; pack respeita a ordem de insercao na hora de
        # reservar espaco) =====
        self._build_footer()

        # ===== Corpo =====
        body = ttk.Frame(self, padding=(20, 16))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        # Card de configuracao
        cfg = ttk.Frame(body, style="Card.TFrame", padding=16)
        cfg.grid(row=0, column=0, sticky="ew")
        cfg.columnconfigure(0, weight=1)

        ttk.Label(cfg, text="FONTE DA BOM", style="FieldLabel.TLabel"
                  ).grid(row=0, column=0, sticky="w")
        ttk.Label(cfg,
                  text="Cole a URL do SharePoint, ou deixe vazio para usar o arquivo local.",
                  style="Subtitle.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 6))

        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(cfg, textvariable=self.url_var, style="Modern.TEntry",
                                   font=("Segoe UI", 10))
        self.url_entry.grid(row=2, column=0, sticky="ew")
        _Tooltip(self.url_entry, "URL do arquivo Excel no SharePoint (link de compartilhamento).")

        # Linha de opcoes
        opts = ttk.Frame(body, style="Card.TFrame", padding=(16, 12))
        opts.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        opts.columnconfigure(0, weight=1)

        self.test_var = tk.BooleanVar(value=bool(getattr(config, "TEST_MODE", True)))
        self.test_var.trace_add("write", lambda *_: self._update_mode_badge())
        chk = ttk.Checkbutton(
            opts,
            text='TEST MODE  -  pula a transicao para "Purchasing" e o assignee Colby Zheng',
            variable=self.test_var,
            style="Modern.TCheckbutton",
        )
        chk.grid(row=0, column=0, sticky="w")
        _Tooltip(chk, "Use durante testes para nao mexer no workflow real do Jira.")

        # Botoes de acao principais (direita)
        actions = ttk.Frame(opts, style="Card.TFrame")
        actions.grid(row=0, column=1, sticky="e")
        self.btn_clear = ttk.Button(actions, text="Limpar log",
                                    style="Secondary.TButton",
                                    command=self.clear_log)
        self.btn_clear.pack(side="left", padx=(0, 8))
        _Tooltip(self.btn_clear, "Limpa o conteudo do console (Ctrl+L).")

        self.btn_start = ttk.Button(actions, text="Iniciar  >",
                                    style="Primary.TButton",
                                    command=self.on_start)
        self.btn_start.pack(side="left")
        _Tooltip(self.btn_start, "Inicia o pipeline (Ctrl+Enter).")

        # ===== Console =====
        log_wrap = ttk.Labelframe(body, text="  Console  ", style="Card.TLabelframe",
                                  padding=8)
        log_wrap.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        log_wrap.rowconfigure(0, weight=1)
        log_wrap.columnconfigure(0, weight=1)

        self.log = scrolledtext.ScrolledText(
            log_wrap, wrap="word", state="disabled",
            bg="#11151F", fg=Theme.TEXT, insertbackground=Theme.TEXT,
            relief="flat", borderwidth=0,
            # height=1 permite que o widget encolha junto com a janela
            # (sem isso ele forca um tamanho minimo grande e empurra o rodape).
            width=1, height=1,
            font=("Cascadia Mono", 10) if self._font_exists("Cascadia Mono")
                                       else ("Consolas", 10),
            padx=10, pady=8,
        )
        self.log.grid(row=0, column=0, sticky="nsew")
        # Tags coloridas
        self.log.tag_configure("info",  foreground=Theme.INFO)
        self.log.tag_configure("ok",    foreground=Theme.SUCCESS)
        self.log.tag_configure("warn",  foreground=Theme.WARNING)
        self.log.tag_configure("err",   foreground=Theme.DANGER)
        self.log.tag_configure("muted", foreground=Theme.TEXT_MUTED)

        self.protocol("WM_DELETE_WINDOW", self.on_finalize)
        self._update_mode_badge()

    def _build_footer(self):
        # Separator acima do rodape
        ttk.Separator(self, orient="horizontal").pack(fill="x", side="bottom")
        footer = ttk.Frame(self, padding=(20, 10))
        footer.pack(fill="x", side="bottom")
        footer.columnconfigure(1, weight=1)

        # Indicador de status (bolinha + texto)
        status_box = ttk.Frame(footer)
        status_box.grid(row=0, column=0, sticky="w")
        self.status_dot = tk.Canvas(status_box, width=12, height=12, bg=Theme.BG,
                                    highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 8))
        self._draw_dot(Theme.TEXT_MUTED)
        self.status_var = tk.StringVar(value="Pronto")
        ttk.Label(status_box, textvariable=self.status_var,
                  style="Status.TLabel").pack(side="left")

        # Progressbar (escondida ate ter trabalho)
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=180,
                                        style="Modern.Horizontal.TProgressbar")
        self.progress.grid(row=0, column=1, padx=16, sticky="ew")

        # Botoes do rodape
        right = ttk.Frame(footer)
        right.grid(row=0, column=2, sticky="e")
        self.btn_close_browser = ttk.Button(right, text="Encerrar navegador",
                                            style="Secondary.TButton",
                                            command=self.on_close_browser)
        self.btn_close_browser.pack(side="left", padx=(0, 8))
        _Tooltip(self.btn_close_browser, "Fecha o Edge controlado pelo Playwright.")

        self.btn_finalize = ttk.Button(right, text="Finalizar",
                                       style="Danger.TButton",
                                       command=self.on_finalize)
        self.btn_finalize.pack(side="left")
        _Tooltip(self.btn_finalize, "Encerra a aplicacao (Esc).")

    def _bind_shortcuts(self):
        self.bind_all("<Control-Return>", lambda e: self.on_start())
        self.bind_all("<Control-l>",      lambda e: self.clear_log())
        self.bind_all("<Escape>",         lambda e: self.on_finalize())

    def _font_exists(self, name: str) -> bool:
        try:
            return name in tkfont.families()
        except Exception:
            return False

    def _draw_dot(self, color: str):
        self.status_dot.delete("all")
        self.status_dot.create_oval(1, 1, 11, 11, fill=color, outline=color)

    def _update_mode_badge(self):
        if self.test_var.get():
            self.mode_badge.configure(text=" TEST MODE ", bg=Theme.WARNING, fg="#1E2330")
        else:
            self.mode_badge.configure(text="  LIVE  ", bg=Theme.SUCCESS, fg="#1E2330")

    def _print_welcome(self):
        msg = (
            "[GUI] Bem-vindo!\n"
            "      - Cole a URL do SharePoint (ou deixe vazio para usar a BOM local).\n"
            "      - Atalhos: Ctrl+Enter = iniciar, Ctrl+L = limpar log, Esc = finalizar.\n"
        )
        # bypass do queue para sair antes de qualquer redirect
        self._log_queue.put(msg)

    # -------------------------------------------- stdout/stderr -> fila
    def _redirect_stdio(self):
        writer = _QueueWriter(self._log_queue)
        sys.stdout = writer
        sys.stderr = writer

    def _classify(self, line: str) -> str:
        low = line.lower()
        if "[erro" in low or "error" in low or "traceback" in low:
            return "err"
        if "[aviso" in low or "warn" in low:
            return "warn"
        if "[test_mode]" in low or re.search(r"\bmat-\d+\b", low) or "concluido" in low:
            return "ok"
        if line.startswith("[GUI]") or line.startswith("="*10) or line.startswith("-"*10):
            return "info"
        return "muted"

    def _append_line(self, line: str):
        tag = self._classify(line)
        self.log.configure(state="normal")
        self.log.insert("end", line, tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_queue(self):
        # Acumula um chunk e processa por linha para conseguir colorir
        try:
            chunks = []
            while True:
                chunks.append(self._log_queue.get_nowait())
        except queue.Empty:
            pass
        if chunks:
            buf = "".join(chunks)
            # mantem todas as linhas, inclusive a parcial final
            parts = buf.splitlines(keepends=True)
            for p in parts:
                self._append_line(p)
        self.after(80, self._drain_queue)

    # ----------------------------------------- Worker thread (Playwright)
    def _worker_loop(self):
        while True:
            item = self._job_queue.get()
            if item is self._STOP:
                break
            job, on_done = item
            try:
                job()
            except Exception as exc:
                print(f"[ERRO] {exc}")
            finally:
                if on_done is not None:
                    self.after(0, on_done)

    def _submit(self, job: Callable[[], None],
                on_done: Optional[Callable[[], None]] = None) -> None:
        self._job_queue.put((job, on_done))

    # ------------------------------------------------------------ Acoes
    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _set_busy(self, busy: bool, status: str, color: str):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.btn_start.configure(state=state)
        self.btn_close_browser.configure(state=state)
        self.status_var.set(status)
        self._draw_dot(color)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def on_start(self):
        if self._busy:
            messagebox.showinfo("Em andamento", "Ja existe uma tarefa em execucao.")
            return
        url = self.url_var.get().strip()
        test = self.test_var.get()
        self._set_busy(True, "Executando pipeline...", Theme.INFO)

        def _done():
            self._set_busy(False, "Concluido", Theme.SUCCESS)

        self._submit(lambda: _run_pipeline(url, test), _done)

    def on_close_browser(self):
        if self._busy:
            messagebox.showinfo("Em andamento",
                                "Aguarde a tarefa atual terminar antes de encerrar o navegador.")
            return
        self._set_busy(True, "Encerrando navegador...", Theme.WARNING)

        def _do_close():
            try:
                close_browser()
                print("[GUI] Navegador fechado.")
            except Exception as exc:
                print(f"[GUI] Erro ao fechar navegador: {exc}")

        def _done():
            self._set_busy(False, "Pronto", Theme.TEXT_MUTED)

        self._submit(_do_close, _done)

    def on_finalize(self):
        if self._busy:
            if not messagebox.askyesno(
                "Finalizar",
                "Uma tarefa ainda esta em execucao. Finalizar mesmo assim?",
            ):
                return
        self.status_var.set("Finalizando...")
        self._draw_dot(Theme.DANGER)
        self.progress.start(12)
        for btn in (self.btn_start, self.btn_close_browser, self.btn_finalize):
            btn.configure(state="disabled")

        def _do_close():
            try:
                close_browser()
            except Exception as exc:
                print(f"[GUI] Erro ao fechar navegador no shutdown: {exc}")

        self._submit(_do_close, None)
        self._job_queue.put(self._STOP)
        self._wait_worker_then_destroy()

    def _wait_worker_then_destroy(self, tries: int = 50):
        if self._worker.is_alive() and tries > 0:
            self.after(100, lambda: self._wait_worker_then_destroy(tries - 1))
        else:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            self.destroy()


if __name__ == "__main__":
    App().mainloop()
