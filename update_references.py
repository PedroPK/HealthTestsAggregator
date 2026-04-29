#!/usr/bin/env python3
"""
Interactive CLI para gerenciar os valores de referência dos exames.

Edita config/reference_ranges.yaml.

Uso:
    python update_references.py

AVISO: ao salvar, os comentários do arquivo YAML são removidos.
"""

import sys
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "config" / "reference_ranges.yaml"


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def _load() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(
            data, f,
            allow_unicode=True,
            sort_keys=True,
            default_flow_style=False,
            indent=2,
        )
    print(f"\n  ✓ Salvo em {CONFIG_PATH}")


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def _prompt(msg: str, default=None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    try:
        val = input(f"  {msg}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val if val else (str(default) if default is not None else "")


def _prompt_float(msg: str, default=None):
    while True:
        raw = _prompt(msg, default)
        if not raw:
            return None
        try:
            return float(raw.replace(",", "."))
        except ValueError:
            print("    ✗ Digite um número válido (ex: 3.5 ou 3,5).")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(data: dict) -> None:
    if not data:
        print("\n  Nenhum exame configurado ainda.")
        return
    print(f"\n  {'Nome Canônico':<48} {'Tipo':<12} {'Mín':>10} {'Máx':>10}  Unidade")
    print("  " + "─" * 92)
    for name in sorted(data):
        cfg = data[name]
        mn = str(cfg.get("min", "─"))
        mx = str(cfg.get("max", "─"))
        print(
            f"  {name:<48} {cfg.get('type', ''):<12} "
            f"{mn:>10} {mx:>10}  {cfg.get('unit', '')}"
        )
    print(f"\n  Total: {len(data)} exame(s) configurado(s).")


def cmd_add_or_edit(data: dict) -> None:
    canonical = _prompt("Nome canônico do exame (ex: GLICOSE)").upper()
    if not canonical:
        return

    existing = data.get(canonical, {})
    print(f"\n  {'Editando' if existing else 'Novo exame'}: {canonical}")

    unit = _prompt("Unidade (ex: mg/dL)", existing.get("unit", ""))
    print("  Tipos: range | max_only | min_only | qualitative")
    ref_type = _prompt("Tipo", existing.get("type", "range"))

    cfg: dict = {
        "unit": unit,
        "type": ref_type,
        "aliases": list(existing.get("aliases", [canonical])),
    }

    if ref_type in ("range", "min_only"):
        v = _prompt_float("Valor mínimo (Enter = sem mínimo)", existing.get("min"))
        if v is not None:
            cfg["min"] = v

    if ref_type in ("range", "max_only"):
        v = _prompt_float("Valor máximo (Enter = sem máximo)", existing.get("max"))
        if v is not None:
            cfg["max"] = v

    note = _prompt("Observação (ex: Masculino)", existing.get("note") or "")
    if note:
        cfg["note"] = note

    # Aliases
    print(f"\n  Aliases atuais: {cfg['aliases']}")
    while True:
        alias = _prompt("Adicionar alias? (Enter para pular)").upper()
        if not alias:
            break
        if alias not in cfg["aliases"]:
            cfg["aliases"].append(alias)
            print(f"    + adicionado: {alias}")

    # Zones
    if existing.get("zones"):
        keep = _prompt(
            f"\n  Manter {len(existing['zones'])} zona(s) existente(s)? [S/n]", "S"
        ).lower()
        if keep != "n":
            cfg["zones"] = list(existing["zones"])

    add_zones = _prompt("\n  Adicionar zonas coloridas? [s/N]", "N").lower()
    if add_zones == "s":
        zones = cfg.get("zones", [])
        print("  Adicione zonas (label vazio para terminar):")
        while True:
            label = input("    Label (ex: Normal): ").strip()
            if not label:
                break
            color = _prompt("    Cor hexadecimal", "#aaaaaa")
            z: dict = {"label": label, "color": color}
            mn = _prompt_float("    Min (Enter = aberto à esquerda)")
            mx = _prompt_float("    Max (Enter = aberto à direita)")
            if mn is not None:
                z["min"] = mn
            if mx is not None:
                z["max"] = mx
            zones.append(z)
        if zones:
            cfg["zones"] = zones

    data[canonical] = cfg
    _save(data)
    print(f"  ✓ '{canonical}' {'atualizado' if existing else 'adicionado'}.")


def cmd_delete(data: dict) -> None:
    canonical = _prompt("Nome canônico do exame a remover").upper()
    if not canonical:
        return
    if canonical not in data:
        print(f"\n  '{canonical}' não encontrado.")
        return
    confirm = _prompt(f"Confirma remoção de '{canonical}'? [s/N]", "N").lower()
    if confirm == "s":
        del data[canonical]
        _save(data)
        print(f"  ✓ '{canonical}' removido.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║  HealthTests — Valores de Referência         ║")
    print("  ╚══════════════════════════════════════════════╝")
    print(f"  Config: {CONFIG_PATH}")

    data = _load()

    while True:
        print()
        print("  1 — Listar exames configurados")
        print("  2 — Adicionar / editar exame")
        print("  3 — Remover exame")
        print("  0 — Sair")
        choice = _prompt("Opção")

        if choice == "1":
            cmd_list(data)
        elif choice == "2":
            cmd_add_or_edit(data)
        elif choice == "3":
            cmd_delete(data)
        elif choice == "0":
            break
        else:
            print("  Opção inválida.")


if __name__ == "__main__":
    main()
