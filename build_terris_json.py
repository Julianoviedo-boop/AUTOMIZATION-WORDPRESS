#!/usr/bin/env python3
"""
build_terris_json.py

Lee un archivo TXT con URLs de imágenes de productos (una por línea), las agrupa por <PREFIX> y <COLOR VARIATION> según el nombre del archivo, y genera un JSON estructurado listo para que otro sistema lo convierta en CSV/Excel para WooCommerce.

Escalable: funciona con miles de líneas, sin límites artificiales.

Ejemplo de nombres esperados (flexibles):
  https://.../01-AZUL BLANCO(1)-scaled.webp
  https://.../01-ROJO-NEGRO2.jpg
  https://.../02_VERDE GRIS.jpeg

Del nombre de archivo se extrae:
  <PREFIX> -> números iniciales del nombre (p.ej. "01")
  <COLOR> -> lo que sigue después del primer separador (- _ o espacio)

Uso:
  python build_terris_json.py input.txt output.json \
      --brand TERRIS \
      --name-template "Chaqueta Técnica TERRIS - Modelo {prefix}"

Argumentos opcionales útiles:
  --attribute-name Nombre del atributo (por defecto: color)
  --min-images-per-variation Valida un mínimo de imágenes por variación
  --ignore-case Normaliza mayúsculas/minúsculas (por defecto ON)

Salida JSON (por grupo):
[
  {
    "group_sku": "TERRIS-01",
    "type": "variable",
    "sku": "TERRIS-01",
    "nombre": "Chaqueta Técnica TERRIS - Modelo 01",
    "atributo": "color",
    "valores_del_atributo": ["AZUL-BLANCO", "ROJO-NEGRO"],
    "imagenes_variable": ["..."],
    "variations": [
      {
        "type": "variation",
        "sku": "TERRIS-01-AZUL-BLANCO",
        "nombre": "Chaqueta Técnica TERRIS - Modelo 01 AZUL BLANCO",
        "valor_del_atributo": "AZUL-BLANCO",
        "imagenes": ["..."]
      }
    ]
  }
]
"""

from __future__ import annotations
import argparse
import json
import os
import re
from collections import defaultdict
from urllib.parse import unquote
from typing import Dict, List, Tuple

# ----------------------- utilidades -----------------------
def natural_key(s: str):
    """Clave de ordenamiento natural: 'img2' < 'img10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.findall(r"\d+|\D+", s)]

NORMALIZE_SPACE_UNDERSCORE = re.compile(r"[\s_]+")
TRAILING_SEQ = re.compile(r"([\- _]?(?:\(\d+\)|\d+))+$", re.IGNORECASE)  # quita (1), -2, _3
SCALED_TAG = re.compile(r"[\- _]?scaled$", re.IGNORECASE)
EXT_PATTERN = re.compile(r"\.(?:jpg|jpeg|png|webp|gif|bmp|tiff)$", re.IGNORECASE)

PREFIX_COLOR_RE = re.compile(
    r"^(?P<prefix>[0-9]+(?:[ABab])?)[- _]+(?P<color>.+?)$"
)

def clean_stem(stem: str) -> str:
    """Limpia el stem (sin extensión): decodifica, quita 'scaled', '(1)', '-2', etc."""
    s = unquote(stem)
    s = s.strip()
    # quitar extensión residual si quedara
    s = EXT_PATTERN.sub("", s)
    # quitar sufijos de secuencia (1), -2, _3... pero OJO: conservamos para orden, no para color
    s_no_seq = TRAILING_SEQ.sub("", s)
    # quitar sufijo 'scaled'
    s_no_seq = SCALED_TAG.sub("", s_no_seq)
    return s_no_seq.strip(" -_")

def extract_prefix_color(stem: str) -> Tuple[str | None, str | None]:
    """Devuelve (prefix, color_raw) o (None, None) si no calza."""
    m = PREFIX_COLOR_RE.match(stem)
    if not m:
        return None, None
    prefix = m.group("prefix")
    color_raw = m.group("color").strip()
    return prefix, color_raw

def normalize_color(color_raw: str, ignore_case: bool = True) -> str:
    """Normaliza el color a formato 'AZUL-BLANCO' (guiones)."""
    c = color_raw
    c = SCALED_TAG.sub("", c)
    c = TRAILING_SEQ.sub("", c)  # quita secuencias al final
    c = c.strip(" -_")
    c = NORMALIZE_SPACE_UNDERSCORE.sub("-", c)
    c = re.sub(r"-+", "-", c)
    if ignore_case:
        c = c.upper()
    return c

def collect_groups(urls: List[str], ignore_case: bool = True):
    """Agrupa por prefix y color, devolviendo estructura interna."""
    groups: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    all_by_prefix: Dict[str, List[str]] = defaultdict(list)

    for url in urls:
        url = url.strip()
        if not url:
            continue
        # obtener filename y stem
        filename = os.path.basename(url)
        filename = unquote(filename)
        stem = EXT_PATTERN.sub("", filename)
        stem_clean = clean_stem(stem)

        prefix, color_raw = extract_prefix_color(stem_clean)
        if not prefix or not color_raw:
            # si no calza, intentamos con stem original sin limpiar secuencia
            prefix2, color_raw2 = extract_prefix_color(stem)
            if not prefix2 or not color_raw2:
                # saltar (o se podría loggear)
                continue
            prefix, color_raw = prefix2, color_raw2

        color = normalize_color(color_raw, ignore_case=ignore_case)
        groups[prefix][color].append(url)
        all_by_prefix[prefix].append(url)

    # ordenar las URLs por orden natural
    for p in groups:
        for c in groups[p]:
            groups[p][c] = sorted(groups[p][c], key=natural_key)
        all_by_prefix[p] = sorted(all_by_prefix[p], key=natural_key)

    return groups, all_by_prefix

def build_json(groups, all_by_prefix, brand: str, name_template: str, attribute_name: str = "color") -> List[dict]:
    """Construye la salida JSON por grupo.

    ACTUALIZADO:
    - El producto **variable** ahora usa SKU y group_sku con **<PREFIX>-<COLOR REPRESENTATIVO>**.
    - El **nombre** del variable incluye el **color representativo**.
    - imagenes_variable contiene **solo** las imágenes que coinciden con ese **prefix+color**.
    - valores_del_atributo sigue listando **todos los colores** detectados para el prefix.

    Regla del color representativo: se elige el **primer color** en orden natural.
    """
    payload = []

    for prefix in sorted(groups.keys(), key=natural_key):
        colors = sorted(groups[prefix].keys(), key=natural_key)
        # Elegimos un color representativo estable (primero por orden natural)
        rep_color = colors[0] if colors else None
        # Valores del atributo: excluir el color representativo para que aparezcan solo las variaciones
        valores_attr = [c for c in colors if c != rep_color] if rep_color else colors

        group_sku_value = f"{brand}-{prefix}-{rep_color}" if rep_color else f"{brand}-{prefix}"
        var_nombre = (
            f"{name_template.format(prefix=prefix)} {rep_color.replace('-', ' ')}"
            if rep_color else name_template.format(prefix=prefix)
        )
        imagenes_variable = (
            groups[prefix][rep_color]
            if rep_color else all_by_prefix.get(prefix, [])
        )

        # Determinar si es producto simple (solo un color) o variable
        is_simple = len(colors) <= 1
        group_type = "simple" if is_simple else "variable"

        group_obj = {
            "group_sku": group_sku_value,
            "type": group_type,
            "sku": group_sku_value,
            "nombre": var_nombre,
            "atributos": "" if is_simple else attribute_name,
            "valor(es) del atributo 1": "" if is_simple else valores_attr,
            "imagenes_variable": imagenes_variable,
            "variations": []
        }

        for color in colors:
            var_sku = f"{brand}-{prefix}-{color}"
            # Evitar duplicar el SKU del padre dentro de sus propias variaciones
            if var_sku == group_sku_value:
                continue
            variation_obj = {
                "type": "variation",
                "sku": var_sku,
                "nombre": f"{name_template.format(prefix=prefix)} {color.replace('-', ' ')}",
                "valor(es) del atributo": color,
                "imagenes": groups[prefix][color]
            }
            group_obj["variations"].append(variation_obj)

        payload.append(group_obj)

    return payload

def main():
    ap = argparse.ArgumentParser(description="Genera JSON estructurado (VARIABLE + VARIATIONS) desde un TXT de URLs")
    ap.add_argument("input_txt", help="Ruta del TXT con URLs (una por línea)")
    ap.add_argument("output_json", help="Ruta del JSON de salida")
    ap.add_argument("--brand", default="TERRIS", help="Prefijo de marca para el SKU (por defecto TERRIS)")
    ap.add_argument(
        "--name-template",
        default="Chaqueta Técnica TERRIS - Modelo {prefix}",
        help="Plantilla de nombre para el producto variable y base de variaciones. Use {prefix}"
    )
    ap.add_argument("--attribute-name", default="color", help="Nombre del atributo (por defecto 'color')")
    ap.add_argument("--ignore-case", action="store_true", default=True, help="Normaliza colores en MAYÚSCULAS")
    ap.add_argument("--no-ignore-case", dest="ignore_case", action="store_false", help="Mantiene el caso original de colores")
    ap.add_argument("--min-images-per-variation", type=int, default=0, help="Valida que cada variación tenga al menos N imágenes (0 = sin validación)")

    args = ap.parse_args()

    # lee URLs
    with open(args.input_txt, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    groups, all_by_prefix = collect_groups(urls, ignore_case=args.ignore_case)

    payload = build_json(
        groups,
        all_by_prefix,
        brand=args.brand,
        name_template=args.name_template,
        attribute_name=args.attribute_name,
    )

    # validación opcional
    if args.min_images_per_variation > 0:
        problemas = []
        for g in payload:
            for v in g["variations"]:
                if len(v["imagenes"]) < args.min_images_per_variation:
                    problemas.append((g["sku"], v["sku"], len(v["imagenes"])))
        if problemas:
            # no abortamos; solo informamos por stderr
            import sys
            print("ADVERTENCIA: Variaciones con menos imágenes que el mínimo:", file=sys.stderr)
            for sku_parent, sku_var, count in problemas:
                print(f"  {sku_parent} -> {sku_var}: {count} imágenes", file=sys.stderr)

    # escribe JSON bonito
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"OK -> {args.output_json} ({len(payload)} grupos)")

if __name__ == "__main__":
    main()
