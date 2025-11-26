#!/bin/bash
# Script de backup automático para ZenzSpa
# Requiere variables de entorno: DB_HOST, DB_USER, DB_NAME, PGPASSWORD (o .pgpass)

BACKUP_DIR="/var/backups/zenzspa"
mkdir -p $BACKUP_DIR

DATE=$(date +%Y%m%d_%H%M%S)
FILENAME="$BACKUP_DIR/zenzspa_$DATE.sql.gz"

echo "Iniciando backup de $DB_NAME en $DATE..."

# Realizar dump y comprimir
if pg_dump -h $DB_HOST -U $DB_USER $DB_NAME | gzip > $FILENAME; then
    echo "Backup exitoso: $FILENAME"
else
    echo "Error al realizar backup"
    exit 1
fi

# Mantener solo últimos 30 días
echo "Limpiando backups antiguos..."
find $BACKUP_DIR -name "zenzspa_*.sql.gz" -mtime +30 -delete

echo "Proceso completado."
