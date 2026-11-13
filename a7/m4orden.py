#!/usr/bin/env python3
"""Envía una orden al M4 por /dev/ttyRPMSG0 e imprime la respuesta (OK/ERR).
   ./m4orden.py "adc prueba" [espera_s]      (el visor no debe tener el tty abierto)
Copyright (c) 2026 rommeljose y colaboradores. MIT."""
import os, sys, termios, time, select
orden = sys.argv[1]; espera = float(sys.argv[2]) if len(sys.argv) > 2 else 3
fd = os.open("/dev/ttyRPMSG0", os.O_RDWR | os.O_NOCTTY)
a = termios.tcgetattr(fd); a[3] &= ~(termios.ECHO | termios.ICANON); termios.tcsetattr(fd, termios.TCSANOW, a)
os.write(fd, orden.encode())
buf = b""; t = time.time() + espera
while time.time() < t:
    if select.select([fd], [], [], 0.1)[0]:
        buf += os.read(fd, 4096)
        if b"\n" in buf:
            linea = [l for l in buf.replace(b"\r", b"\n").split(b"\n") if l.startswith((b"OK", b"ERR", b"H ", b"S "))]
            if linea: print(linea[0].decode(errors="replace")); break
else:
    print("sin respuesta:", buf[-300:])
os.close(fd)
