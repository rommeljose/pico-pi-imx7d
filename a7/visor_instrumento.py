#!/usr/bin/env python3
"""
Visor del «M4 instrumento» (etapas 0 a 2): el lado Linux de RPMsg.

El M4 adquiere (ADS1220 o señal sintética, según «fuente»), procesa y detecta;
este programa solo muestra lo que el M4 manda
y le envía órdenes. Órdenes, respuestas y eventos van en texto por
/dev/ttyRPMSG0; las muestras, en binario por un endpoint propio (/dev/rpmsgN,
creado con /dev/rpmsg_ctrl0). Si no hay rpmsg_ctrl, todo va por el tty. Sin dependencias fuera de lo que trae el
Ubuntu de TechNexion (python3-gi, GTK 3, pycairo).

  visor_instrumento.py                   ventana a pantalla completa (800×480)
  visor_instrumento.py --ventana         ventana normal
  visor_instrumento.py --consola [-s N] [orden ...]
                                         sin gráficos: envía las órdenes, imprime
                                         lo que responde el M4 durante N s y un
                                         resumen. Para verificar por SSH.

Con VISOR_GUARDA=<fichero> en el entorno, añade cada muestra recibida por el
canal binario al fichero, una por línea: «t_unix índice valor».
En modo gráfico, la segunda fila elige la fuente del M4 (sintética o ADS1220,
entrada, ganancia, SPS) y «Aplicar» la pone en marcha. El visor cede el SPI al
M4 con /usr/local/sbin/spi-m4 (sudo sin contraseña solo para ese script) antes
de «fuente adc», y lo devuelve a Linux tras «fuente sint» y al cerrarse. La
última configuración se guarda en ~/.config/instrumento.conf y se aplica al
abrir. En --consola la fuente no se toca: es estado del M4 (m4orden.py).

Protocolo: ver docs/M4_Instrumento_Bitacora.md.
Copyright (c) 2026 rommeljose y colaboradores. MIT.
"""
import argparse
import array
import collections
import fcntl
import glob
import math
import json
import os
import signal
import struct
import subprocess
import sys
import termios
import time
import tty

TTY = "/dev/ttyRPMSG0"
CTRL = "/dev/rpmsg_ctrl0"
GUARDA = open(os.environ["VISOR_GUARDA"], "a", buffering=1) if os.environ.get("VISOR_GUARDA") else None
EPT_NOMBRE = "instrumento-bin"
RPMSG_CREATE_EPT_IOCTL = 0x4028b501     # _IOW(0xb5, 1, struct rpmsg_endpoint_info)
RPMSG_DESTROY_EPT_IOCTL = 0xb502        # _IO(0xb5, 2)
RPMSG_ADDR_ANY = 0xFFFFFFFF
BIN_BLOQUE = 0xB1                       # primer byte de un bloque binario
LATIDO_S = 0.5                          # el M4 deja el binario tras 2 s sin latido
GPIO_LED = "/sys/class/gpio/gpio38"     # USER LED = GPIO2_IO06; SOLO LECTURA
VENTANA_S = 30                          # segundos de traza en pantalla, al abrir
HIST_S = 300                            # segundos de historia para congelar y desplazar
PANEL_XFCE = 26     # px: el panel de XFCE se dibuja encima sin reservar su franja
SPI_M4 = "/usr/local/sbin/spi-m4"                   # cede/devuelve ECSPI3 (sudo)
SPI_LIGADO = "/sys/bus/platform/drivers/spi_imx/30840000.spi"
CONF = os.path.expanduser("~/.config/instrumento.conf")
CONF_DEF = {"fuente": "sint", "entrada": "ain01", "pga": 64, "sps": 90,
            "filtro": 0, "unidades": "cuentas", "ventana_s": VENTANA_S,
            "sens_v_ms": 20.9}  # V/(m/s): SM-6 (28,8) con el shunt de 1 kΩ
ENTRADAS = [("ain01", "geófono"), ("corto", "corto"),
            ("avdd", "AVDD/4"), ("temp", "temperatura")]
FILTROS = [(0, "sin filtro"), (60, "red 60 Hz"), (50, "red 50 Hz")]
UNIDADES = [("cuentas", "cuentas"), ("uv", "µV"), ("ums", "µm/s")]
VENTANAS = [1, 2, 5, 10, 20, 30, 60, 120, 300]   # s de traza en pantalla
VREF = 2.048                                      # V, referencia interna del ADS1220
PGAS = [1, 2, 4, 8, 16, 32, 64, 128]
SPSS = [20, 45, 90, 175, 330, 600]


def lee_conf():
    """(configuración, existía el fichero)"""
    try:
        with open(CONF) as f:
            d = json.load(f)
        return {k: d.get(k, v) for k, v in CONF_DEF.items()}, True
    except (OSError, ValueError):
        return dict(CONF_DEF), False


def guarda_conf(d):
    try:
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        with open(CONF, "w") as f:
            json.dump(d, f)
    except OSError:
        pass


def spi_m4(accion):
    """Cede o devuelve el ECSPI3. Devuelve None si fue bien, o el error."""
    try:
        r = subprocess.run(["sudo", "-n", SPI_M4, accion], capture_output=True,
                           text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e)
    return None if r.returncode == 0 else (r.stderr.strip() or f"código {r.returncode}")


# --------------------------------------------------------------------------
# Canal con el M4

class Canal:
    def __init__(self, ruta=TTY):
        self.fd = os.open(ruta, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        # Sin esto el tty devuelve como eco al M4 todo lo que el M4 envía
        tty.setraw(self.fd)
        a = termios.tcgetattr(self.fd)
        a[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON)
        termios.tcsetattr(self.fd, termios.TCSANOW, a)
        self.resto = b""

    def envia(self, orden):
        os.write(self.fd, (orden.strip() + "\n").encode())

    def lee_lineas(self):
        try:
            datos = os.read(self.fd, 65536)
        except BlockingIOError:
            return []
        self.resto += datos
        *lineas, self.resto = self.resto.split(b"\n")
        return [l.decode(errors="replace").strip() for l in lineas if l.strip()]

    def cierra(self):
        try:
            self.envia("pausa")         # que el M4 no siga llenando un tty cerrado
            time.sleep(0.1)
        finally:
            os.close(self.fd)


class CanalBin:
    """Endpoint propio para los bloques binarios. Un read() = un mensaje."""

    @staticmethod
    def busca():
        """/dev/rpmsgN ya creado con nuestro nombre, o None."""
        for d in sorted(glob.glob("/sys/class/rpmsg/rpmsg[0-9]*")):
            try:
                nombre = open(d + "/name").read().strip()
            except OSError:
                continue
            if nombre == EPT_NOMBRE and os.path.exists("/dev/" + os.path.basename(d)):
                return "/dev/" + os.path.basename(d)
        return None

    def __init__(self):
        # Si un visor anterior murió sin despedirse (kill -9), su /dev/rpmsgN
        # sigue ahí: el endpoint muere al cerrar el fd, el nodo no. Se reutiliza.
        self.ruta = self.busca()
        if not self.ruta:
            ctrl = os.open(CTRL, os.O_RDWR)
            try:
                fcntl.ioctl(ctrl, RPMSG_CREATE_EPT_IOCTL,
                            struct.pack("32sII", EPT_NOMBRE.encode(), RPMSG_ADDR_ANY, 0))
            finally:
                os.close(ctrl)
            for _ in range(50):         # udev tarda un poco en crear el nodo
                self.ruta = self.busca()
                if self.ruta:
                    break
                time.sleep(0.05)
        if not self.ruta:
            raise OSError("no apareció /dev/rpmsgN para " + EPT_NOMBRE)
        self.fd = None
        for _ in range(50):             # y en darle los permisos de la regla
            try:
                self.fd = os.open(self.ruta, os.O_RDWR | os.O_NONBLOCK)
                break
            except PermissionError:
                time.sleep(0.05)
        if self.fd is None:
            raise PermissionError(self.ruta)
        self.latido()

    def latido(self):
        os.write(self.fd, b"bin")       # alta en el binario, y «sigo vivo»
        return True

    def lee(self):
        """Lista de mensajes pendientes: bytes (bloque) o str (texto)."""
        r = []
        while True:
            try:
                m = os.read(self.fd, 512)
            except BlockingIOError:
                return r
            if not m:
                return r
            r.append(m if m[0] == BIN_BLOQUE else m.decode(errors="replace").strip())

    def cierra(self):
        try:
            os.write(self.fd, b"bin 0")     # baja: el M4 vuelve al tty
            time.sleep(0.1)
            fcntl.ioctl(self.fd, RPMSG_DESTROY_EPT_IOCTL)
        except OSError:
            pass
        finally:
            os.close(self.fd)


def abre_bin():
    try:
        return CanalBin(), None
    except OSError as e:
        return None, f"{type(e).__name__}: {e}"


def lee_led():
    try:
        with open(GPIO_LED + "/value") as f:
            return f.read().strip() == "1"
    except OSError:
        return None


def exporta_led():
    """Exporta el GPIO 38 para LEERLO. Nunca se escribe en 'direction'."""
    if os.path.exists(GPIO_LED):
        return True
    try:
        with open("/sys/class/gpio/export", "w") as f:
            f.write("38")
    except OSError:
        os.system("echo 38 | sudo -n tee /sys/class/gpio/export >/dev/null 2>&1")
    return os.path.exists(GPIO_LED)


# --------------------------------------------------------------------------
# Estado común (lo que sabemos del M4)

class Estado:
    def __init__(self):
        self.fs = 100
        # Muestras en posiciones consecutivas k: las pausas y las pérdidas se
        # «comprimen» (la traza anterior queda pegada a la nueva y la unión se
        # marca en pantalla). vals[j] es la muestra de la posición k0 + j.
        self.vals = array.array("i")
        self.k0 = 0
        self.ultima = -1            # índice del M4 de la última muestra recibida
        self.base = None            # índice del M4 de la posición 0
        self.saltos = []            # (última antes, muestras saltadas, por_pausa)
        self.plegado = 0            # muestras de saltos ya olvidados
        self.t_ultima = 0.0         # hora (Unix) de llegada de la última muestra
        self.tras_pausa = False     # el próximo salto se debe a una pausa
        self.huecos = 0             # muestras PERDIDAS (no cuenta las pausas)
        self.eventos = []           # [inicio, fin|None, ratio, pico]
        self.s = {}                 # última línea S
        self.hola = ""
        self.respuestas = collections.deque(maxlen=4)
        self.lineas = 0
        self.bloques = 0
        self.bloques_bin = 0
        self.seq = None             # último seq de bloque binario
        self.flags = 0              # del último bloque binario
        self.via = "texto"
        self.t_s = 0.0              # hora de la última línea S

    def bloque(self, ini, fs, vals, seq=None):
        if fs != self.fs:           # otra base de tiempo: se empieza de cero
            self.fs = fs
            del self.vals[:]
            self.k0 = 0
            self.saltos.clear()
            self.plegado = 0
            self.eventos.clear()
            self.base = None
            self.seq = None
        if self.base is None:
            self.base = ini
        elif ini > self.ultima + 1:
            g = ini - self.ultima - 1
            # Con seq no hay que adivinar: si los bloques son consecutivos,
            # el salto de índice es una pausa; si no, se perdieron bloques.
            pausa = self.tras_pausa if seq is None or self.seq is None \
                else ((seq - self.seq) & 0xFFFF) == 1
            self.saltos.append((self.ultima, g, pausa))
            if not pausa:
                self.huecos += g
        self.tras_pausa = False
        if seq is not None:
            self.seq = seq
        self.vals.extend(vals)
        self.ultima = ini + len(vals) - 1
        self.t_ultima = time.time()
        # Historia limitada: se recorta de golpe (con margen) para no mover el
        # array en cada bloque; los saltos olvidados pasan a «plegado».
        maxn = HIST_S * self.fs
        if len(self.vals) > maxn + 10 * self.fs:
            cut = len(self.vals) - maxn
            del self.vals[:cut]
            self.k0 += cut
            while self.saltos and self.pos(self.saltos[0][0]) < self.k0:
                self.plegado += self.saltos.pop(0)[1]
        self.bloques += 1

    def binario(self, m):
        n, flags, fs, seq, ini = struct.unpack_from("<xBBxHHI", m)
        if len(m) != 12 + 4 * n:
            self.respuestas.append(f"¿? bloque de {len(m)} B")
            return
        self.flags = flags
        self.via = "binario"
        self.bloques_bin += 1
        vals = array.array("i", m[12:]).tolist()
        if GUARDA:                          # VISOR_GUARDA=fichero: «t_unix índice valor»
            t = time.time()
            GUARDA.writelines(f"{t:.3f} {ini + i} {x}\n" for i, x in enumerate(vals))
        self.bloque(ini, fs, vals, seq)

    def procesa(self, linea):
        self.lineas += 1
        p = linea.split()
        if not p:
            return
        t = p[0]
        try:
            if t == "D":
                self.via = "texto"
                self.bloque(int(p[1]), int(p[2]), [int(v) for v in p[3:]])
            elif t == "E":
                self.eventos.append([int(p[1]), None, int(p[2]) / 100.0, 0])
            elif t == "F":
                fin, dur, pico = int(p[1]), int(p[2]), int(p[3])
                for e in reversed(self.eventos):
                    if e[1] is None:
                        e[1], e[3] = fin, pico
                        break
                else:
                    self.eventos.append([fin - dur, fin, 0.0, pico])
            elif t == "S":
                self.s = dict(kv.split("=", 1) for kv in p[1:] if "=" in kv)
                self.t_s = time.time()
            elif t == "H":
                self.hola = " ".join(p[1:])
            elif t in ("OK", "ERR"):
                self.respuestas.append(linea)
                # El M4 solo manda «S» mientras transmite: tras «pausa» no
                # llegaría ninguno que dijera tx=0. Se toma de la respuesta.
                if t == "OK" and len(p) > 1 and p[1] in ("pausa", "inicia"):
                    self.s["tx"] = "1" if p[1] == "inicia" else "0"
                    if p[1] == "pausa":
                        self.tras_pausa = True
        except (ValueError, IndexError):
            self.respuestas.append("¿? " + linea[:60])
        del self.eventos[:-50]

    def pos(self, i):
        """Posición k en la traza del índice i del M4, con los saltos comprimidos."""
        return i - (self.base or 0) - self.plegado - sum(g for r, g, _ in self.saltos if i > r)

    def ktot(self):
        """Posición que ocupará la próxima muestra."""
        return self.k0 + len(self.vals)


# --------------------------------------------------------------------------
# Modo consola

def consola(segundos, ordenes):
    c = Canal()
    cb, por_que = abre_bin()
    print(f"binario: {cb.ruta}" if cb else f"binario NO ({por_que}): todo por el tty")
    st = Estado()
    led_ok = exporta_led()
    t0 = time.time()
    prox_latido = t0 + LATIDO_S
    pendientes = ["hola", "inicia"] + list(ordenes) + ["estado"]
    prox_orden = t0
    cambios_led, led_ant = 0, lee_led()
    try:
        while time.time() - t0 < segundos:
            if pendientes and time.time() >= prox_orden:
                o = pendientes.pop(0)
                print(f"{time.time() - t0:7.2f}  >> {o}")
                c.envia(o)
                prox_orden = time.time() + 1.0
            for l in c.lee_lineas():
                st.procesa(l)
                if not l.startswith("D "):
                    print(f"{time.time() - t0:7.2f}  << {l}")
            if cb:
                for m in cb.lee():
                    if isinstance(m, bytes):
                        st.binario(m)
                    else:
                        st.procesa(m)
                        print(f"{time.time() - t0:7.2f}  <<bin {m}")
                if time.time() >= prox_latido:
                    cb.latido()
                    prox_latido += LATIDO_S
            led = lee_led()
            if led is not None and led != led_ant:
                cambios_led += 1
                print(f"{time.time() - t0:7.2f}  LED {'ENCENDIDO' if led else 'apagado'}"
                      "  (leído en /sys/class/gpio/gpio38/value)")
                led_ant = led
            time.sleep(0.02)
    finally:
        if cb:
            cb.cierra()
        c.cierra()
    dur = time.time() - t0
    print("\n--- resumen ---")
    print(f"duración {dur:.1f} s, líneas {st.lineas}, bloques {st.bloques} "
          f"(binarios {st.bloques_bin}), "
          f"muestras {len(st.vals)} en memoria, huecos {st.huecos}, "
          f"pausas {sum(1 for *_, pp in st.saltos if pp)}")
    if st.s:
        print("último estado:", " ".join(f"{k}={v}" for k, v in st.s.items()))
    print(f"eventos vistos {len(st.eventos)}, cambios del LED {cambios_led}"
          + ("" if led_ok else " (GPIO 38 no exportado: LED no leído)"))


# --------------------------------------------------------------------------
# Modo gráfico

def unidades_de(s, unidades, sens_v_ms):
    """(factor por cuenta, nombre) según la entrada activa y las unidades pedidas.
    La entrada y la ganancia se leen del estado del M4 (adc_r0, adc_r1)."""
    if s.get("fuente") != "adc":
        return 1.0, "cuentas"
    r0, r1 = int(s.get("adc_r0", 0)), int(s.get("adc_r1", 0))
    mux, ts = r0 >> 4, (r1 >> 1) & 1
    g = 1 if r0 & 1 else 1 << ((r0 >> 1) & 7)
    v_cuenta = VREF / (g * 2 ** 23)
    if ts:
        return 0.03125 / 1024, "°C"         # 14 bits alineados a la izquierda
    if mux == 0xD:
        return 4 * v_cuenta, "V (AVDD)"
    if unidades == "ums" and mux == 0x0:
        return v_cuenta / sens_v_ms * 1e6, "µm/s"
    if unidades in ("uv", "ums"):
        return v_cuenta * 1e6, "µV"
    return 1.0, "cuentas"


def bonito(x):
    """Número con 3 cifras significativas, sin notación científica."""
    a = abs(x)
    if a >= 100:
        return f"{x:.0f}"
    if a >= 10:
        return f"{x:.1f}"
    if a >= 1:
        return f"{x:.2f}"
    return f"{x:.3g}"


def grafico(pantalla_completa):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib, Gdk

    c = Canal()
    cb, por_que = abre_bin()
    st = Estado()
    if not cb:
        st.respuestas.append("sin binario: " + por_que[:40])
    exporta_led()
    conf, habia_conf = lee_conf()

    def leer(*_):
        for l in c.lee_lineas():
            st.procesa(l)
        return True

    def leer_bin(*_):
        for m in cb.lee():
            if isinstance(m, bytes):
                st.binario(m)
            else:
                st.procesa(m)
        return True

    # Vista: qué tramo de la historia se dibuja
    vista = {
        "vivo": True,           # el borde derecho sigue a la última muestra
        "k_der": 0,             # posición del borde derecho si está congelada
        "vent": conf["ventana_s"] if conf["ventana_s"] in VENTANAS else VENTANA_S,
        "amp": None,            # semiescala fija en cuentas, o None = automática
        "esc": 100.0,           # última semiescala usada (para pasar a fija)
        "marcas": [],           # posiciones k de P y S
        "arrastre": None,       # (x inicial, k_der inicial, se movió)
    }

    def n_vent():
        return max(2, int(vista["vent"] * st.fs))

    def k_derecha():
        ult = st.ktot() - 1
        if vista["vivo"]:
            return ult
        k = min(vista["k_der"], ult)
        return max(k, st.k0 + min(n_vent(), len(st.vals)) - 1)

    def fs_real():
        try:
            return int(st.s["fs_real_mhz"]) / 1000.0 or st.fs
        except (KeyError, ValueError):
            return float(st.fs)

    win = Gtk.Window(title="Instrumento M4")
    win.set_default_size(800, 480)
    caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    win.add(caja)

    area = Gtk.DrawingArea()
    area.set_vexpand(True)
    area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                    Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK)
    caja.pack_start(area, True, True, 0)

    sup = PANEL_XFCE if pantalla_completa else 0
    CAB = 46            # alto de la cabecera
    EJE = 16            # alto del eje de tiempo

    def dibuja(w, cr):
        W, H = w.get_allocated_width(), w.get_allocated_height()
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        cr.translate(0, sup)
        H -= sup
        s = st.s
        led = lee_led()
        fac, uni = unidades_de(s, conf["unidades"], conf["sens_v_ms"])
        fr = fs_real()

        # Cabecera: estado del M4
        if s.get("fuente") == "adc":
            fuente = "ADC " + (aplicada["txt"] or "")
        else:
            fuente = "sintética"
        filtro = int(s.get("filtro", 0) or 0)
        if not filtro:
            ftxt = "sin filtro"
        elif s.get("filtro_hw") == "1":
            ftxt = f"red {filtro} Hz (ADS1220)"
        elif int(s.get("notch_mhz", 0) or 0):
            ftxt = f"red {filtro} Hz → notch {int(s['notch_mhz']) / 1000:.2f} Hz"
        else:
            ftxt = f"red {filtro} Hz: no aplicable"
        cr.set_source_rgb(0.1, 0.1, 0.1)
        cr.select_font_face("Sans")
        cr.set_font_size(14)
        cr.move_to(8, 17)
        cr.show_text(f"{fuente}   {fr:.2f} SPS   {ftxt}   "
                     f"eventos={s.get('eventos', '?')}  perdidos={s.get('perdidos', '?')}"
                     + ("  calentando" if st.via == "binario" and st.flags & 2 else ""))
        cr.set_font_size(12)
        cr.move_to(8, 36)
        carga = int(s["carga_ppm"]) / 1e4 if "carga_ppm" in s else int(s.get("carga_pm", 0)) / 10
        cr.show_text(f"carga M4 {carga:.2f} %   peor {s.get('peor_us', '?')} µs   "
                     f"umbral {int(s.get('umbral_on', 0)) / 10:.1f}/"
                     f"{int(s.get('umbral_off', 0)) / 10:.1f}   "
                     f"tx={'sí' if s.get('tx') == '1' else 'no'}   vía {st.via}")
        if st.respuestas:                       # última respuesta del M4
            cr.set_font_size(11)
            cr.set_source_rgb(0.1, 0.45, 0.1)
            cr.move_to(W - 250, 36)
            cr.show_text(st.respuestas[-1][:34])
        cr.set_source_rgb(*((0.9, 0.1, 0.1) if led else (0.85, 0.85, 0.85)))
        cr.arc(W - 20, 16, 11, 0, 6.2832)
        cr.fill()

        # Ventana visible, en posiciones k
        y0, h = CAB, H - CAB - EJE
        n = n_vent()
        kd = k_derecha()
        ki = kd - n + 1                         # posición en x = 0
        def x_de_k(k):
            return (k - ki + 0.5) * W / n
        def x_de(i):
            return x_de_k(st.pos(i))
        cr.set_source_rgb(0.97, 0.97, 0.97) if vista["vivo"] else cr.set_source_rgb(0.95, 0.96, 1.0)
        cr.rectangle(0, y0, W, h)
        cr.fill()

        # eventos sombreados
        for ini, fin, ratio, pico in st.eventos:
            f = fin if fin is not None else st.ultima
            if x_de(f) < 0 or x_de(ini) > W:
                continue
            cr.set_source_rgba(1, 0.55, 0.1, 0.25)
            xa = max(0, x_de(ini))
            cr.rectangle(xa, y0, max(2, min(W, x_de(f)) - xa), h)
            cr.fill()
        # uniones: pausas (gris) y pérdidas (rojo)
        cr.set_font_size(11)
        for r, g, por_pausa in st.saltos:
            x = x_de(r) + 0.5 * W / n
            if x < 0 or x > W:
                continue
            cr.set_source_rgb(*((0.55, 0.55, 0.55) if por_pausa else (0.85, 0.1, 0.1)))
            cr.set_dash([4, 3])
            cr.move_to(x, y0)
            cr.line_to(x, y0 + h)
            cr.stroke()
            cr.set_dash([])
            cr.move_to(min(x + 3, W - 80), y0 + 26)
            cr.show_text(f"pausa {g / st.fs:.0f} s" if por_pausa else f"perdidas {g}")

        # traza
        a = max(ki, st.k0) - st.k0              # índices en vals
        b = kd - st.k0 + 1
        if b - a >= 2:
            tramo = st.vals[a:b]
            media = sum(tramo) / len(tramo)
            x_a = x_de_k(a + st.k0)
            cols = []                           # (x, mín, máx) en cuentas
            m = len(tramo)
            px = W * m / n                      # píxeles que ocupa el tramo
            if m > 2 * px:                      # muchas muestras por píxel
                ncol = max(1, int(px))
                for cx in range(ncol):
                    t = tramo[cx * m // ncol:(cx + 1) * m // ncol]
                    if t:
                        cols.append((x_a + cx * px / ncol, min(t), max(t)))
                lo_g = min(cl[1] for cl in cols); hi_g = max(cl[2] for cl in cols)
            else:
                lo_g, hi_g = min(tramo), max(tramo)
            esc_auto = max(abs(hi_g - media), abs(media - lo_g), 1) * 1.1
            esc = vista["amp"] or esc_auto
            vista["esc"] = esc
            def y_de(v):
                return y0 + h / 2 - (v - media) / esc * h / 2
            cr.save()
            cr.rectangle(0, y0, W, h)
            cr.clip()
            cr.set_source_rgb(0.05, 0.2, 0.6)
            cr.set_line_width(1)
            if cols:
                for x, lo, hi in cols:
                    cr.move_to(int(x) + 0.5, y_de(hi))
                    cr.line_to(int(x) + 0.5, y_de(lo) + 1)
            else:
                paso = W / n
                cr.move_to(x_a, y_de(tramo[0]))
                for j in range(1, m):
                    cr.line_to(x_a + j * paso, y_de(tramo[j]))
                if paso > 6:                    # muy ampliado: se ven las muestras
                    cr.stroke()
                    for j in range(m):
                        cr.arc(x_a + j * paso, y_de(tramo[j]), 1.6, 0, 6.2832)
                        cr.fill()
            cr.stroke()
            cr.restore()
            cr.set_source_rgb(0.3, 0.3, 0.3)
            cr.set_font_size(11)
            cr.move_to(4, y0 + 12)
            cr.show_text(f"±{bonito(esc * fac)} {uni}"
                         + ("" if vista["amp"] else " (auto)")
                         + f"   media {bonito(media * fac)} {uni}")

        # marcas P y S
        nombres = ("P", "S")
        for j, km in enumerate(vista["marcas"]):
            x = x_de_k(km)
            if 0 <= x <= W:
                cr.set_source_rgb(*((0.8, 0.0, 0.0) if j == 0 else (0.0, 0.55, 0.0)))
                cr.set_line_width(1.5)
                cr.move_to(x, y0)
                cr.line_to(x, y0 + h)
                cr.stroke()
                cr.set_font_size(14)
                cr.move_to(x + 3, y0 + h - 6)
                cr.show_text(nombres[j])
        if len(vista["marcas"]) == 2:
            dt = abs(vista["marcas"][1] - vista["marcas"][0]) / fr
            cr.set_source_rgb(0.1, 0.1, 0.1)
            cr.set_font_size(13)
            cr.move_to(W / 2 - 120, y0 + 14)
            cr.show_text(f"S−P = {dt:.2f} s   ≈ {8 * dt:.0f} km")

        # eje de tiempo: segundos respecto a la última muestra recibida
        ult = st.ktot() - 1
        cr.set_source_rgb(0.4, 0.4, 0.4)
        cr.set_font_size(11)
        span = n / fr
        paso = next((p for p in (0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 30, 60) if span / p <= 7), 60)
        t_der = (kd - ult) / fr
        t = paso * math.floor(t_der / paso)
        while t >= t_der - span:
            x = x_de_k(ult + t * fr)
            cr.move_to(x, y0 + h)
            cr.line_to(x, y0 + h + 4)
            cr.stroke()
            etiqueta = "0" if abs(t) < 1e-9 else f"{t:g} s"
            cr.move_to(min(max(x - 12, 2), W - 40), y0 + h + 14)
            cr.show_text(etiqueta)
            t -= paso
        if not vista["vivo"]:                   # hora aproximada del borde derecho
            hora = time.strftime("%H:%M:%S", time.localtime(st.t_ultima + t_der))
            cr.set_source_rgb(0.2, 0.2, 0.7)
            cr.move_to(W - 150, y0 + 26)
            cr.show_text(f"congelada · {hora}")

    area.connect("draw", dibuja)

    # Ratón o dedo sobre la traza: arrastrar desplaza; un toque pone P y S;
    # la rueda cambia la escala de tiempo.
    def pulsa(w, ev):
        if ev.type != Gdk.EventType.BUTTON_PRESS:  # dobles y triples: solo cuentan los simples
            return True
        vista["arrastre"] = (ev.x, k_derecha(), False)
        return True

    def mueve(w, ev):
        ar = vista["arrastre"]
        if not ar:
            return False
        dx = ev.x - ar[0]
        if abs(dx) > 8 or ar[2]:
            vista["arrastre"] = (ar[0], ar[1], True)
            vista["vivo"] = False
            vista["k_der"] = int(ar[1] - dx * n_vent() / max(1, w.get_allocated_width()))
            area.queue_draw()
        return True

    def suelta(w, ev):
        ar = vista["arrastre"]
        vista["arrastre"] = None
        if ar and not ar[2]:                    # toque sin arrastre: marca
            W = max(1, w.get_allocated_width())
            k = k_derecha() - n_vent() + 1 + int(ev.x * n_vent() / W)
            if len(vista["marcas"]) >= 2:
                vista["marcas"] = []
            vista["marcas"].append(k)
            area.queue_draw()
        return True

    def rueda(w, ev):
        if ev.direction == Gdk.ScrollDirection.UP:
            zoom_t(-1)
        elif ev.direction == Gdk.ScrollDirection.DOWN:
            zoom_t(+1)
        return True

    area.connect("button-press-event", pulsa)
    area.connect("motion-notify-event", mueve)
    area.connect("button-release-event", suelta)
    area.connect("scroll-event", rueda)

    # --- Fila 1: órdenes al M4 -------------------------------------------
    barra = Gtk.Box(spacing=3)
    caja.pack_start(barra, False, False, 1)

    def boton(fila_, texto, accion, expandir=True):
        b = Gtk.Button(label=texto)
        b.connect("clicked", lambda *_: accion())
        fila_.pack_start(b, expandir, expandir, 0)
        return b

    def orden(texto_fn):
        return lambda: c.envia(texto_fn())

    def pausa_sigue():
        return "pausa" if st.s.get("tx") == "1" else "inicia"

    def umbral(delta):
        on = int(st.s.get("umbral_on", 30)) + delta
        on = min(max(on, 15), 200)
        return f"umbral {on} {max(10, on // 2)}"

    def ruido(f):
        r = int(st.s.get("ruido", 20))
        return f"ruido {max(0, min(100000, int(r * f) if r else 10))}"

    solo_sint = [boton(barra, "¡Sismo!", orden(lambda: "sismo"))]
    b_pausa = boton(barra, "Pausa", orden(pausa_sigue))
    solo_sint += [boton(barra, "10", orden(lambda: "fs 10")),
                  boton(barra, "100", orden(lambda: "fs 100")),
                  boton(barra, "250 SPS", orden(lambda: "fs 250"))]
    boton(barra, "Umbral−", orden(lambda: umbral(-5)))
    boton(barra, "Umbral+", orden(lambda: umbral(+5)))
    solo_sint += [boton(barra, "Ruido×2", orden(lambda: ruido(2))),
                  boton(barra, "Ruido÷2", orden(lambda: ruido(0.5)))]
    boton(barra, "✕", Gtk.main_quit)

    # --- Fila 2: la fuente del M4, el filtro y el reparto del SPI ---------
    fila = Gtk.Box(spacing=3)
    caja.pack_start(fila, False, False, 1)

    def combo(fila_, opciones, activo):
        cb_ = Gtk.ComboBoxText()
        for ident, texto in opciones:
            cb_.append(str(ident), texto)
        cb_.set_active_id(str(activo))
        fila_.pack_start(cb_, False, False, 0)
        return cb_

    c_fuente = combo(fila, [("sint", "sintética"), ("adc", "ADS1220")], conf["fuente"])
    c_entrada = combo(fila, ENTRADAS, conf["entrada"])
    c_pga = combo(fila, [(g, f"×{g}") for g in PGAS], conf["pga"])
    c_sps = combo(fila, [(v, f"{v} SPS") for v in SPSS], conf["sps"])
    b_aplicar = Gtk.Button(label="Aplicar")
    fila.pack_start(b_aplicar, False, False, 0)
    c_filtro = combo(fila, FILTROS, conf["filtro"])
    l_spi = Gtk.Label(label="")
    fila.pack_start(l_spi, True, True, 0)

    aplicada = {"txt": "", "fuente": None}      # lo último que se pidió al M4
    espera = {"adc": 0.0}                       # comprobar que el ADC respondió

    def sensibles(*_):
        adc = c_fuente.get_active_id() == "adc"
        c_entrada.set_sensitive(adc)
        c_sps.set_sensitive(adc)
        c_pga.set_sensitive(adc and c_entrada.get_active_id() in ("ain01", "corto"))

    c_fuente.connect("changed", sensibles)
    c_entrada.connect("changed", sensibles)
    sensibles()

    def devolver():
        err = spi_m4("devolver")
        if err:
            st.respuestas.append("ERR spi-m4: " + err)
        return False

    def aplicar(*_):
        conf.update(fuente=c_fuente.get_active_id(), entrada=c_entrada.get_active_id(),
                    pga=int(c_pga.get_active_id()), sps=int(c_sps.get_active_id()))
        guarda_conf(conf)
        if conf["fuente"] == "adc":
            err = spi_m4("ceder")               # primero soltar Linux
            if err:
                st.respuestas.append("ERR spi-m4: " + err)
                return
            g = conf["pga"] if conf["entrada"] in ("ain01", "corto") else 1
            c.envia(f"fuente adc {conf['entrada']} {g} {conf['sps']}")
            aplicada["txt"] = f"{conf['entrada']} ×{g}"
            espera["adc"] = time.time()
            GLib.timeout_add(700, lambda: (c.envia("estado"), False)[1])
        else:
            c.envia("fuente sint")              # el M4 suelta el bus en su tarea...
            aplicada["txt"] = ""
            espera["adc"] = 0.0
            GLib.timeout_add(600, devolver)     # ...y entonces vuelve a Linux
        aplicada["fuente"] = conf["fuente"]
        vista["marcas"] = []

    def cambia_filtro(*_):
        conf["filtro"] = int(c_filtro.get_active_id())
        guarda_conf(conf)
        c.envia(f"filtro {conf['filtro']}")
        GLib.timeout_add(500, lambda: (c.envia("estado"), False)[1])

    b_aplicar.connect("clicked", aplicar)
    c_filtro.connect("changed", cambia_filtro)

    # --- Fila 3: navegación por la traza ----------------------------------
    nav = Gtk.Box(spacing=3)
    caja.pack_start(nav, False, False, 1)

    def en_vivo():
        vista["vivo"] = True
        area.queue_draw()

    def congela_vivo():
        if vista["vivo"]:
            vista["k_der"] = k_derecha()
            vista["vivo"] = False
        else:
            vista["vivo"] = True
        area.queue_draw()

    def desplaza(fraccion):
        if vista["vivo"]:
            vista["k_der"] = k_derecha()
            vista["vivo"] = False
        vista["k_der"] = int(k_derecha() + fraccion * n_vent())
        if vista["k_der"] >= st.ktot() - 1 and fraccion > 0:
            vista["vivo"] = True                # llegó al presente
        area.queue_draw()

    def zoom_t(paso):
        i = VENTANAS.index(vista["vent"]) if vista["vent"] in VENTANAS else 5
        i = min(max(i + paso, 0), len(VENTANAS) - 1)
        if not vista["vivo"]:                   # congelada: conserva el centro
            centro = k_derecha() - n_vent() // 2
            vista["vent"] = VENTANAS[i]
            vista["k_der"] = centro + n_vent() // 2
        else:
            vista["vent"] = VENTANAS[i]
        conf["ventana_s"] = vista["vent"]
        guarda_conf(conf)
        area.queue_draw()

    def zoom_a(f):
        vista["amp"] = (vista["amp"] or vista["esc"]) * f
        area.queue_draw()

    def amp_auto():
        vista["amp"] = None
        area.queue_draw()

    def borra_marcas():
        vista["marcas"] = []
        area.queue_draw()

    def cambia_unidades(*_):
        conf["unidades"] = c_uni.get_active_id()
        guarda_conf(conf)
        area.queue_draw()

    b_vivo = boton(nav, "Congelar", congela_vivo)
    boton(nav, "◀◀", lambda: desplaza(-1.0))
    boton(nav, "◀", lambda: desplaza(-0.25))
    boton(nav, "▶", lambda: desplaza(+0.25))
    boton(nav, "▶▶", lambda: desplaza(+1.0))
    nav.pack_start(Gtk.Label(label=" t"), False, False, 0)
    boton(nav, "+", lambda: zoom_t(-1))
    boton(nav, "−", lambda: zoom_t(+1))
    l_vent = Gtk.Label(label="")
    nav.pack_start(l_vent, False, False, 0)
    nav.pack_start(Gtk.Label(label=" A"), False, False, 0)
    boton(nav, "+", lambda: zoom_a(0.5))
    boton(nav, "−", lambda: zoom_a(2.0))
    boton(nav, "auto", amp_auto)
    boton(nav, "✕P/S", borra_marcas)
    c_uni = combo(nav, UNIDADES, conf["unidades"])
    c_uni.connect("changed", cambia_unidades)

    GLib.io_add_watch(c.fd, GLib.PRIORITY_DEFAULT, GLib.IO_IN, leer)
    if cb:
        GLib.io_add_watch(cb.fd, GLib.PRIORITY_DEFAULT, GLib.IO_IN, leer_bin)
        GLib.timeout_add(int(LATIDO_S * 1000), cb.latido)

    def refresca():
        area.queue_draw()
        b_pausa.set_label("Pausa" if st.s.get("tx", "1") == "1" else "Sigue")
        b_vivo.set_label("Congelar" if vista["vivo"] else "En vivo")
        v = vista["vent"]
        l_vent.set_text(f"{v // 60} min" if v >= 60 else f"{v} s")
        adc = st.s.get("fuente") == "adc"
        for b in solo_sint:
            b.set_sensitive(not adc)
        l_spi.set_text("SPI: " + ("Linux" if os.path.exists(SPI_LIGADO) else "M4"))
        # ¿Tomó el M4 el ADC? Si no responde, el M4 vuelve solo a la sintética
        # (adc_err≠0) y el bus debe volver a Linux.
        if espera["adc"] and st.t_s > espera["adc"] + 0.5:
            espera["adc"] = 0.0
            if st.s.get("fuente") != "adc":
                st.respuestas.append(f"ERR el ADC no responde (adc_err={st.s.get('adc_err', '?')})")
                aplicada["txt"] = ""
                devolver()
        return True

    GLib.timeout_add(100, refresca)
    for o in ("hola", "inicia", f"filtro {conf['filtro']}", "estado"):
        c.envia(o)
    if habia_conf:
        GLib.timeout_add(300, lambda: (aplicar(), False)[1])

    win.connect("destroy", Gtk.main_quit)
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    if pantalla_completa:
        # xfwm deja el panel de XFCE por encima de una ventana a pantalla
        # completa: mejor ocupar exactamente el área útil, sin bordes.
        mon = Gdk.Display.get_default().get_primary_monitor() or \
            Gdk.Display.get_default().get_monitor(0)
        a = mon.get_workarea()
        win.set_decorated(False)
        win.move(a.x, a.y)
        win.set_default_size(a.width, a.height)
        win.resize(a.width, a.height)
    win.show_all()
    try:
        Gtk.main()
    finally:
        # Al cerrar, el bus vuelve a Linux: primero el M4 lo suelta.
        if aplicada["fuente"] == "adc" or st.s.get("fuente") == "adc" \
                or not os.path.exists(SPI_LIGADO):
            c.envia("fuente sint")
            time.sleep(0.6)
            devolver()
        if cb:
            cb.cierra()
        c.cierra()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--consola", action="store_true")
    ap.add_argument("--ventana", action="store_true")
    ap.add_argument("-s", "--segundos", type=float, default=20)
    ap.add_argument("ordenes", nargs="*")
    a = ap.parse_args()
    if a.consola:
        consola(a.segundos, a.ordenes)
    else:
        grafico(not a.ventana)
