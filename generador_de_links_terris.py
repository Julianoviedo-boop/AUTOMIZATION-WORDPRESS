#!/usr/bin/env python3
"""
generador_de_links_terris.py

Escanea una carpeta (por defecto: "imagenes-a-optimizar/closet-de-narnia-formato-cambiado"),
obtiene los nombres de las imágenes, genera un archivo TXT y muestra en consola
solamente los links con la estructura:

https://terris.com.co/wp-content/uploads/<YYYY>/<MM>/<NOMBRE-SIN-EXTENSION>-scaled.webp

La parte <YYYY>/<MM>/ se calcula dinámicamente con la fecha actual en la zona horaria de Bogotá.

Uso:
    python generador_de_links_terris.py
    python generador_de_links_terris.py --folder "ruta/a/mi/carpeta" --out linksProductos.txt
    python generador_de_links_terris.py --base-url "https://otrodominio.com/wp-content/uploads"  # si quieres anular dominio

El archivo de salida por defecto se llama: linksProductos.txt
"""

from pathlib import Path
import argparse
import re
import sys
from datetime import datetime

# Intentar usar zoneinfo (stdlib en Python 3.9+). Si no está, se usa la hora local como fallback.
try:
    from zoneinfo import ZoneInfo
    ZONEINFO_AVAILABLE = True
except Exception:
    ZoneInfo = None
    ZONEINFO_AVAILABLE = False

def get_bogota_year_month(tz_name="America/Bogota"):
    """
    Retorna (year_str, month_str) con la fecha actual en la zona horaria dada.
    Si zoneinfo no está disponible, usa la hora local del sistema.
    """
    if ZONEINFO_AVAILABLE:
        try:
            now = datetime.now(ZoneInfo(tz_name))
        except Exception:
            now = datetime.now()
    else:
        now = datetime.now()
    return str(now.year), f"{now.month:02d}"

def slugify(name: str) -> str:
    """Convierte un nombre en una forma apta para URL según reglas simples"""
    s = name
    s = s.replace(' ', '-')
    s = s.replace('(', '').replace(')', '')
    # quitar caracteres no alfanuméricos ni guion/underscore
    s = re.sub(r"[^\w\-]", '', s)
    # colapsar guiones repetidos
    s = re.sub(r"-+", '-', s)
    s = s.strip('-')
    return s

def build_link(base_url: str, filename: str) -> str:
    """
    Construye el link final. base_url debe ser la parte hasta el mes (sin slash final preferible).
    Ejemplo base_url: 'https://terris.com.co/wp-content/uploads/2025/08'
    """
    stem = Path(filename).stem
    # quitar sufijos como -scaled o _scaled al final del stem
    stem = re.sub(r"[-_]?scaled$", '', stem, flags=re.IGNORECASE)
    safe = slugify(stem)
    # garantizar que base_url termine sin slash simple para concatenar con '/'
    base = base_url.rstrip('/')
    return f"{base}/{safe}-scaled.webp"

def main():
    parser = argparse.ArgumentParser(description='Genera un TXT con links de imágenes para Terris')
    parser.add_argument('--folder', '-f', type=str,
                        default='imagenes-a-optimizar/closet-de-narnia-formato-cambiado',
                        help='Ruta a la carpeta que contiene las imágenes')
    parser.add_argument('--base-url', '-b', type=str,
                        default=None,
                        help=('Base de la URL hasta el mes (sin barra final). '
                              'Si no se pasa, se usará: https://terris.com.co/wp-content/uploads/<YYYY>/<MM>'))
    parser.add_argument('--out', '-o', type=str, default='linksProductos.txt',
                        help='Nombre del archivo de salida TXT')
    parser.add_argument('--tz', type=str, default='America/Bogota',
                        help='Zona horaria para calcular YYYY/MM (por defecto: America/Bogota)')

    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists() or not folder.is_dir():
        print(f"ERROR: la carpeta especificada no existe o no es un directorio: {folder}")
        sys.exit(1)

    # Determinar la base URL: si se pasa --base-url la usamos tal cual; si no, construimos con la fecha actual en TZ
    if args.base_url:
        base_url = args.base_url.rstrip('/')
    else:
        year, month = get_bogota_year_month(args.tz)
        base_url = f"https://terris.com.co/wp-content/uploads/{year}/{month}"

    image_suffixes = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.tiff', '.bmp', '.avif'}
    files = [p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in image_suffixes]

    if not files:
        print(f"No se encontraron imágenes en: {folder}")
        sys.exit(0)

    links = []
    print(f"Encontradas {len(files)} imágenes en: {folder}\n")
    print(f"Usando base_url: {base_url}\n")

    for p in files:
        link = build_link(base_url, p.name)
        links.append(link)
        print(link)

    try:
        out_path = Path(args.out)
        with out_path.open('w', encoding='utf-8') as f:
            for link in links:
                f.write(link + '\n')
        print(f"\nArchivo generado: {out_path.resolve()}")
    except Exception as e:
        print(f"Error al escribir el archivo de salida: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

