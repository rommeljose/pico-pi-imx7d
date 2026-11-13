#!/usr/bin/env python3
"""ADS1220 en conversión continua sin leer (DRDY casi siempre bajo), para medir
con multímetro: sudo python3 ads1220_continuo.py <segundos>. Etapa 2, paso 4."""
import time, sys
sys.path.insert(0, "/home/ubuntu")
from ads1220_prueba import Spi, RESET, START, WREG
s = Spi()
s.xfer([RESET]); time.sleep(0.01)
s.xfer([WREG(0, 4), 0xE1, 0x04, 0x00, 0x00])   # corto, continuo 20 SPS, sin leer: DRDY casi siempre bajo
s.xfer([START])
time.sleep(int(sys.argv[1]))
s.xfer([RESET]); s.cierra()
