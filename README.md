
# pg-backup – Guia Rápido

Este projeto automatiza o backup de bancos PostgreSQL com suporte a **Rclone** e armazenamento em nuvem como o **S3 da MagaluCloud**.

---

## 1. Instalação e Configuração Inicial

### 1.1. Download

Faça o download e extração do pacote:

```bash
git clone git@github.com:henrique559/pgbackup.git
```

### 1.2. Instalação de Dependências

#### Rclone

Instale o **Rclone** com o script incluso:

```bash
sudo ./rclone-install.sh
```

#### Python & Dependências

Instale o `pip` (caso ainda não esteja instalado) e as dependências do projeto:

```bash
sudo apt install -y python3-pip
pip install -r requirements.txt --break-system-packages
```

> **Dica**: use `--break-system-packages` somente se for necessário. Avalie o uso de ambientes virtuais (`venv`) para evitar conflitos.

##  Instalação do PostgreSQL e `pg_basebackup`

Para que o script funcione corretamente, é necessário ter o cliente PostgreSQL instalado, especialmente a ferramenta `pg_basebackup`, usada para fazer os backups binários. Siga esses passos:

```bash
# Instale o pacote de utilitários do PostgreSQL
sudo apt install -y postgresql-common

# Adicione o repositório oficial do PostgreSQL
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh

# Instale a versão desejada (ex: PostgreSQL 16)
sudo apt install -y postgresql-16
```

> Isso instalará os binários do cliente, incluindo `pg_basebackup`, que é essencial para o script de backup.

> **Dica:** Se você _não precisa de um servidor PostgreSQL local_, pode instalar apenas os pacotes de cliente:

```bash
sudo apt install -y postgresql-client-16
```

---

### Permissões (Opcional)

Se quiser que o usuário `postgres` execute o script, altere o dono dos arquivos:

```bash
sudo chown -R postgres:postgres [diretório-do-script]
```

> **Atenção:** Evite executar scripts diretamente como `root`. Arquivos criados como `root` podem causar erros de permissão, especialmente em arquivos de configuração.

**Boas práticas:**

- Certifique-se de que todos os arquivos de configuração sejam legíveis pelo usuário que executa o script.
- Use `ls -la` para verificar permissões.

---

## 2. Configurando o Rclone

### Iniciando a configuração

```bash
rclone config
```

> Siga o assistente interativo e selecione:
> 
> - `n` para criar uma nova configuração
> - Nome do remote: `magalu_s3` (ou o que preferir)
> - Tipo: `s3`
> - Provedor: `Magalu`
> - Endpoint: conforme a [documentação oficial da MagaluCloud](https://rclone.org/s3/#magalu)
> - Informe sua `Access Key` e `Secret Key`


Caso tenha dúvidas, siga as instruções interativas e utilize como base a [documentação oficial da Rclone para S3 da MagaluCloud](https://rclone.org/s3/#magalu).

---

### Rclone – Cheat Sheet (S3 MagaluCloud)

|Comando|Descrição|
|---|---|
|`rclone config`|Inicia o assistente de configuração interativa|
|`rclone ls magalu_s3:/meu-bucket`|Lista arquivos no bucket remoto|
|`rclone lsd magalu_s3:/`|Lista buckets disponíveis|
|`rclone mkdir magalu_s3:/novo-bucket`|Cria novo bucket|
|`rclone copy local/dir magalu_s3:/bucket`|Copia arquivos do local para o S3|
|`rclone copy magalu_s3:/bucket local/dir`|Copia arquivos do S3 para o local|
|`rclone sync local/dir magalu_s3:/bucket`|Sincroniza (apaga do destino o que não existir na origem!)|
|`rclone delete magalu_s3:/bucket/path`|Apaga arquivos/diretórios remotos (perigoso!)|
|`rclone cat magalu_s3:/bucket/file`|Mostra o conteúdo de um arquivo remoto|
|`rclone --progress ...`|Adiciona barra de progresso aos comandos|

---


> ** O nome do`magalu_s3` é um exemplo, certifique-se de colocar o nome do S3 configurado no `rclone config`.** <br>
> O arquivo `rclone.conf` será salvo automaticamente em:
 ```bash
 
  ~/.config/rclone/rclone.conf
 ```

> Mantenha esse arquivo protegido. Ele contém suas credenciais de acesso ao S3.

**Importante:** Certifique-se de que o arquivo `rclone.conf` esteja presente no diretório HOME do **usuário que executa o script** (ex: `/var/lib/postgres/.config/rclone/rclone.conf` para o usuário `postgres`).

---

## 3. Arquivos de Configuração

### `config.toml`

Arquivo principal de configuração do script. Ele define os parâmetros globais, controle de paralelismo e política de retenção de backups.

```toml
[global]
s3 = "nome"       # Nome do bucket configurado no S3 (MagaluCloud)
bucket_dir = "nome-dir" # Nome do diretório no S3 
base_dir = "/caminho/para/backups" # Diretório local onde os backups serão salvos
log_dir = "/caminho/para/logs"     # Diretório onde os logs serão armazenados
instance_file = "./instances.csv"    # Caminho para o CSV com as instâncias PostgreSQL

[parallel]
max_parallel = 5                   # Quantidade máxima de backups simultâneos

[retention]
retention_local = 3               # Dias até exclusão de backups locais
retention_rclone = 7             # Dias até exclusão de backups remotos (S3)
```

> **Importante:** Todos os diretórios devem existir ou serão criados automaticamente. O usuário que executa o script precisa ter **permissão de leitura e escrita** nesses caminhos.

---

### `rclone.conf`

Arquivo de configuração do **Rclone**, necessário para autenticação com o S3.

- Local esperado: `$HOME/.config/rclone/rclone.conf`
- Esse caminho deve ser acessível pelo **usuário que executa o script** (ex: `postgres`).

> Mantenha este arquivo seguro, ele contém credenciais de acesso ao S3.

---

### `instances.csv`

Lista das instâncias PostgreSQL a serem processadas. O script usará esse arquivo para conectar aos bancos e realizar os backups.

#### Exemplo:

```
instance_name,host,port,user
data-production,172.0.0.1,5432,masterdba
```

> **Atenção:** O usuário listado em cada linha **deve existir na instância do PostgreSQL** e **possuir a role `REPLICATION`** para que o backup funcione corretamente.

---

### `.pgpass`

Arquivo de senhas do PostgreSQL que permite autenticação sem prompt de senha.

- Local: `$HOME/.pgpass` do usuário que executa o script.
- Formato:

```
host:port:database:user:senha
```

#### Exemplo:

```
172.0.0.1:5432:*:masterdba:senha-secreta
```

> Esse arquivo deve ter permissão `600` e pertencer ao usuário do script.  
> Todas as credenciais devem estar **em sintonia** com os dados do `instances.csv`.

### Requisitos no Servidor PostgreSQL de Destino

Para que o backup funcione corretamente, o servidor PostgreSQL de **origem (de onde o backup será feito)** precisa estar devidamente preparado.

#### Requisitos obrigatórios:

1. **Usuário PostgreSQL compatível:**
- O usuário especificado no `instances.csv` e no `.pgpass` **deve existir no PostgreSQL de destino**.
- Esse usuário **precisa ter a role `REPLICATION`**.

    ```sql
  CREATE ROLE masterdba WITH LOGIN REPLICATION PASSWORD 'sua_senha';
    ```

2. **Arquivo `pg_hba.conf` configurado:**

- O servidor PostgreSQL deve permitir conexões do IP da máquina de backup.
- Adicione uma linha ao `pg_hba.conf`, exemplo:

    ```
    host    replication     masterdba     192.168.1.100/32     md5
    ```

- Dê reload nas configurações: 

    ```bash
        psql -h localhost -d postgres -c "SELECT pg_reload_conf();"
    ```

> Substitua `192.168.1.100` pelo IP real do servidor onde o script será executado e o `masterdba` com o usuário do seu banco de dados.

---

## 4. Automação com Crontab

Para agendar backups automáticos, edite o `crontab` do usuário responsável (ex: `postgres`):

```bash
crontab -e
```

#### Exemplo: rodar o backup todo dia às 3h da manhã

```cron
0 3 * * * /caminho/para/o/script/pg-backup.py >/dev/null 2>&1
```

> **Dica:** Use caminhos absolutos. O ambiente do `cron` é limitado e não carrega `.bashrc`.

---

## 5. Restaurando Backups

TODO

 
