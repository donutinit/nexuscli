"""Registro local de lo ya visto, para que `novedades` muestre solo lo nuevo.

SQLite en ~/.local/state/nexuscli/visto.db. Cada cosa observable tiene una clave estable
(p. ej. `retro:39544023`) y una huella de su contenido; si la huella cambia, es novedad.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from . import config, texto


def huella(*partes: Any) -> str:
    raw = json.dumps(partes, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class Visto:
    def __init__(self, path: Path) -> None:
        config.ensure_private_dir(path.parent)
        if not path.exists():
            path.touch(mode=0o600)
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS visto (clave TEXT PRIMARY KEY, huella TEXT NOT NULL, visto_en TEXT NOT NULL)"
        )
        nueva = self.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'materias'").fetchone() is None
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS materias (curso_id INTEGER PRIMARY KEY, nombre TEXT, visto_en TEXT NOT NULL)"
        )
        if nueva:
            # Bases anteriores a la tabla: las materias con tareas registradas ya se conocían.
            ts = texto.ahora().isoformat(timespec="seconds")
            for (clave,) in self.db.execute("SELECT clave FROM visto WHERE clave LIKE 'tarea:%'").fetchall():
                partes = clave.split(":")
                if len(partes) > 1 and partes[1].isdigit():
                    self.db.execute("INSERT OR IGNORE INTO materias VALUES (?, NULL, ?)", (int(partes[1]), ts))
        self.db.commit()

    def vacio(self) -> bool:
        return self.db.execute("SELECT 1 FROM visto LIMIT 1").fetchone() is None

    def hay_prefijo(self, prefijo: str) -> bool:
        return self.db.execute("SELECT 1 FROM visto WHERE clave LIKE ? LIMIT 1", (prefijo + "%",)).fetchone() is not None

    def estado(self, clave: str, h: str) -> str | None:
        """None si ya se vio igual; 'nuevo' o 'cambio' si no."""
        row = self.db.execute("SELECT huella FROM visto WHERE clave = ?", (clave,)).fetchone()
        if row is None:
            return "nuevo"
        return None if row[0] == h else "cambio"

    def marcar(self, items: list[tuple[str, str]]) -> None:
        ts = texto.ahora().isoformat(timespec="seconds")
        self.db.executemany(
            "INSERT INTO visto (clave, huella, visto_en) VALUES (?, ?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET huella = excluded.huella, visto_en = excluded.visto_en",
            [(k, h, ts) for k, h in items],
        )
        self.db.commit()

    def materia_conocida(self, curso_id: int) -> bool:
        return self.db.execute("SELECT 1 FROM materias WHERE curso_id = ?", (curso_id,)).fetchone() is not None

    def conocer(self, materias: list[tuple[int, str]]) -> None:
        ts = texto.ahora().isoformat(timespec="seconds")
        self.db.executemany(
            "INSERT INTO materias (curso_id, nombre, visto_en) VALUES (?, ?, ?) "
            "ON CONFLICT(curso_id) DO UPDATE SET nombre = excluded.nombre",
            [(cid, nombre, ts) for cid, nombre in materias],
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()
