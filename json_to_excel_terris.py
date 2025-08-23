#!/usr/bin/env python3
"""
Uso:
    python json_to_excel_terris.py output.json salida.xlsx
    # o CSV
    python json_to_excel_terris.py output.json salida.csv

Opciones:
    --attr-name-in-variations    Si se indica, también rellena "atributos" en variaciones.
    --sheet-name NOMBRE          Nombre de la hoja Excel (por defecto: "Productos").
    --sep ","                   Separador para CSV (por defecto: ",").

Requisitos: pandas, openpyxl (para .xlsx)
"""
from __future__ import annotations
import argparse
import json
import os
from typing import List, Dict, Any

import pandas as pd

COLUMNS = [
    "Tipo",
    "SKU",
    "Nombre",
    "atributos",
    "Valor(es) del atributo 1",
    "Imágenes",
]

# -------------------- Utilidades --------------------

def _lower_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    """Devuelve un dict con las claves en minúscula para búsquedas insensibles a mayúsculas."""
    return {str(k).lower(): v for k, v in d.items()}


def pick_ci(d: Dict[str, Any], candidates: List[str], default: Any = "") -> Any:
    """Obtiene el primer valor cuya clave coincida (case-insensitive) con alguna de 'candidates'."""
    if not isinstance(d, dict):
        return default
    dl = _lower_keys(d)
    for k in candidates:
        v = dl.get(k.lower())
        if v is not None:
            return v
    return default


def listify(x: Any) -> List[str]:
    """Convierte x en lista de strings. Si es None -> []. Si es str -> [str]. Si es lista -> limpia y castea a str."""
    if x is None:
        return []
    if isinstance(x, list):
        return [str(i).strip() for i in x if str(i).strip() != ""]
    return [str(x).strip()]

# -------------------- Transformación --------------------

def rows_from_payload(payload: List[Dict[str, Any]], attr_name_in_variations: bool = False) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    for group in payload:
        # Detectar 'type' o 'tipo' (case-insensitive) para reconocer productos 'simple'
        tipo_raw = pick_ci(group, ["type", "tipo"], default="")
        tipo = str(tipo_raw).lower()

        if tipo == "simple":
            # Producto SIMPLE -> aceptar imágenes desde 'imagenes' o 'imagenes_variable'
            imgs = listify(pick_ci(group, ["imagenes", "imagenes_variable", "imagenes variable"], default=[]))
            rows.append({
                "Tipo": "simple",
                "SKU": str(group.get("sku", "")),
                "Nombre": str(group.get("nombre", "")),
                "atributos": "",
                "Valor(es) del atributo 1": "",
                "Imágenes": ", ".join(imgs),
            })
            continue

        # Detectar nombre y valores del atributo en el grupo (case-insensitive, varias opciones)
        grp_attr_name = pick_ci(
            group,
            ["atributos", "atributo", "nombre_atributo"],
            default="",
        )
        grp_attr_values = pick_ci(
            group,
            [
                "Valor(es) del atributo 1",
                "valores_del_atributo",
                "valores del atributo",
                "valores",
            ],
            default=[],
        )
        grp_attr_values_list = listify(grp_attr_values)

        # Fila VARIABLE
        rows.append({
            "Tipo": "variable",
            "SKU": str(group.get("sku", "")),
            "Nombre": str(group.get("nombre", "")),
            "atributos": str(grp_attr_name),
            "Valor(es) del atributo 1": " , ".join(grp_attr_values_list),
            "Imágenes": ", ".join(listify(group.get("imagenes_variable"))),
        })

        # Filas VARIATIONS
        variations = group.get("variations", []) or []
        for var in variations:
            # Valor del atributo en la variación (acepta varias claves y minúsculas)
            var_attr_value = pick_ci(
                var,
                [
                    "Valor(es) del atributo 1",
                    "Valor(es) del atributo",
                    "valor_del_atributo",
                    "valor",
                ],
                default="",
            )

            rows.append({
                "Tipo": "variation",
                "SKU": str(var.get("sku", "")),
                "Nombre": str(var.get("nombre", "")),
                "atributos": str(grp_attr_name) if attr_name_in_variations else "",
                "Valor(es) del atributo 1": str(var_attr_value),
                "Imágenes": ", ".join(listify(var.get("imagenes"))),
            })

    return rows


# -------------------- Salida --------------------

def save_table(rows: List[Dict[str, str]], output_path: str, sheet_name: str = "Productos", sep: str = ",") -> None:
    df = pd.DataFrame(rows, columns=COLUMNS)
    # Asegurar tipos string para evitar cast no deseado en Excel
    for col in COLUMNS:
        df[col] = df[col].astype(str)

    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".xlsx":
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
    elif ext == ".csv":
        df.to_csv(output_path, index=False, sep=sep, encoding="utf-8-sig")
    else:
        raise ValueError("Extensión no soportada. Use .xlsx o .csv")


# -------------------- CLI --------------------

def main():
    ap = argparse.ArgumentParser(description="Convierte JSON organizado (VARIABLE + VARIATIONS + SIMPLE) a Excel/CSV con columnas específicas")
    ap.add_argument("output_json", help="Ruta del archivo JSON fuente")
    ap.add_argument("output_file", help="Ruta del archivo de salida (.xlsx o .csv)")
    ap.add_argument("--attr-name-in-variations", action="store_true", help="Rellenar también el nombre del atributo en variaciones")
    ap.add_argument("--sheet-name", default="Productos", help="Nombre de la hoja de Excel (por defecto 'Productos')")
    ap.add_argument("--sep", default=",", help="Separador CSV (por defecto ',')")

    args = ap.parse_args()

    with open(args.output_json, "r", encoding="utf-8") as f:
        payload = json.load(f)
        if not isinstance(payload, list):
            raise ValueError("El JSON debe ser una lista de grupos")

    rows = rows_from_payload(payload, attr_name_in_variations=args.attr_name_in_variations)
    save_table(rows, args.output_file, sheet_name=args.sheet_name, sep=args.sep)

    print(f"OK -> {args.output_file} ({len(rows)} filas)")

if __name__ == "__main__":
    main()
