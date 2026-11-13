#!/usr/bin/env python3
"""
Prueba del ADS1220 (módulo CJMCU-1220) desde Linux, por /dev/spidev2.0 (ECSPI3).
Etapa 2, paso 3 del proyecto «M4 instrumento». Sin dependencias: ioctl a mano.

No necesita nada en AIN0..AIN3: usa los modos internos del ADS1220.
  1. RESET y escritura/lectura de los 4 registros (prueba el cableado SPI).
  2. Entradas en cortocircuito  (MUX 1110)   -> debe dar ~0 V.
  3. (AVDD − AVSS) / 4          (MUX 1101)   -> ×4 = la alimentación, ~3,3 V.
  4. Sensor de temperatura      (TS = 1)     -> temperatura del cuarto.

Requiere que spi_imx esté LIGADO (que exista /dev/spidev2.0) y root.
Cableado: docs/SPI_M4_ECSPI3.md y la bitácora. ¡Alimentación a 3,3 V!

Copyright (c) 2026 rommeljose y colaboradores. MIT.
"""
import fcntl
import os
import struct
import sys
import time

DEV = "/dev/spidev2.0"
VELOCIDAD = 1_000_000          # Hz; el ADS1220 admite bastante más
VREF = 2.048                   # referencia interna

SPI_IOC_WR_MODE = 0x40016B01           # _IOW('k', 1, u8)
SPI_IOC_WR_MAX_SPEED_HZ = 0x40046B04   # _IOW('k', 4, u32)
SPI_IOC_MESSAGE_1 = 0x40206B00         # _IOW('k', 0, struct spi_ioc_transfer[1]), 32 B

# Órdenes del ADS1220 (hoja de datos SBAS501)
RESET, START, RDATA = 0x06, 0x08, 0x10
RREG = lambda r, n: 0x20 | (r << 2) | (n - 1)
WREG = lambda r, n: 0x40 | (r << 2) | (n - 1)


class Spi:
    def __init__(self, ruta=DEV):
        self.fd = os.open(ruta, os.O_RDWR)
        fcntl.ioctl(self.fd, SPI_IOC_WR_MODE, struct.pack("B", 1))      # modo SPI 1
        fcntl.ioctl(self.fd, SPI_IOC_WR_MAX_SPEED_HZ, struct.pack("I", VELOCIDAD))

    def xfer(self, datos):
        """Transferencia full-duplex con CS bajo durante todo el bloque."""
        tx = bytearray(datos)
        rx = bytearray(len(tx))
        tb = (ctypes_addr(tx), ctypes_addr(rx))
        # struct spi_ioc_transfer: tx_buf, rx_buf (u64), len, speed_hz (u32),
        # delay_usecs (u16), bits_per_word, cs_change, tx_nbits, rx_nbits,
        # word_delay_usecs, pad (u8)
        t = struct.pack("QQIIHBBBBBB", tb[0], tb[1], len(tx), VELOCIDAD, 0, 8, 0, 0, 0, 0, 0)
        fcntl.ioctl(self.fd, SPI_IOC_MESSAGE_1, t)
        return bytes(rx)

    def cierra(self):
        os.close(self.fd)


def ctypes_addr(buf):
    import ctypes
    return ctypes.addressof((ctypes.c_char * len(buf)).from_buffer(buf))


def lee_regs(s):
    return list(s.xfer([RREG(0, 4), 0, 0, 0, 0])[1:])


def escribe_regs(s, r):
    s.xfer([WREG(0, 4)] + list(r))


def convierte(s, r0, r1=0x00):
    """Una conversión single-shot a 20 SPS. Devuelve el código de 24 bits con signo."""
    escribe_regs(s, [r0, r1, 0x00, 0x00])
    s.xfer([START])
    time.sleep(0.080)                   # 20 SPS: ~51 ms por conversión, con margen
    d = s.xfer([RDATA, 0, 0, 0])[1:]
    v = (d[0] << 16) | (d[1] << 8) | d[2]
    return v - (1 << 24) if v & 0x800000 else v


def main():
    if not os.path.exists(DEV):
        sys.exit(f"No existe {DEV}: ¿está desligado spi_imx? "
                 "echo 30840000.spi | sudo tee /sys/bus/platform/drivers/spi_imx/bind")
    s = Spi()
    try:
        s.xfer([RESET])
        time.sleep(0.001)
        print("tras RESET     regs =", " ".join(f"{b:02X}" for b in lee_regs(s)),
              "  (esperado 00 00 00 00)")

        patron = [0x3E, 0x94, 0x50, 0x00]   # valores distintos de cero, reg3 bit0 reservado
        escribe_regs(s, patron)
        leido = lee_regs(s)
        ok = leido == patron
        print("escrito        regs =", " ".join(f"{b:02X}" for b in patron))
        print("leído          regs =", " ".join(f"{b:02X}" for b in leido),
              "  ->", "OK: el SPI funciona" if ok else "FALLO: revisa cableado/alimentación")
        if not ok:
            if all(b == 0xFF for b in leido):
                print("   todo FF: MISO al aire o el ADC sin alimentar")
            elif all(b == 0x00 for b in leido):
                print("   todo 00: MISO a tierra, CS o MOSI sin conectar, o modo SPI equivocado")
            return 1

        lsb = VREF / (1 << 23)
        c = convierte(s, (0b1110 << 4) | 1)          # entradas en corto, PGA en bypass
        print(f"corto          código={c:9d}  {c * lsb * 1e6:9.1f} µV   (esperado ~0)")
        c = convierte(s, (0b1101 << 4) | 1)          # (AVDD-AVSS)/4
        print(f"(AVDD-AVSS)/4  código={c:9d}  {c * lsb:9.4f} V  -> AVDD = {4 * c * lsb:.3f} V"
              "   (esperado ~3,3)")
        c = convierte(s, 0x00, 0x02)                 # TS=1: sensor de temperatura
        t = c >> 10                                  # 14 bits, justificados a la izquierda
        print(f"temperatura    código={c:9d}  {t * 0.03125:6.2f} °C")
        s.xfer([RESET])                              # lo dejamos como al encender
        return 0
    finally:
        s.cierra()


if __name__ == "__main__":
    sys.exit(main())
