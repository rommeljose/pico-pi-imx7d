#!/usr/bin/env python3
"""
Captura muestras REALES del ADS1220 a través del M4 (firmware v0.5, etapa 2 paso 4b)
y da su estadística: ruido en cuentas y en µV, tasa real, pérdidas.

  sudo python3 adc_captura.py [-s SEG] [--deja] [corto|ain01|avdd|temp] [PGA] [SPS]
  ej.:  sudo python3 adc_captura.py -s 20 corto 128 90

Requisito: spi_imx DESLIGADO (si existe /dev/spidev2.0, se niega a seguir):
  echo 30840000.spi | sudo tee /sys/bus/platform/drivers/spi_imx/unbind
Al terminar vuelve a la fuente sintética (salvo --deja); el bus lo vuelve a ligar
quien lo desligó. Usa el canal binario /dev/rpmsgN como el visor.

Copyright (c) 2026 rommeljose y colaboradores. MIT.
"""
import argparse, math, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from visor_instrumento import Canal, CanalBin, LATIDO_S

VREF = 2.048

ap = argparse.ArgumentParser()
ap.add_argument("-s", "--segundos", type=float, default=20)
ap.add_argument("--deja", action="store_true", help="no volver a la fuente sintética")
ap.add_argument("--guarda", help="fichero de texto: una muestra (cuentas) por línea")
ap.add_argument("entrada", nargs="?", default="corto")
ap.add_argument("pga", nargs="?", type=int, default=128)
ap.add_argument("sps", nargs="?", type=int, default=90)
a = ap.parse_args()
if os.path.exists("/dev/spidev2.0"):
    sys.exit("spi_imx está ligado (/dev/spidev2.0 existe): desligarlo antes")
pga = 1 if a.entrada in ("avdd", "temp") else a.pga

c = Canal(); b = CanalBin()
resp = []
def textos(lst):
    for t in lst:
        if t and not isinstance(t, bytes):
            resp.append(t)

orden = f"fuente adc {a.entrada} {a.pga} {a.sps}"
c.envia(orden); c.envia("inicia")
v, seqs, saltos_seq, flags_ev = [], [], 0, 0
t0 = time.time(); prox = t0; primero = None
while time.time() - t0 < a.segundos + 1.5:
    if time.time() >= prox:
        b.latido(); prox += LATIDO_S
    textos(c.lee_lineas())
    for m in b.lee():
        if isinstance(m, bytes):
            n, fl, fs, seq, ini = struct.unpack_from("<xBBxHHI", m)
            if time.time() - t0 < 1.5:          # descarta el arranque del ADC
                continue
            if seqs and seq != (seqs[-1] + 1) & 0xFFFF:
                saltos_seq += 1
            seqs.append(seq)
            if primero is None: primero = (ini, time.time())
            ultimo = (ini + n, time.time())
            flags_ev += fl & 1
            v += struct.unpack_from(f"<{n}i", m, 12)
        else:
            textos([m])
    time.sleep(0.01)
c.envia("estado"); time.sleep(0.3); textos(c.lee_lineas()); textos(b.lee())
if not a.deja:
    c.envia("fuente sint"); time.sleep(0.2); textos(c.lee_lineas())
b.cierra(); c.cierra()

ss = [t for t in resp if t.startswith("S ")]
for t in resp:
    if t.split()[0] in ("OK", "ERR"):
        print("<<", t[:120])
if ss:
    d = dict(kv.split("=", 1) for kv in ss[-1].split()[1:] if "=" in kv)
    print("<< M4:", " ".join(f"{k}={d.get(k)}" for k in
          ("fuente", "fs", "fs_real_mhz", "filtro", "notch_mhz", "filtro_hw",
           "adc_saltos", "adc_err", "perdidos", "carga_ppm", "peor_us")))
if not v:
    sys.exit("sin muestras")
if a.guarda:
    with open(a.guarda, "w") as f:
        f.write(f"# {orden}  sps={a.sps} pga={pga} lsb_V={VREF / pga / (1 << 23):.6e}\n")
        f.writelines(f"{x}\n" for x in v)
N = len(v); m = sum(v) / N
sd = math.sqrt(sum((x - m) ** 2 for x in v) / N)
lsb = VREF / pga / (1 << 23)
print(f"\nentrada={a.entrada} pga={pga} sps={a.sps}: {N} muestras, saltos de seq={saltos_seq}, bloques con evento={flags_ev}")
print(f"tasa medida ≈ {(ultimo[0]-primero[0])/(ultimo[1]-primero[1]):.2f} muestras/s (reloj del A7, "
      "aproximada; la buena es fs_real_mhz del M4)")
if a.entrada == "temp":
    print(f"temperatura media {(m / 1024) * 0.03125:.3f} °C   (desv. {sd/1024*0.03125*1000:.1f} m°C)")
elif a.entrada == "avdd":
    print(f"AVDD medio {4*m*lsb:.5f} V   (desv. {4*sd*lsb*1e6:.1f} µV)")
else:
    print(f"media {m:.1f} cuentas = {m*lsb*1e6:.3f} µV")
    print(f"ruido {sd:.2f} cuentas rms = {sd*lsb*1e6:.3f} µV rms   p-p {(max(v)-min(v))*lsb*1e6:.3f} µV")
    print(f"bits sin ruido (p-p) ≈ {math.log2((1<<24)/max(1,max(v)-min(v))):.1f}")
