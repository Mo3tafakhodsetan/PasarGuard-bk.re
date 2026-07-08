# Dev by: Sin Kabir
# GitHub: https://github.com/1NoJoom/

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
        # Clear the line when stopped
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

# Auto-install paramiko
try:
    import paramiko
except ImportError:
    print(f"{Colors.YELLOW}⏳ Required libraries not found. Starting background installation...{Colors.RESET}")
    with Spinner("Installing required packages (Paramiko, unzip)... Please wait"):
        try:
            subprocess.check_call(["apt-get", "update"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.check_call(["apt-get", "install", "-y", "python3-paramiko", "python3-pip", "unzip"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            # Fallback to pip silently
            subprocess.check_call([sys.executable, "-m", "pip", "install", "paramiko", "--quiet"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import paramiko
    print(f"{Colors.GREEN}✅ Libraries installed successfully!{Colors.RESET}\n")

def run_command(command, output_file=None, cwd=None, quiet=True):
    try:
        if output_file:
            with open(output_file, "w") as f:
                subprocess.run(command, shell=True, check=True, stdout=f, stderr=subprocess.PIPE, cwd=cwd)
        else:
            # Hide output
            stdout_target = subprocess.DEVNULL if quiet else None
            subprocess.run(command, shell=True, check=True, stdout=stdout_target, stderr=subprocess.PIPE, cwd=cwd)
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {command}")
        if e.stderr:
            print_error(f"Details: {e.stderr.decode('utf-8').strip()}")
        return False

# ─── Docker stack paths & timing ───
PASARGUARD_DIR = "/opt/pasarguard"
PG_NODE_DIR = "/opt/pg-node"
PASARGUARD_DATA_DIR = "/var/lib/pasarguard"
PG_NODE_DATA_DIR = "/var/lib/pg-node"

COMPOSE_DOWN_TIMEOUT = 30
POSTGRES_READY_MAX_WAIT = 120
POSTGRES_READY_INTERVAL = 2
COMPOSE_UP_MAX_WAIT = 120
COMPOSE_UP_INTERVAL = 3
COMPOSE_STOP_RETRIES = 3

def local_shell(command, cwd=None):
    """Run a shell command locally; return (ok, stdout, stderr)."""
    try:
        result = subprocess.run(
            command, shell=True, cwd=cwd, capture_output=True, text=True
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return False, "", str(e)

def ssh_shell(ssh, command):
    """Run a command over SSH; return (exit_code, stdout, stderr)."""
    stdin, stdout, stderr = ssh.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    return exit_status, stdout.read().decode().strip(), stderr.read().decode().strip()

def _running_compose_ids_local(compose_dir):
    _, out, _ = local_shell("docker compose ps -q --status running", cwd=compose_dir)
    return [line for line in out.splitlines() if line.strip()]

def _running_compose_ids_ssh(ssh, compose_dir):
    _, out, _ = ssh_shell(
        ssh, f"cd {compose_dir} && docker compose ps -q --status running 2>/dev/null || true"
    )
    return [line for line in out.splitlines() if line.strip()]

def _expected_running_count_local(compose_dir, services):
    if services:
        return len(services)
    ok, out, _ = local_shell("docker compose config --services", cwd=compose_dir)
    if not ok:
        return 0
    return len([line for line in out.splitlines() if line.strip()])

def _expected_running_count_ssh(ssh, compose_dir, services):
    if services:
        return len(services)
    exit_code, out, _ = ssh_shell(ssh, f"cd {compose_dir} && docker compose config --services 2>/dev/null")
    if exit_code != 0:
        return 0
    return len([line for line in out.splitlines() if line.strip()])

def stop_compose_stack_local(compose_dir, label):
    """Stop a docker compose stack and verify every container is down."""
    if not os.path.isdir(compose_dir):
        print_warning(f"{label}: {compose_dir} not found — nothing to stop.")
        return True
    if not os.path.isfile(os.path.join(compose_dir, "docker-compose.yml")):
        print_warning(f"{label}: no docker-compose.yml — skipping stop.")
        return True

    print_info(f"Stopping {label} containers in {compose_dir}...")
    for attempt in range(1, COMPOSE_STOP_RETRIES + 1):
        run_command(
            f"docker compose down --remove-orphans -t {COMPOSE_DOWN_TIMEOUT}",
            cwd=compose_dir, quiet=True
        )
        run_command("docker compose stop -t 10 2>/dev/null || true", cwd=compose_dir, quiet=True)
        run_command("docker compose rm -f 2>/dev/null || true", cwd=compose_dir, quiet=True)

        running = _running_compose_ids_local(compose_dir)
        if not running:
            print_success(f"{label}: all containers stopped.")
            return True

        print_warning(f"{label}: {len(running)} container(s) still running (attempt {attempt}/{COMPOSE_STOP_RETRIES})...")
        time.sleep(2)

    _, status, _ = local_shell("docker compose ps", cwd=compose_dir)
    print_error(f"{label}: could not stop all containers.")
    if status:
        print_error(status)
    return False

def stop_compose_stack_ssh(ssh, compose_dir, label):
    """Stop a docker compose stack over SSH and verify every container is down."""
    exit_code, _, _ = ssh_shell(ssh, f"test -d {compose_dir} && test -f {compose_dir}/docker-compose.yml")
    if exit_code != 0:
        print_warning(f"{label}: {compose_dir} not found or missing docker-compose.yml — skipping stop.")
        return True

    print_info(f"Stopping {label} containers in {compose_dir}...")
    for attempt in range(1, COMPOSE_STOP_RETRIES + 1):
        ssh_shell(ssh, f"cd {compose_dir} && docker compose down --remove-orphans -t {COMPOSE_DOWN_TIMEOUT}")
        ssh_shell(ssh, f"cd {compose_dir} && docker compose stop -t 10 2>/dev/null || true")
        ssh_shell(ssh, f"cd {compose_dir} && docker compose rm -f 2>/dev/null || true")

        running = _running_compose_ids_ssh(ssh, compose_dir)
        if not running:
            print_success(f"{label}: all containers stopped.")
            return True

        print_warning(f"{label}: {len(running)} container(s) still running (attempt {attempt}/{COMPOSE_STOP_RETRIES})...")
        time.sleep(2)

    _, status, _ = ssh_shell(ssh, f"cd {compose_dir} && docker compose ps")
    print_error(f"{label}: could not stop all containers.")
    if status:
        print_error(status)
    return False

def clean_restore_directories_local():
    """Remove and recreate restore target directories after containers are stopped."""
    targets = [
        (PASARGUARD_DIR, "Pasarguard config (/opt/pasarguard)"),
        (PG_NODE_DIR, "PG-Node config (/opt/pg-node)"),
        (PASARGUARD_DATA_DIR, "Pasarguard data (/var/lib/pasarguard)"),
        (PG_NODE_DATA_DIR, "PG-Node data (/var/lib/pg-node)"),
    ]
    print_info("Cleaning target directories...")
    for path, desc in targets:
        if not run_command(f"rm -rf {path} && mkdir -p {path}", quiet=True):
            print_error(f"Failed to clean {desc}")
            return False
        if not os.path.isdir(path):
            print_error(f"Directory missing after cleanup: {path}")
            return False
    print_success("All target directories cleaned and recreated.")
    return True

def clean_restore_directories_ssh(ssh):
    """Remove and recreate restore target directories on remote server."""
    targets = [
        (PASARGUARD_DIR, "Pasarguard config (/opt/pasarguard)"),
        (PG_NODE_DIR, "PG-Node config (/opt/pg-node)"),
        (PASARGUARD_DATA_DIR, "Pasarguard data (/var/lib/pasarguard)"),
        (PG_NODE_DATA_DIR, "PG-Node data (/var/lib/pg-node)"),
    ]
    print_info("Cleaning target directories...")
    for path, desc in targets:
        exit_code, _, err = ssh_shell(ssh, f"rm -rf {path} && mkdir -p {path}")
        if exit_code != 0:
            print_error(f"Failed to clean {desc}")
            if err:
                print_error(err)
            return False
        verify_code, _, _ = ssh_shell(ssh, f"test -d {path}")
        if verify_code != 0:
            print_error(f"Directory missing after cleanup: {path}")
            return False
    print_success("All target directories cleaned and recreated.")
    return True

def wait_for_postgres_ready_local():
    """Wait until timescaledb accepts connections."""
    print_info("Waiting for timescaledb to become ready...")
    deadline = time.time() + POSTGRES_READY_MAX_WAIT
    while time.time() < deadline:
        ok, _, _ = local_shell(
            "docker compose exec -T timescaledb pg_isready -U pasarguard -d postgres",
            cwd=PASARGUARD_DIR,
        )
        if ok:
            print_success("Database is ready for restore operations.")
            return True
        time.sleep(POSTGRES_READY_INTERVAL)
    print_error("Database did not become ready in time.")
    return False

def wait_for_postgres_ready_ssh(ssh):
    """Wait until remote timescaledb accepts connections."""
    print_info("Waiting for timescaledb to become ready...")
    deadline = time.time() + POSTGRES_READY_MAX_WAIT
    while time.time() < deadline:
        exit_code, _, _ = ssh_shell(
            ssh,
            f"cd {PASARGUARD_DIR} && docker compose exec -T timescaledb pg_isready -U pasarguard -d postgres",
        )
        if exit_code == 0:
            print_success("Database is ready for restore operations.")
            return True
        time.sleep(POSTGRES_READY_INTERVAL)
    print_error("Database did not become ready in time.")
    return False

def start_compose_stack_local(compose_dir, label, services=None, wait_postgres=False):
    """Start docker compose stack locally and verify containers are running."""
    if not os.path.isdir(compose_dir) or not os.path.isfile(os.path.join(compose_dir, "docker-compose.yml")):
        print_error(f"{label}: compose project not found at {compose_dir}")
        return False

    svc_part = " ".join(services) if services else ""
    print_info(f"Starting {label} containers{f' ({svc_part})' if svc_part else ''}...")
    if not run_command(f"docker compose up -d {svc_part}".strip(), cwd=compose_dir):
        print_error(f"{label}: docker compose up failed.")
        return False

    if wait_postgres and not wait_for_postgres_ready_local():
        return False

    expected = _expected_running_count_local(compose_dir, services)
    if expected == 0 and not wait_postgres:
        print_warning(f"{label}: could not read service list; assuming startup succeeded.")
        return True

    print_info(f"Verifying {label} containers are running...")
    deadline = time.time() + COMPOSE_UP_MAX_WAIT
    while time.time() < deadline:
        running = _running_compose_ids_local(compose_dir)
        if len(running) >= expected:
            print_success(f"{label}: {len(running)} container(s) running.")
            return True
        time.sleep(COMPOSE_UP_INTERVAL)

    _, status, _ = local_shell("docker compose ps", cwd=compose_dir)
    print_error(f"{label}: startup verification failed.")
    if status:
        print_error(status)
    return False

def start_compose_stack_ssh(ssh, compose_dir, label, services=None, wait_postgres=False):
    """Start docker compose stack over SSH and verify containers are running."""
    exit_code, _, _ = ssh_shell(ssh, f"test -d {compose_dir} && test -f {compose_dir}/docker-compose.yml")
    if exit_code != 0:
        print_error(f"{label}: compose project not found at {compose_dir}")
        return False

    svc_part = " ".join(services) if services else ""
    print_info(f"Starting {label} containers{f' ({svc_part})' if svc_part else ''}...")
    exit_code, _, err = ssh_shell(ssh, f"cd {compose_dir} && docker compose up -d {svc_part}".strip())
    if exit_code != 0:
        print_error(f"{label}: docker compose up failed.")
        if err:
            print_error(err)
        return False

    if wait_postgres and not wait_for_postgres_ready_ssh(ssh):
        return False

    expected = _expected_running_count_ssh(ssh, compose_dir, services)
    if expected == 0 and not wait_postgres:
        print_warning(f"{label}: could not read service list; assuming startup succeeded.")
        return True

    print_info(f"Verifying {label} containers are running...")
    deadline = time.time() + COMPOSE_UP_MAX_WAIT
    while time.time() < deadline:
        running = _running_compose_ids_ssh(ssh, compose_dir)
        if len(running) >= expected:
            print_success(f"{label}: {len(running)} container(s) running.")
            return True
        time.sleep(COMPOSE_UP_INTERVAL)

    _, status, _ = ssh_shell(ssh, f"cd {compose_dir} && docker compose ps")
    print_error(f"{label}: startup verification failed.")
    if status:
        print_error(status)
    return False

def send_telegram_file(token, chat_id, file_path, caption=""):
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    
    if not os.path.exists(file_path):
        return False, "File not found"

    try:
        with open(file_path, "rb") as f:
            file_content = f.read()
    except Exception as e:
        return False, f"Read error: {e}"

    file_name = os.path.basename(file_path)
    parts = []
    
    parts.append(f"--{boundary}".encode('utf-8'))
    parts.append(f'Content-Disposition: form-data; name="chat_id"'.encode('utf-8'))
    parts.append(b'')
    parts.append(str(chat_id).encode('utf-8'))
    
    if caption:
        parts.append(f"--{boundary}".encode('utf-8'))
        parts.append(f'Content-Disposition: form-data; name="caption"'.encode('utf-8'))
        parts.append(b'')
        parts.append(caption.encode('utf-8'))
        
    parts.append(f"--{boundary}".encode('utf-8'))
    parts.append(f'Content-Disposition: form-data; name="document"; filename="{file_name}"'.encode('utf-8'))
    parts.append(b'Content-Type: application/zip')
    parts.append(b'')
    parts.append(file_content)
    
    parts.append(f"--{boundary}--".encode('utf-8'))
    parts.append(b'')
    
    body = b'\r\n'.join(parts)
    
    req = urllib.request.Request(url, data=body)
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    req.add_header('Content-Length', str(len(body)))
    
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode('utf-8')
            return True, res_body
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8')
        return False, f"HTTP Error {e.code}: {err_msg}"
    except Exception as e:
        return False, f"Connection error: {e}"

def create_backup():
    print_info("Starting Backup Generation...")
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_name = f"backup_{timestamp}"

    current_dir = os.getcwd() 
    tmp_dir = os.path.join("/tmp", backup_name)
    final_zip_base = os.path.join(current_dir, backup_name)
    expected_zip_file = f"{final_zip_base}.zip"

    # Pasarguard paths
    opt_dir = "/opt/pasarguard"
    data_dir = "/var/lib/pasarguard"

    # PG-Node paths
    pg_node_opt_dir_src = "/opt/pg-node"
    pg_node_data_dir_src = "/var/lib/pg-node"

    # Temp structure
    pg_dump_dir = os.path.join(tmp_dir, "pg_dump")
    pasarguard_data_dir = os.path.join(tmp_dir, "pasarguard_data")
    pg_node_opt_dir_dest = os.path.join(tmp_dir, "pg_node_opt")
    pg_node_data_dir_dest = os.path.join(tmp_dir, "pg_node_data")

    try:
        print_info("Creating temporary directories...")
        os.makedirs(pg_dump_dir, exist_ok=True)

        print_info("Copying Pasarguard configuration files...")
        if os.path.exists(os.path.join(opt_dir, "docker-compose.yml")):
            shutil.copy(os.path.join(opt_dir, "docker-compose.yml"), tmp_dir)
        if os.path.exists(os.path.join(opt_dir, ".env")):
            shutil.copy(os.path.join(opt_dir, ".env"), tmp_dir)

        print_info("Exporting PostgreSQL globals... (This may take a moment)")
        cmd_globals = "docker compose exec -T timescaledb pg_dumpall -U pasarguard --globals-only"
        run_command(cmd_globals, output_file=os.path.join(pg_dump_dir, "globals.sql"), cwd=opt_dir)

        print_info("Exporting Pasarguard database... (Please wait, this might take a while for large databases)")
        cmd_db = "docker compose exec -T timescaledb pg_dump -U pasarguard -d pasarguard"
        run_command(cmd_db, output_file=os.path.join(pg_dump_dir, "db-001.sql"), cwd=opt_dir)

        print_info("Creating manifest file...")
        with open(os.path.join(pg_dump_dir, "manifest.tsv"), "w") as f:
            f.write("pasarguard\tpasarguard\t1\tdb-001.sql\t2.28.1\n")

        print_info("Copying Pasarguard data directory...")
        if os.path.exists(data_dir):
            shutil.copytree(data_dir, pasarguard_data_dir)
        else:
            print_warning(f"Data directory {data_dir} not found. Skipping...")

        # -- PG-Node Backup --
        print_info("Copying PG-Node configuration directory (/opt/pg-node)...")
        if os.path.exists(pg_node_opt_dir_src):
            shutil.copytree(pg_node_opt_dir_src, pg_node_opt_dir_dest)
        else:
            print_warning(f"Directory {pg_node_opt_dir_src} not found. Skipping...")

        print_info("Copying PG-Node data directory (/var/lib/pg-node)...")
        if os.path.exists(pg_node_data_dir_src):
            shutil.copytree(pg_node_data_dir_src, pg_node_data_dir_dest)
        else:
            print_warning(f"Directory {pg_node_data_dir_src} not found. Skipping...")

        print_info("Compressing all files into a ZIP archive... (Please wait)")
        shutil.make_archive(final_zip_base, 'zip', tmp_dir)

        print_info("Cleaning up temporary files...")
        shutil.rmtree(tmp_dir)

        print_success(f"Backup created successfully: {expected_zip_file}")
        return expected_zip_file

    except Exception as e:
        print_error(f"Unexpected error during backup: {e}")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

def execute_ssh_command(ssh, command, description, required=True):
    print(f"{Colors.CYAN}🌐 [SSH]{Colors.RESET} {description}...")
    exit_status, out, err = ssh_shell(ssh, command)

    if exit_status == 0:
        print_success("Done.")
    else:
        print_error("Command failed!")
        if err:
            print_error(f"Details: {err}")
        elif out:
            print_error(f"Details: {out}")
    return exit_status == 0 if required else True

def workflow_auto_backup_restore():
    print_header("Auto Backup & Transfer to New Server")
    
    # 1. Create Backup
    zip_file_path = create_backup()
    if not zip_file_path or not os.path.exists(zip_file_path):
        print_error("Aborting process due to backup failure.")
        return

    # 2. Telegram Options
    print("")
    send_to_tg = input(f"{Colors.CYAN}🤖 Do you want to send this backup to a Telegram Bot first? (y/n): {Colors.RESET}").strip().lower()
    if send_to_tg == 'y':
        bot_token = input(f"{Colors.CYAN}🔑 Enter Telegram Bot Token: {Colors.RESET}").strip()
        admin_id = input(f"{Colors.CYAN}👤 Enter Admin Numeric Chat ID: {Colors.RESET}").strip()
        
        print_info("Uploading backup to Telegram (Please wait)...")
        caption = f"📦 Pasarguard & PG-Node Manual Transfer Backup\nDate: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        success, details = send_telegram_file(bot_token, admin_id, zip_file_path, caption=caption)
        if success:
            print_success("Backup sent to Telegram successfully!")
        else:
            print_error(f"Telegram upload failed: {details}")

    # 3. New Server Details
    print(f"\n{Colors.BOLD}--- New Server Information ---{Colors.RESET}")
    new_server_ip = input(f"{Colors.CYAN}🖥️  Enter New Server IP: {Colors.RESET}").strip()
    
    is_root = input(f"{Colors.CYAN}⚠️  User MUST be root. Do you confirm? (y/n): {Colors.RESET}").strip().lower()
    if is_root != 'y':
        print_error("Root access is required. Aborting...")
        return
        
    new_server_pass = input(f"{Colors.CYAN}🔑 Enter Root Password: {Colors.RESET}").strip()

    # 4. SSH Process
    print_info(f"Connecting to {new_server_ip}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(hostname=new_server_ip, username='root', password=new_server_pass, timeout=10)
        print_success("Connected to the new server!")
        print("")
        
        execute_ssh_command(ssh, "apt-get update >/dev/null 2>&1 && apt-get install -y unzip >/dev/null 2>&1", "Installing 'unzip' package silently")

        # Stop PG-Node first, then Pasarguard (separate compose projects in two folders)
        if not stop_compose_stack_ssh(ssh, PG_NODE_DIR, "PG-Node"):
            print_error("Aborting: PG-Node containers could not be stopped cleanly.")
            return
        if not stop_compose_stack_ssh(ssh, PASARGUARD_DIR, "Pasarguard"):
            print_error("Aborting: Pasarguard containers could not be stopped cleanly.")
            return

        if not clean_restore_directories_ssh(ssh):
            print_error("Aborting: directory cleanup failed.")
            return

        # Upload zip
        print(f"{Colors.CYAN}🌐 [SSH]{Colors.RESET} Uploading backup file (This depends on your internet speed)...")
        sftp = ssh.open_sftp()
        zip_filename = os.path.basename(zip_file_path)
        remote_zip_path = f"/opt/pasarguard/{zip_filename}"
        sftp.put(zip_file_path, remote_zip_path)
        sftp.close()
        print_success("Upload completed.")

        # Extract files
        execute_ssh_command(ssh, f"cd /opt/pasarguard && unzip -q -o {zip_filename}", "Extracting files (This may take a moment)")
        
        # Distribute Pasarguard Data and PG-Node
        if not execute_ssh_command(ssh, "cp -a /opt/pasarguard/pasarguard_data/. /var/lib/pasarguard/ 2>/dev/null || true && rm -rf /opt/pasarguard/pasarguard_data", "Restoring Pasarguard data"):
            print_error("Aborting: failed to restore Pasarguard data.")
            return
        if not execute_ssh_command(ssh, "cp -a /opt/pasarguard/pg_node_opt/. /opt/pg-node/ 2>/dev/null || true && rm -rf /opt/pasarguard/pg_node_opt", "Restoring PG-Node configuration"):
            print_error("Aborting: failed to restore PG-Node configuration.")
            return
        if not execute_ssh_command(ssh, "cp -a /opt/pasarguard/pg_node_data/. /var/lib/pg-node/ 2>/dev/null || true && rm -rf /opt/pasarguard/pg_node_data", "Restoring PG-Node data"):
            print_error("Aborting: failed to restore PG-Node data.")
            return

        # Start database only, wait until PostgreSQL is fully ready, then restore
        if not start_compose_stack_ssh(ssh, PASARGUARD_DIR, "Pasarguard DB", services=["timescaledb"], wait_postgres=True):
            print_error("Aborting: timescaledb did not start correctly.")
            return

        if not execute_ssh_command(ssh, 'cd /opt/pasarguard && docker compose exec -T timescaledb psql -U pasarguard -d postgres -c "DROP DATABASE IF EXISTS pasarguard WITH (FORCE);"', "Dropping old database to prevent conflicts"):
            print_error("Aborting: failed to drop old database.")
            return
        if not execute_ssh_command(ssh, 'cd /opt/pasarguard && docker compose exec -T timescaledb psql -U pasarguard -d postgres -c "CREATE DATABASE pasarguard;"', "Creating a fresh, clean database"):
            print_error("Aborting: failed to create database.")
            return

        if not execute_ssh_command(ssh, "cd /opt/pasarguard && cat pg_dump/globals.sql | docker compose exec -T timescaledb psql -U pasarguard", "Restoring globals.sql"):
            print_error("Aborting: failed to restore globals.sql.")
            return
        if not execute_ssh_command(ssh, "cd /opt/pasarguard && cat pg_dump/db-001.sql | docker compose exec -T timescaledb psql -U pasarguard -d pasarguard", "Restoring db-001.sql (Please wait, this might take a while for large databases)"):
            print_error("Aborting: failed to restore db-001.sql.")
            return

        # Start full Pasarguard stack, then PG-Node — verify both are running
        if not start_compose_stack_ssh(ssh, PASARGUARD_DIR, "Pasarguard"):
            print_error("Aborting: Pasarguard containers did not start correctly.")
            return
        if not start_compose_stack_ssh(ssh, PG_NODE_DIR, "PG-Node"):
            print_error("Aborting: PG-Node containers did not start correctly.")
            return

        print_header("Transfer & Restore Completed Successfully! 🎉")
        print_success("Verified: Pasarguard and PG-Node Docker stacks are running on the new server.")

    except paramiko.AuthenticationException:
        print_error("Incorrect server password!")
    except Exception as e:
        print_error(f"Server connection error: {e}")
    finally:
        ssh.close()
        try:
            if os.path.exists(zip_file_path):
                os.remove(zip_file_path)
        except:
            pass

def workflow_backup_bot():
    print_header("Auto Backup to Telegram Bot (Scheduled)")
    
    bot_token = input(f"{Colors.CYAN}🔑 Enter Telegram Bot Token: {Colors.RESET}").strip()
    while not bot_token:
        bot_token = input(f"{Colors.RED}Token cannot be empty!{Colors.RESET} {Colors.CYAN}Enter Bot Token:{Colors.RESET} ").strip()

    admin_id = input(f"{Colors.CYAN}👤 Enter Admin Numeric Chat ID: {Colors.RESET}").strip()
    while not admin_id or not admin_id.lstrip('-').isdigit():
        admin_id = input(f"{Colors.RED}Invalid ID!{Colors.RESET} {Colors.CYAN}Enter Admin Numeric Chat ID:{Colors.RESET} ").strip()

    try:
        interval_input = input(f"{Colors.CYAN}⏱️  Enter interval in hours (e.g., 0.5 for 30 mins, 1 for 1 hour): {Colors.RESET}").strip()
        interval_hours = float(interval_input)
    except ValueError:
        print_warning("Invalid number. Defaulting to 1.0 hour.")
        interval_hours = 1.0

    interval_seconds = int(interval_hours * 3600)
    print_info(f"Scheduler started! Backups will run every {interval_hours} hours.")
    print_warning("Press Ctrl+C at any time to stop this utility.")
    print("-" * 50)

    try:
        while True:
            current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n{Colors.BOLD}⏳ Starting scheduled task at {current_time_str}...{Colors.RESET}")
            
            zip_file_path = create_backup()
            
            if zip_file_path and os.path.exists(zip_file_path):
                print_info("Uploading to Telegram...")
                caption = f"🤖 Pasarguard & PG-Node Auto Backup\nDate: {current_time_str}\nInterval: {interval_hours} hrs"
                success, details = send_telegram_file(bot_token, admin_id, zip_file_path, caption=caption)
                
                if success:
                    print_success("Backup sent to Telegram!")
                else:
                    print_error(f"Failed to send to Telegram: {details}")
                
                try:
                    os.remove(zip_file_path)
                    print_info("Local ZIP file removed to save disk space.")
                except Exception:
                    pass
            else:
                print_error("Backup failed. Skipping Telegram upload.")

            print_info(f"Sleeping for {interval_hours} hours... (Zzz)")
            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}🚪 Backup scheduler stopped by user.{Colors.RESET}")

def workflow_manual_backup():
    print_header("Manual Backup (Local)")
    print_info("This will create a backup and save it in the current directory.")
    
    zip_file_path = create_backup()
    
    if zip_file_path and os.path.exists(zip_file_path):
        print_success(f"Manual backup completed! Your file is safe at: {zip_file_path}")
    else:
        print_error("Manual backup failed!")

def workflow_manual_restore():
    print_header("Manual Restore (Local)")
    print_info("This process will wipe the current Pasarguard & PG-Node setup and restore from a ZIP file.")
    
    zip_name = input(f"{Colors.CYAN}📦 Enter the exact Backup ZIP file name (e.g. backup_2026.zip): {Colors.RESET}").strip()
    
    if not os.path.exists(zip_name):
        print_error(f"Cannot find the file '{zip_name}' in the current directory!")
        return

    confirm = input(f"{Colors.RED}⚠️  WARNING: This will overwrite your current configuration and database. Continue? (y/n): {Colors.RESET}").strip().lower()
    if confirm != 'y':
        print_warning("Restore process aborted by user.")
        return

    try:
        # Step 1: Stop both Docker stacks (two separate folders), then clean
        if not stop_compose_stack_local(PG_NODE_DIR, "PG-Node"):
            print_error("Aborting: PG-Node containers could not be stopped cleanly.")
            return
        if not stop_compose_stack_local(PASARGUARD_DIR, "Pasarguard"):
            print_error("Aborting: Pasarguard containers could not be stopped cleanly.")
            return

        if not clean_restore_directories_local():
            print_error("Aborting: directory cleanup failed.")
            return
        
        # Step 2: Extract files
        print_info("Extracting backup files (This may take a moment)...")
        if not run_command(f"unzip -q -o {zip_name} -d /opt/pasarguard"):
            print_error("Failed to extract backup archive.")
            return
        
        print_info("Restoring PG-Node and Pasarguard files...")
        run_command("cp -a /opt/pasarguard/pasarguard_data/. /var/lib/pasarguard/ 2>/dev/null || true")
        run_command("cp -a /opt/pasarguard/pg_node_opt/. /opt/pg-node/ 2>/dev/null || true")
        run_command("cp -a /opt/pasarguard/pg_node_data/. /var/lib/pg-node/ 2>/dev/null || true")
        run_command("rm -rf /opt/pasarguard/pg_node_opt /opt/pasarguard/pg_node_data /opt/pasarguard/pasarguard_data")
        
        # Step 3: Start DB only and wait until PostgreSQL is fully ready
        if not start_compose_stack_local(PASARGUARD_DIR, "Pasarguard DB", services=["timescaledb"], wait_postgres=True):
            raise Exception("timescaledb did not start correctly")
        
        # Step 4: Drop and Recreate DB
        print_info("Dropping old database to prevent conflicts...")
        if not run_command('cd /opt/pasarguard && docker compose exec -T timescaledb psql -U pasarguard -d postgres -c "DROP DATABASE IF EXISTS pasarguard WITH (FORCE);"'):
            raise Exception("Failed to drop old database")
        
        print_info("Creating a fresh, clean database...")
        if not run_command('cd /opt/pasarguard && docker compose exec -T timescaledb psql -U pasarguard -d postgres -c "CREATE DATABASE pasarguard;"'):
            raise Exception("Failed to create database")

        # Step 5: Restore DBs
        print_info("Restoring PostgreSQL globals...")
        if not run_command("cd /opt/pasarguard && cat pg_dump/globals.sql | docker compose exec -T timescaledb psql -U pasarguard"):
            raise Exception("Failed to restore globals.sql")
            
        print_info("Restoring Pasarguard database... (Please wait, this might take a while for large databases)")
        if not run_command("cd /opt/pasarguard && cat pg_dump/db-001.sql | docker compose exec -T timescaledb psql -U pasarguard -d pasarguard"):
            raise Exception("Failed to restore db-001.sql")
            
        # Step 6: Start full stacks and verify both are running
        if not start_compose_stack_local(PASARGUARD_DIR, "Pasarguard"):
            raise Exception("Pasarguard containers did not start correctly")
        if not start_compose_stack_local(PG_NODE_DIR, "PG-Node"):
            raise Exception("PG-Node containers did not start correctly")
        
        print_header("Local Restore Completed Successfully! 🎉")
        print_success("Verified: Pasarguard and PG-Node Docker stacks are running.")

    except Exception as e:
        print_error(f"An error occurred during restoration: {e}")
        print_warning("Your system might be in a partially restored state.")

def main():
    while True:
        # Clear screen
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print(f"\n{Colors.HEADER}{Colors.BOLD}=================================================={Colors.RESET}")
        print(f"{Colors.HEADER}{Colors.BOLD}          🛡️  PASARGUARD MANAGER UTILITY 🛡️           {Colors.RESET}")
        print(f"{Colors.HEADER}{Colors.BOLD}=================================================={Colors.RESET}")
        print(f"{Colors.CYAN}       Dev by: Sin Kabir{Colors.RESET}")
        print(f"{Colors.CYAN}       GitHub: https://github.com/c-Nojoom/PasarGuard-bk.re/{Colors.RESET}")
        print(f"{Colors.HEADER}{Colors.BOLD}=================================================={Colors.RESET}\n")
        print(f"{Colors.BLUE}1-{Colors.RESET} 🚀 Auto Backup & Transfer to New Server")
        print(f"{Colors.BLUE}2-{Colors.RESET} 🤖 Auto Backup to Telegram Bot (Scheduled)")
        print(f"{Colors.BLUE}3-{Colors.RESET} 💾 Manual Backup (Save locally)")
        print(f"{Colors.BLUE}4-{Colors.RESET} 🔄 Manual Restore (From local zip)")
        print(f"{Colors.RED}5-{Colors.RESET} 🚪 Exit")
        print(f"{Colors.HEADER}--------------------------------------------------{Colors.RESET}")
        
        choice = input(f"{Colors.CYAN}👉 Please select an option (1-5): {Colors.RESET}").strip()
        
        if choice == '1':
            workflow_auto_backup_restore()
            pause_and_return()
        elif choice == '2':
            workflow_backup_bot()
            pause_and_return()
        elif choice == '3':
            workflow_manual_backup()
            pause_and_return()
        elif choice == '4':
            workflow_manual_restore()
            pause_and_return()
        elif choice == '5':
            print(f"{Colors.YELLOW}🚪 Exiting... Have a great day!{Colors.RESET}")
            sys.exit(0)
        else:
            print_error("Invalid option! Please try again.")
            time.sleep(2)

if __name__ == "__main__":
    main()
