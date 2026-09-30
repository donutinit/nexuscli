"""Pausas aleatorias entre llamadas, con entropía del sistema operativo.

Cada espera sale de `secrets.SystemRandom` (os.urandom), no del Mersenne Twister de
`random`: no hay semilla que reproducir ni patrón periódico. La forma también importa:

- base log-normal: casi siempre un rato corto, a veces uno largo (como alguien leyendo);
- de vez en cuando una pausa larga extra ("se distrajo");
- micro-jitter para que dos esperas nunca midan lo mismo;
- el tiempo que ya pasó desde la llamada anterior se descuenta, porque el ritmo que ve
  el servidor es entre peticiones, no entre sleeps.

Perfiles: off (tests y scripts), rapido, normal (default) y lento. Se elige con
`--pace` o `NEXUS_PACE`.
"""

from __future__ import annotations

import math
import secrets
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Perfil:
    mediana: float        # segundos, centro de la log-normal
    sigma: float          # dispersión de la log-normal
    p_larga: float        # probabilidad de una pausa larga extra
    larga: tuple[float, float]
    tope: float           # ninguna espera pasa de aquí
    teclear: tuple[float, float]  # lo que "tarda" en escribir usuario y contraseña


PERFILES: dict[str, Perfil | None] = {
    "off": None,
    "rapido": Perfil(0.45, 0.45, 0.03, (1.2, 3.0), 4.0, (0.8, 1.8)),
    "normal": Perfil(1.1, 0.55, 0.08, (2.5, 7.0), 12.0, (2.0, 5.5)),
    "lento": Perfil(2.4, 0.60, 0.15, (5.0, 15.0), 25.0, (4.0, 9.0)),
}

_rng = secrets.SystemRandom()


class Pacer:
    def __init__(
        self,
        perfil: str = "normal",
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if perfil not in PERFILES:
            raise ValueError(f"perfil de pausas desconocido: {perfil!r} (usa {', '.join(PERFILES)})")
        self.nombre = perfil
        self.perfil = PERFILES[perfil]
        self._sleep = sleep
        self._clock = clock
        self._ultima: float | None = None
        self.total = 0.0

    def muestra(self, peso: float = 1.0) -> float:
        """Una duración aleatoria según el perfil, sin dormir."""
        p = self.perfil
        if p is None:
            return 0.0
        d = _rng.lognormvariate(math.log(p.mediana), p.sigma)
        if _rng.random() < p.p_larga:
            d += _rng.uniform(*p.larga)
        d = d * peso + _rng.random() * 0.25
        return min(d, p.tope * max(peso, 1.0))

    def antes(self, peso: float = 1.0) -> float:
        """Espera antes de una petición. Devuelve lo que durmió."""
        if self.perfil is None:
            return 0.0
        if self._ultima is None:
            # Primera petición del proceso: solo un respiro corto.
            d = _rng.uniform(0.05, 0.6)
        else:
            d = self.muestra(peso) - (self._clock() - self._ultima)
        if d > 0:
            self._sleep(d)
            self.total += d
        return max(d, 0.0)

    def despues(self) -> None:
        self._ultima = self._clock()

    def teclear(self) -> None:
        """Pausa de "escribir credenciales" entre abrir el login y mandarlo."""
        if self.perfil is None:
            return
        d = _rng.uniform(*self.perfil.teclear)
        self._sleep(d)
        self.total += d
