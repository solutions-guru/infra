# Database Backup Infrastructure Tool

A Python-based backup solution that automatically backs up MySQL, PostgreSQL, and MongoDB databases and uploads them to Amazon S3 (or S3-compatible storage). The tool creates compressed backups, organizes them by server, database type, and date, and automatically cleans up local files after successful upload.

## Features

- **Multi-Database Support**: Automatically detects and backs up MySQL, PostgreSQL, and MongoDB databases
- **Automatic Database Discovery**: Can enumerate databases automatically or use explicit database lists
- **S3 Upload**: Uploads backups to Amazon S3 or S3-compatible storage (e.g., MinIO, DigitalOcean Spaces)
- **Compressed Backups**: All backups are gzipped to save storage space
- **Organized Storage**: Backups are organized by server IP/hostname, database type, and date
- **Secure**: Uses environment variables for all credentials; no hardcoded secrets
- **Logging**: Creates detailed backup logs with timestamps and file information
- **Automatic Cleanup**: Automatically deletes local backup files only after successful S3 upload to save disk space
- **Error Handling**: Gracefully handles missing tools and connection failures

## Prerequisites

### Required Tools

The tool requires the appropriate database client tools to be installed on your system:

- **MySQL**: `mysqldump` and `mysql` CLI tools
- **PostgreSQL**: `pg_dump` and `psql` CLI tools
- **MongoDB**: `pymongo` Python package (uses PyMongo instead of CLI tools)

### Python Requirements

- Python 3.8 or higher
- pip package manager

### S3 Access

- An S3 bucket (or S3-compatible storage)
- S3 credentials (access key and secret key) OR AWS IAM role with S3 permissions

## Installation

1. **Clone or download this repository**

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

All configuration is done through environment variables. You can set them in your shell or use a `.env` file (recommended).

### Required Environment Variables

- `S3_BUCKET`: Name of your S3 bucket (required)

### Optional Environment Variables

#### S3 Configuration
- `S3_PREFIX`: Optional prefix for S3 keys (e.g., `backups/infra`)
- `S3_REGION`: AWS region (e.g., `us-east-1`)
- `S3_ACCESS_KEY`: S3 access key ID (if not using IAM roles)
- `S3_SECRET_KEY`: S3 secret access key (if not using IAM roles)
- `S3_ENDPOINT` or `S3_ENDPOINT_URL`: Custom S3 endpoint URL (for S3-compatible storage)

#### General Configuration
- `BACKUP_OUTPUT_DIR`: Local directory for temporary backups (default: `backups`)

#### MySQL Configuration
- `MYSQL_HOST`: MySQL host (default: `127.0.0.1`)
- `MYSQL_PORT`: MySQL port (default: `3306`)
- `MYSQL_USER`: MySQL username
- `MYSQL_PASSWORD`: MySQL password
- `MYSQL_DATABASE`: Single database to backup
- `MYSQL_DATABASES`: Comma-separated list of databases (e.g., `db1,db2,db3`)
- `MYSQL_SSL_MODE`: SSL mode (e.g., `REQUIRED`)

#### PostgreSQL Configuration
- `POSTGRES_HOST` or `PGHOST`: PostgreSQL host
- `POSTGRES_PORT` or `PGPORT`: PostgreSQL port
- `POSTGRES_USER` or `PGUSER`: PostgreSQL username
- `POSTGRES_PASSWORD` or `PGPASSWORD`: PostgreSQL password
- `POSTGRES_DATABASE` or `PGDATABASE` or `POSTGRES_DB`: Single database to backup
- `POSTGRES_DATABASES` or `PGDATABASES`: Comma-separated list of databases

#### MongoDB Configuration
- `MONGO_URI`: MongoDB connection URI (recommended, e.g., `mongodb://user:pass@host:port/`)
- `MONGO_HOST`: MongoDB host (default: `127.0.0.1`)
- `MONGO_PORT`: MongoDB port (default: `27017`)
- `MONGO_USER`: MongoDB username
- `MONGO_PASSWORD`: MongoDB password
- `MONGO_AUTH_DB`: Authentication database (default: `admin`)
- `MONGO_DATABASE`: Single database to backup
- `MONGO_DATABASES`: Comma-separated list of databases

### Example `.env` File

Create a `.env` file in the project root:

```env
# S3 Configuration
S3_BUCKET=my-backup-bucket
S3_PREFIX=backups/production
S3_REGION=us-east-1
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key

# Optional: For S3-compatible storage
# S3_ENDPOINT=https://nyc3.digitaloceanspaces.com

# General
BACKUP_OUTPUT_DIR=backups

# MySQL
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=backup_user
MYSQL_PASSWORD=secure_password
MYSQL_DATABASES=app_db,analytics_db

# PostgreSQL
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=backup_user
POSTGRES_PASSWORD=secure_password
POSTGRES_DATABASES=app_db,analytics_db

# MongoDB
MONGO_URI=mongodb://backup_user:secure_password@127.0.0.1:27017/
MONGO_DATABASES=app_db,analytics_db
```

**⚠️ Security Note**: Never commit your `.env` file to version control. Add it to `.gitignore`.

## Usage

### Basic Usage

Run the backup script:

```bash
python main.py
```

### Using the Shell Script

An example shell script (`run.sh`) is provided. Customize it for your environment:

```bash
#!/bin/bash
set -e

cd /path/to/infra/
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
python main.py
```

### Exit Codes

- `0`: Success - backups created and uploaded
- `1`: No backups were created
- `2`: S3_BUCKET environment variable missing
- `3`: S3 upload failed

## S3 Storage Structure

Backups are organized in S3 with the following structure:

```
s3://{bucket}/{prefix}/{server}/{db_type}/{YYYY-MM-DD}/{filename}
```

Example:
```
s3://my-backup-bucket/backups/production/192.168.1.100/mysql/2024-01-15/mysql_server1_app_db_20240115T120000Z.sql.gz
```

- **server**: Server IP address (preferred) or hostname
- **db_type**: `mysql`, `postgres`, or `mongo`
- **date**: Date folder in `YYYY-MM-DD` format
- **filename**: Includes hostname, database name, and UTC timestamp

## File Structure

```
infra/
├── main.py           # Main orchestration script
├── mysql.py          # MySQL backup module
├── postgres.py       # PostgreSQL backup module
├── mongo.py          # MongoDB backup module
├── upload.py         # S3 upload module
├── requirements.txt  # Python dependencies
├── run.sh            # Example shell script
└── README.md         # This file
```

## Backup File Formats

- **MySQL**: `mysql_{hostname}_{database}_{timestamp}.sql.gz`
- **PostgreSQL**: `postgres_{hostname}_{database}_{timestamp}.sql.gz`
- **MongoDB**: `mongo_{hostname}_{database}_{timestamp}.archive.gz`

All backup files are compressed with gzip and have secure permissions (`600`).

## Logging

After each backup run, a log file is created in the backup output directory:

```
backups/backup_log_{timestamp}.txt
```

The log includes:
- UTC timestamp
- S3 bucket and prefix
- List of uploaded files with sizes and S3 keys

## Automatic Cleanup

The tool automatically deletes local backup files **only after successful upload to S3**. This behavior ensures:

- **Disk space is freed** immediately after upload
- **Backups are preserved** if upload fails (allowing retry)
- **Only successfully uploaded files are deleted** (tracks upload status)

**Important Notes:**
- If S3 upload fails, local backup files are **preserved** so you can retry or investigate
- Only files that were successfully uploaded to S3 are deleted
- The log file is created before deletion, so you have a record of what was uploaded
- If deletion fails for any file, a warning is printed but the process continues

## Database Discovery

If you don't specify databases via environment variables, the tool will attempt to enumerate them:

- **MySQL**: Lists all databases except system schemas (`information_schema`, `performance_schema`, `mysql`, `sys`)
- **PostgreSQL**: Lists all databases except templates and `rdsadmin`
- **MongoDB**: Lists all databases using PyMongo (requires `MONGO_URI`)

## Examples

### Backup Specific Databases

```bash
export S3_BUCKET=my-backups
export MYSQL_DATABASES=production_db,staging_db
export POSTGRES_DATABASE=analytics_db
python main.py
```

### Using AWS IAM Roles (EC2/ECS)

If running on EC2 or ECS with an IAM role, you don't need to set `S3_ACCESS_KEY` and `S3_SECRET_KEY`:

```bash
export S3_BUCKET=my-backups
export S3_REGION=us-east-1
python main.py
```

### Using S3-Compatible Storage (MinIO)

```bash
export S3_BUCKET=my-backups
export S3_ENDPOINT=https://minio.example.com
export S3_ACCESS_KEY=minio_access_key
export S3_SECRET_KEY=minio_secret_key
python main.py
```

### Cron Job Example

Add to crontab for daily backups at 2 AM:

```bash
0 2 * * * cd /path/to/infra && /path/to/.venv/bin/python main.py >> /var/log/backup.log 2>&1
```

## Troubleshooting

### MySQL Backup Fails

- **Issue**: `mysqldump not found`
  - **Solution**: Install MySQL client tools: `sudo apt-get install mysql-client` (Ubuntu/Debian) or `brew install mysql-client` (macOS)

- **Issue**: Authentication failed
  - **Solution**: Verify `MYSQL_USER` and `MYSQL_PASSWORD` are correct

### PostgreSQL Backup Fails

- **Issue**: `pg_dump not found`
  - **Solution**: Install PostgreSQL client tools: `sudo apt-get install postgresql-client` (Ubuntu/Debian) or `brew install postgresql` (macOS)

- **Issue**: Connection refused
  - **Solution**: Check `POSTGRES_HOST` and `POSTGRES_PORT`, ensure PostgreSQL allows connections

### MongoDB Backup Fails

- **Issue**: `PyMongo not available`
  - **Solution**: Ensure `pymongo` is installed: `pip install pymongo`

- **Issue**: `MONGO_URI env var is required`
  - **Solution**: Set `MONGO_URI` with full connection string, or set individual connection parameters

### S3 Upload Fails

- **Issue**: Access denied
  - **Solution**: Verify S3 credentials have write permissions to the bucket
  - Check bucket policy and IAM permissions

- **Issue**: Endpoint URL incorrect
  - **Solution**: Verify `S3_ENDPOINT` format (include `https://`)

### No Backups Created

- Check that database tools are installed and in PATH
- Verify database connection credentials
- Ensure databases exist and are accessible
- Check that `MONGO_URI` is set for MongoDB (if using automatic discovery)

## Security Best Practices

1. **Never commit `.env` files** - Add `.env` to `.gitignore`
2. **Use IAM roles** when running on AWS infrastructure instead of access keys
3. **Restrict file permissions** - Backup files are created with `600` permissions
4. **Use strong passwords** for database backup users
5. **Limit database user permissions** - Grant only `SELECT` and backup-specific permissions
6. **Use SSL/TLS** for database connections when possible (`MYSQL_SSL_MODE=REQUIRED`)

## Dependencies

- `boto3` - AWS SDK for Python (S3 operations)
- `pymongo` - MongoDB driver for Python
- `python-dotenv` - Load environment variables from `.env` file
- Standard library modules: `os`, `subprocess`, `pathlib`, `datetime`, `socket`, `gzip`, `tarfile`

See `requirements.txt` for exact versions.

## License

[Specify your license here]

## Contributing

[Add contribution guidelines if applicable]

## Support

For issues and questions, please [create an issue](link-to-issues) or contact the maintainers.

