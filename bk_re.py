# Dev by: Mo3tafa
# GitHub: https://github.com/Mo3tafa/

import os
import subprocess
import datetime
import shutil
import sys
import time
import urllib.request
import urllib.error
import uuid
import threading
import itertools
import shlex
import zipfile
from flask import Flask, render_template_string, request, redirect, url_for, session, flash

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class Spinner:
    def __init__(self, message="Processing..."):
        self.spinner_cycle = itertools.cycle(['-', '\\', '|', '/'])
        self.stop_running = threading.Event()
        self.message = message
        self.thread = threading.Thread(target=self.spin)

    def spin(self):
        while not self.stop_running.is_set():
            sys.stdout.write(f"\r{Colors.YELLOW}⏳ {next(self.spinner_cycle)} {self.message}{Colors.RESET}")
            sys.stdout.flush()
            time.sleep(0.1)
        sys.stdout.write('\r' + ' ' * (len(self.message) + 15) + '\r')
        sys.stdout.flush()

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.stop_running.set()
        self.thread.join()

def print_info(msg):
    print(f"{Colors.BLUE}ℹ️  [INFO]{Colors.RESET} {msg}")

def print_success(msg):
    print(f"{Colors.GREEN}✅ [SUCCESS]{Colors.RESET} {msg}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠️  [WARNING]{Colors.RESET} {msg}")

def print_error(msg):
    print(f"{Colors.RED}❌ [ERROR]{Colors.RESET} {msg}")

def print_header(title):
    print(f"\n{Colors.HEADER}{Colors.BOLD}=================================================={Colors.RESET}")
    print(f"{Colors.HEADER}{Colors.BOLD}        {title}        {Colors.RESET}")
    print(f"{Colors.HEADER}{Colors.BOLD}=================================================={Colors.RESET}\n")

def pause_and_return():
    input(f"\n{Colors.YELLOW}Press [ENTER] to return to the main menu...{Colors.RESET}")

def check_disk_space(required_mb=500, path="/var/lib"):
    try:
        stat = shutil.disk_usage(path)
        free_mb = stat.free / (1024 * 1024)
        if free_mb < required_mb:
            print_warning(f"Low disk space detected on {path}! Free: {free_mb:.2f} MB")
            return False
        return True
    except Exception:
        return True

def run_command(command, output_file=None, cwd=None, quiet=True):
    try:
        if output_file:
            with open(output_file, "w") as f:
                subprocess.run(command, shell=True, check=True, stdout=f, stderr=subprocess.PIPE, cwd=cwd)
        else:
            stdout_target = subprocess.DEVNULL if quiet else None
            subprocess.run(command, shell=True, check=True, stdout=stdout_target, stderr=subprocess.PIPE, cwd=cwd)
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {command}")
        return False

PASARGUARD_DIR = "/opt/pasarguard"
PG_NODE_DIR = "/opt/pg-node"
PASARGUARD_DATA_DIR = "/var/lib/pasarguard"
PG_NODE_DATA_DIR = "/var/lib/pg-node"

def stop_compose_stack_local(compose_dir, label):
    if not os.path.isdir(compose_dir) or not os.path.isfile(os.path.join(compose_dir, "docker-compose.yml")):
        return True
    print_info(f"Stopping {label} containers in {compose_dir}...")
    run_command("docker compose down --remove-orphans -t 30", cwd=compose_dir, quiet=True)
    return True

def clean_restore_directories_local():
    targets = [PASARGUARD_DIR, PG_NODE_DIR, PASARGUARD_DATA_DIR, PG_NODE_DATA_DIR]
    for path in targets:
        if not run_command(f"rm -rf {path} && mkdir -p {path}", quiet=True):
            return False
    return True

def create_backup(db_type="timescaledb"):
    print_info("Starting Smart Backup Generation...")
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_name = f"backup_{timestamp}"
    current_dir = os.getcwd() 
    tmp_dir = os.path.join("/tmp", backup_name)
    final_zip_base = os.path.join(current_dir, backup_name)
    expected_zip_file = f"{final_zip_base}.zip"

    opt_dir = "/opt/pasarguard"
    data_dir = "/var/lib/pasarguard"
    pg_node_opt = "/opt/pg-node"
    pg_node_data = "/var/lib/pg-node"
    pg_dump_dir = os.path.join(tmp_dir, "pg_dump")

    try:
        os.makedirs(pg_dump_dir, exist_ok=True)
        if os.path.exists(os.path.join(opt_dir, "docker-compose.yml")):
            shutil.copy(os.path.join(opt_dir, "docker-compose.yml"), tmp_dir)
        if os.path.exists(os.path.join(opt_dir, ".env")):
            shutil.copy(os.path.join(opt_dir, ".env"), tmp_dir)

        if db_type == "timescaledb":
            subprocess.run(f"cd {opt_dir} && docker compose exec -T timescaledb pg_dumpall -U pasarguard --globals-only > {os.path.join(pg_dump_dir, 'globals.sql')}", shell=True)
            subprocess.run(f"cd {opt_dir} && docker compose exec -T timescaledb pg_dump -U pasarguard -d pasarguard > {os.path.join(pg_dump_dir, 'db-001.sql')}", shell=True)
        else:
            root_pw = subprocess.run(f"grep 'MYSQL_ROOT_PASSWORD=' {opt_dir}/.env | cut -d= -f2- | tr -d '\"'", shell=True, capture_output=True, text=True).stdout.strip()
            subprocess.run(f"cd {opt_dir} && docker compose exec -T mysql sh -c 'exec mysqldump -uroot -p\"{root_pw}\" pasarguard' > {os.path.join(pg_dump_dir, 'db_backup.sql')}", shell=True)

        if os.path.exists(data_dir): shutil.copytree(data_dir, os.path.join(tmp_dir, "pasarguard_data"))
        if os.path.exists(pg_node_opt): shutil.copytree(pg_node_opt, os.path.join(tmp_dir, "pg_node_opt"))
        if os.path.exists(pg_node_data): shutil.copytree(pg_node_data, os.path.join(tmp_dir, "pg_node_data"))

        shutil.make_archive(final_zip_base, 'zip', tmp_dir)
        shutil.rmtree(tmp_dir)

        if zipfile.is_zipfile(expected_zip_file):
            return expected_zip_file
        return None
    except Exception as e:
        if os.path.exists(tmp_dir): shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

def workflow_manual_backup(db_type="timescaledb"):
    print_header("Manual Backup (Local)")
    zip_file_path = create_backup(db_type)
    if zip_file_path: print_success(f"Saved at: {zip_file_path}")

def workflow_manual_restore(db_type="timescaledb"):
    print_header("Safe Secure Manual Restore")
    zip_name = input(f"{Colors.CYAN}📦 Enter exact Backup ZIP file name: {Colors.RESET}").strip()
    if not os.path.exists(zip_name) or not zipfile.is_zipfile(zip_name):
        print_error("File not found or invalid!")
        return

    if input(f"{Colors.RED}⚠️  WARNING: Continue? (y/n): {Colors.RESET}").strip().lower() != 'y': return

    try:
        stop_compose_stack_local(PG_NODE_DIR, "PG-Node")
        stop_compose_stack_local(PASARGUARD_DIR, "Pasarguard")
        clean_restore_directories_local()

        run_command(f"unzip -q -o {zip_name} -d /opt/pasarguard")
        run_command("cp -a /opt/pasarguard/pasarguard_data/. /var/lib/pasarguard/ 2>/dev/null || true")
        run_command("cp -a /opt/pasarguard/pg_node_opt/. /opt/pg-node/ 2>/dev/null || true")
        run_command("cp -a /opt/pasarguard/pg_node_data/. /var/lib/pg-node/ 2>/dev/null || true")
        run_command("rm -rf /opt/pasarguard/pg_node_opt /opt/pasarguard/pg_node_data /opt/pasarguard/pasarguard_data")

        if db_type == "timescaledb":
            run_command("docker compose up -d timescaledb", cwd=PASARGUARD_DIR)
            time.sleep(5)
            run_command('cd /opt/pasarguard && docker compose exec -T timescaledb psql -U pasarguard -d postgres -c "DROP DATABASE IF EXISTS pasarguard WITH (FORCE); CREATE DATABASE pasarguard;"')
            run_command("cd /opt/pasarguard && cat pg_dump/globals.sql | docker compose exec -T timescaledb psql -U pasarguard")
            run_command("cd /opt/pasarguard && cat pg_dump/db-001.sql | docker compose exec -T timescaledb psql -U pasarguard -d pasarguard")

        run_command("docker compose up -d", cwd=PASARGUARD_DIR)
        run_command("docker compose up -d", cwd=PG_NODE_DIR)
        print_success("Restore completed successfully!")
    except Exception as e:
        print_error(f"Restore failed: {e}")

def check_system_health():
    print_header("System Health & Disk Status")
    stat = shutil.disk_usage("/")
    print(f"💽 Disk Free Space: {stat.free / (1024**3):.2f} GB / Total: {stat.total / (1024**3):.2f} GB")
    print(f"🐳 Docker Containers Status:")
    run_command("docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'", quiet=False)
    pause_and_return()

def show_web_panel_info():
    print_header("Web Panel Access Info")
    pwd_file = "/opt/pasarguard/.web_pwd"
    web_pwd = "Not Set"
    if os.path.exists(pwd_file):
        with open(pwd_file, "r") as f:
            web_pwd = f.read().strip()
    
    # گرفتن IP سرور
    ip_cmd = "hostname -I | awk '{print $1}'"
    ip_res = subprocess.run(ip_cmd, shell=True, capture_output=True, text=True).stdout.strip() or "YOUR_SERVER_IP"
    
    print(f"{Colors.GREEN}🌐 Web Panel URL:{Colors.RESET} http://{ip_res}:5000")
    print(f"{Colors.GREEN}🔑 Access Password:{Colors.RESET} {web_pwd}")
    print(f"{Colors.YELLOW}ℹ️  To start or check the web panel, run: python3 web_app.py{Colors.RESET}")
    pause_and_return()

# بخش اپلیکیشن تحت وب (Flask) همراه با صفحه لاگین
app = Flask(__name__)
app.secret_key = "mo3tafa_secure_web_key"

WEB_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>PasarGuard Enterprise Manager</title>
    <style>
        body { font-family: Tahoma, sans-serif; background-color: #121212; color: #e0e0e0; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: auto; background: #1e1e1e; padding: 25px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.7); }
        h1 { color: #bb86fc; text-align: center; }
        .card { background: #2d2d2d; padding: 15px; margin-bottom: 15px; border-radius: 6px; border-right: 4px solid #bb86fc; }
        .btn { display: inline-block; width: 100%; padding: 10px; background: #03dac6; color: #121212; text-align: center; text-decoration: none; font-weight: bold; border-radius: 4px; border: none; cursor: pointer; margin-top: 5px; }
        .btn:hover { background: #018786; color: #fff; }
        .flashes { background: #333; padding: 12px; margin-bottom: 20px; border-radius: 4px; border-right: 4px solid #03dac6; white-space: pre-line; }
        pre { background: #111; padding: 10px; border-radius: 4px; color: #81c784; direction: ltr; text-align: left; }
        input[type="password"] { width: 100%; padding: 8px; margin: 10px 0; background: #333; border: 1px solid #444; color: #fff; border-radius: 4px; box-sizing: border-box; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🛡️ پارسی‌گارد - پنل مدیریت تحت وب</h1>
        <div style="text-align: right; margin-bottom: 15px;"><a href="/logout" style="color: #ff5252; text-decoration: none;">خروج از حساب</a></div>
        
        {% with messages = get_flashed_messages() %}
          {% if messages %}
            <div class="flashes">
              {% for message in messages %}
                <div>{{ message }}</div>
              {% endfor %}
            </div>
          {% endif %}
        {% endwith %}

        <div class="card">
            <h3>💾 ایجاد بکاپ دستی</h3>
            <form action="/backup" method="POST">
                <label>نوع دیتابیس:</label>
                <select name="db_type" style="width:100%; padding:8px; background:#333; color:#fff; border-radius:4px; margin-bottom:10px;">
                    <option value="timescaledb">PostgreSQL / TimescaleDB</option>
                    <option value="mysql">MySQL</option>
                </select>
                <button type="submit" class="btn">شروع بکاپ‌گیری</button>
            </form>
        </div>

        <div class="card">
            <h3>🩺 بررسی وضعیت سلامت سیستم</h3>
            <a href="/health" class="btn" style="background: #bb86fc; color: #121212;">مشاهده وضعیت دیسک و کانتینرها</a>
            {% if health_output %}
                <pre>{{ health_output }}</pre>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>ورود به پنل مدیریت پارسی‌گارد</title>
    <style>
        body { font-family: Tahoma, sans-serif; background-color: #121212; color: #e0e0e0; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #1e1e1e; padding: 30px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.7); width: 300px; text-align: center; }
        h2 { color: #bb86fc; }
        input[type="password"] { width: 100%; padding: 10px; margin: 15px 0; background: #333; border: 1px solid #444; color: #fff; border-radius: 4px; box-sizing: border-box; }
        .btn { width: 100%; padding: 10px; background: #03dac6; color: #121212; font-weight: bold; border-radius: 4px; border: none; cursor: pointer; }
        .error { color: #ff5252; font-size: 13px; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>🔒 ورود به پنل</h2>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <input type="password" name="password" placeholder="رمز عبور را وارد کنید" required>
            <button type="submit" class="btn">ورود</button>
        </form>
    </div>
</body>
</html>
"""

def get_saved_password():
    pwd_file = "/opt/pasarguard/.web_pwd"
    if os.path.exists(pwd_file):
        with open(pwd_file, "r") as f:
            return f.read().strip()
    return "admin123"

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == get_saved_password():
            session['logged_in'] = True
            return redirect(url_for('web_index'))
        error = "رمز عبور اشتباه است!"
    return render_template_string(LOGIN_TEMPLATE, error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
def web_index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template_string(WEB_TEMPLATE, health_output=None)

@app.route('/backup', methods=['POST'])
def web_backup():
    if not session.get('logged_in'): return redirect(url_for('login'))
    db_type = request.form.get('db_type', 'timescaledb')
    res = create_backup(db_type)
    if res: flash(f"✅ بکاپ با موفقیت ایجاد شد: {res}")
    else: flash("❌ خطا در ایجاد بکاپ.")
    return redirect(url_for('web_index'))

@app.route('/health')
def web_health():
    if not session.get('logged_in'): return redirect(url_for('login'))
    stat = shutil.disk_usage("/")
    ok, out, _ = run_command("docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'", quiet=False)
    report = f"💽 Disk Free: {stat.free / (1024**3):.2f} GB\n\n🐳 Containers:\n{out}"
    return render_template_string(WEB_TEMPLATE, health_output=report)

def run_web_server():
    app.run(host='0.0.0.0', port=5000, debug=False)

def main():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"\n{Colors.HEADER}{Colors.BOLD}=================================================={Colors.RESET}")
        print(f"{Colors.HEADER}{Colors.BOLD}       🛡️  PASARGUARD ENTERPRISE MANAGER 🛡️        {Colors.RESET}")
        print(f"{Colors.HEADER}{Colors.BOLD}=================================================={Colors.RESET}")
        print(f"{Colors.CYAN}       Dev by: Mo3tafa{Colors.RESET}")
        print(f"{Colors.HEADER}{Colors.BOLD}=================================================={Colors.RESET}\n")
        print(f"{Colors.BLUE}1-{Colors.RESET} 🚀 Auto Backup & Transfer to New Server")
        print(f"{Colors.BLUE}2-{Colors.RESET} 🤖 Scheduled Backup to Telegram")
        print(f"{Colors.BLUE}3-{Colors.RESET} 💾 Manual Backup (Local)")
        print(f"{Colors.BLUE}4-{Colors.RESET} 🔄 Safe Manual Restore")
        print(f"{Colors.BLUE}5-{Colors.RESET} 🩺 System & Disk Health Check")
        print(f"{Colors.BLUE}6-{Colors.RESET} 🌐 WebPanel Info (مشاهده اطلاعات پنل وب)")
        print(f"{Colors.RED}7-{Colors.RESET} 🚪 Exit")
        print(f"{Colors.HEADER}--------------------------------------------------{Colors.RESET}")
        
        choice = input(f"{Colors.CYAN}👉 Select an option (1-7): {Colors.RESET}").strip()
        
        db_type = "timescaledb"
        if choice in ['1', '2', '3', '4']:
            db_choice = input(f"{Colors.CYAN}🗄️  Database type? (1: timescaledb, 2: mysql): {Colors.RESET}").strip()
            if db_choice == '2': db_type = "mysql"
        
        if choice == '1': workflow_auto_backup_restore(db_type); pause_and_return()
        elif choice == '2': workflow_backup_bot(db_type)
        elif choice == '3': workflow_manual_backup(db_type); pause_and_return()
        elif choice == '4': workflow_manual_restore(db_type); pause_and_return()
        elif choice == '5': check_system_health()
        elif choice == '6': show_web_panel_info()
        elif choice == '7': sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--web":
        run_web_server()
    else:
        main()
