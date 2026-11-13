#!/usr/bin/env python3
"""
¿Llega el DRDY del ADS1220 a un GPIO de J8?  sudo ./ads1220_drdy.py [gpio]  (por defecto 43 = J8-11) Etapa 2, paso 4 del «M4 instrumento».
Desde Linux, por /dev/spidev2.0. Requiere root y spi_imx ligado.

  1. RESET: sin conversión en curso, DRDY debe estar ALTO.
  2. START en modo continuo a 20 SPS: DRDY baja cada ~50 ms con un dato nuevo.
  3. Leer cada dato (RDATA) cuando DRDY baja: DRDY sube al leer y vuelve a bajar
     con la conversión siguiente -> unos 20 flancos por segundo.

La línea solo se LEE: no se escribe nunca su 'direction' (quedó 'in').

Copyright (c) 2026 rommeljose y colaboradores. MIT.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ads1220_prueba import Spi, RESET, START, RDATA, WREG

N = sys.argv[1] if len(sys.argv) > 1 else "43"
G = "/sys/class/gpio/gpio" + N


def nivel():
    with open(G + "/value") as f:
        return f.read(1)


def main():
    exportada = os.path.exists(G)
    if not exportada:
        with open("/sys/class/gpio/export", "w") as f:
            f.write(N)
        time.sleep(0.1)
    s = Spi()
    try:
        print(f"dirección de gpio{N}:", open(G + "/direction").read().strip(), " (debe ser in)")
        s.xfer([RESET]); time.sleep(0.01)
        print("tras RESET, DRDY =", "".join(nivel() for _ in range(20)), " (esperado todo 1)")

        s.xfer([WREG(0, 4), (0b1110 << 4) | 1, 0x04, 0x00, 0x00])   # corto, PGA bypass, 20 SPS continuo
        s.xfer([START])
        t0 = time.monotonic(); muestras = []; cambios = 0; ant = nivel()
        while time.monotonic() - t0 < 1.0:
            v = nivel()
            if v != ant:
                cambios += 1; ant = v
            if v == "0":                                          # dato listo: leerlo
                d = s.xfer([RDATA, 0, 0, 0])[1:]
                c = (d[0] << 16) | (d[1] << 8) | d[2]
                muestras.append(c - (1 << 24) if c & 0x800000 else c)
            time.sleep(0.002)
        print(f"en 1 s: {len(muestras)} datos leídos al bajar DRDY, {cambios} cambios de nivel"
              "  (esperado ~20 y ~40)")
        if muestras:
            print("códigos (entradas en corto, ~0):", muestras[:10])
        s.xfer([RESET])
        return 0 if 15 <= len(muestras) <= 25 else 1
    finally:
        s.cierra()
        if not exportada:
            with open("/sys/class/gpio/unexport", "w") as f:
                f.write(N)


if __name__ == "__main__":
    sys.exit(main())
