# Requisitos para execução do backup do banco de dados PostgreSQL
# Python 3.8+
# pg_basebackup, rclone, gzip instalados e disponíveis no PATH
# .pgpass configurado para autenticação automática
# Arquivo instances.csv com colunas: name,host,port,user

# RECURSOS DO BACKUP
# Backup paralelizado (asyncio)	✅
# Retenção local automática	✅
# Retenção remota rclone	✅
# Log global e por instância	✅
# Upload dos backups	✅

import os
import csv
import asyncio
import time
from rclone_python import rclone
from rclone_python.remote_types import RemoteTypes
from datetime import datetime, timedelta
import tomllib

# === CONFIGS GLOBAIS ===

with open("config.toml", 'rb') as config_file:
    config = tomllib.load(config_file)

S3 = config["global"]["s3"]
S3_DIR = config["global"]["bucket_dir"]
BASE_BACKUP_DIR = config["global"]["base_dir"]
TEMP_DIR =  config["global"]["log_dir"]
INSTANCE_CSV = config["global"]["instance_file"]
MAX_PARALLEL = config["parallel"]["max_parallel"]
RETENTION_LOCAL_DAYS = config["retention"]["retention_local"]
RETENTION_DAYS = config["retention"]["retention_rclone"]
TIMESTAMP = datetime.now().strftime("%Y-%m-%d-%H-%M")
GLOBAL_LOG_FILE = os.path.join(TEMP_DIR, f"backup_log_{TIMESTAMP}.txt")

# === Função de log global ===
def log(msg, file=GLOBAL_LOG_FILE):
    timestamp = datetime.now().isoformat()
    entry = f"{timestamp} - {msg}"
    print(entry)
    with open(file, "a") as f:
        f.write(entry + "\n")

# === Setup inicial ===
def setup_environment():
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(BASE_BACKUP_DIR, exist_ok=True)
    rclone.mkdir(f"{S3}:{S3_DIR}")
    log("🔄 Início do backup PostgreSQL Multi-Instância")


# === Função de backup com log por instância ===
async def backup_instance(name, host, port, user, semaphore):
    backup_file = f"{name}_{TIMESTAMP}.tar.zst"
    backup_path = os.path.join(BASE_BACKUP_DIR, backup_file)
    inst_log = os.path.join(TEMP_DIR, f"{name}_log_{TIMESTAMP}.txt")

    async with semaphore:
        log(f"➡️  [{name}] Iniciando backup de {host}:{port}", inst_log)

        try:
            process = await asyncio.create_subprocess_exec(
                "pg_basebackup",
                "-h", host,
                "-p", port,
                "-U", user,
                "-D", "-",
                "-F", "tar",
                "--compress=zstd:5",
                "--checkpoint=fast",
                "-P",
                "-R",
                "--wal-method=fetch",
                "-v",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            with open(backup_path, "wb") as out_file:
                while True:
                    chunk = await process.stdout.read(4096)
                    if not chunk:
                        break
                    out_file.write(chunk)

            await process.wait()
 
            if process.returncode == 0:
                log(f"✅ [{name}] Backup completo: {backup_file}", inst_log)
                rclone.copy(backup_path, f"{S3}:/{S3_DIR}/{name}")
                rclone.copy(inst_log, f"{S3}:/{S3_DIR}/{name}")

            else:
                log(f"❌ [{name}] Falha no pg_basebackup", inst_log)
                if os.path.exists(backup_path):
                    os.remove(backup_path)

        except Exception as e:
            log(f"❌ [{name}] Exceção: {e}", inst_log)
            if os.path.exists(backup_path):
                os.remove(backup_path)

# === Apaga arquivos antigos localmente ===
def delete_old_backups_local(directory, days):
    now = time.time()
    threshold = now - (days * 86400)
    log(f"🧹 Limpando backups locais com mais de {days} dias...")

    for file in os.listdir(directory):
        if file.endswith(".tar.zst"):
            path = os.path.join(directory, file)
            if os.path.getmtime(path) < threshold:
                try:
                    os.remove(path)
                    log(f"🗑️  Arquivo local removido: {file}")
                except Exception as e:
                    log(f"⚠️  Erro ao remover {file}: {e}")

# === Apaga arquivos antigos no rclone (remoto) por instância ===
async def delete_old_backups_remote(instance_name, days):
    try:
        threshold_date = datetime.now() - timedelta(days=days)
        cmd = ["rclone", "lsjson", f"{S3}:/{S3_DIR}/{instance_name}"]


        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()

        import json
        files = json.loads(stdout)

        for f in files:
            if f.get("IsDir"):
                continue
            if f["Name"].endswith(".tar.zst") or f["Name"].endswith(".txt"):
                modified = datetime.strptime(f["ModTime"][:19], "%Y-%m-%dT%H:%M:%S")
                if modified < threshold_date:
                    path = f"{S3}:/{S3_DIR}/{instance_name}/{f['Name']}"
                    rclone.delete(path)
                    log(f"🗑️  [remoto] {instance_name} - arquivo removido: {f['Name']}")

    except Exception as e:
        log(f"⚠️  Erro ao aplicar retenção remota para {instance_name}: {e}")

# === Loop principal ===
async def run_all_backups():
    semaphore = asyncio.Semaphore(MAX_PARALLEL)
    tasks = []

    instance_names = []

    with open(INSTANCE_CSV, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            name = row["instance_name"]
            instance_names.append(name)
            tasks.append(
                backup_instance(name, row["host"], row["port"], row["user"], semaphore)
            )

    await asyncio.gather(*tasks)

    # Aplica retenção remota por instância
    retention_tasks = [delete_old_backups_remote(name, RETENTION_DAYS) for name in instance_names]
    await asyncio.gather(*retention_tasks)

# === Execução principal ===
def main():
    setup_environment()
    asyncio.run(run_all_backups())
    delete_old_backups_local(BASE_BACKUP_DIR, RETENTION_LOCAL_DAYS)
    log("✅ Todos os backups e limpezas foram concluídos.")

if __name__ == "__main__":
    main()
