#!/usr/bin/env python
"""
Script wrapper para ejecutar migrate con la codificación correcta en Windows.
"""
import os
import sys

# Forzar UTF-8 en todas partes
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PGCLIENTENCODING'] = 'UTF8'

# Eliminar todas las variables de locale que puedan causar problemas
# En Windows con Git Bash instalado, estas variables pueden tener valores incorrectos
locale_vars = ['LANG', 'LC_ALL', 'LC_CTYPE', 'LC_MESSAGES', 'LC_COLLATE',
               'LC_MONETARY', 'LC_NUMERIC', 'LC_TIME']
for var in locale_vars:
    if var in os.environ:
        del os.environ[var]

# Establecer locale a C (predeterminado sin problemas de codificación)
os.environ['LC_ALL'] = 'C'

# Ahora importar Django y ejecutar migrate
if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # Ejecutar migrate
    execute_from_command_line(['manage.py', 'migrate'])
