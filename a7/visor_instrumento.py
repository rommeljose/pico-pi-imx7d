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
Para ver el ADC: m4orden.py "fuente adc ain01 128 90" (con spi_imx desligado)
antes de lanzar el visor; la fuente es estado del M4 y el visor no la cambia.

Protocolo: ver docs/M4_Instrumento_Bitacora.md.
Copyright (c) 2026 rommeljose y colaboradores. MIT.
"""
import argparse
import array
import collections
import fcntl
import glob
import os
import signal
import struct
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
VENTANA_S = 30                          # segundos de traza en pantalla
PANEL_XFCE = 26     # px: el panel de XFCE se dibuja encima sin reservar su franja


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
        # Muestras con su índice del M4. Las pausas se «comprimen»: la traza
        # anterior queda pegada a la nueva y la unión se marca en pantalla.
        self.datos = collections.deque(maxlen=VENTANA_S * 250)   # (i, v)
        self.ultima = -1            # índice de la última muestra recibida
        self.base = None            # índice que ocupa la posición 0
        self.saltos = []            # (última antes, muestras saltadas, por_pausa)
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

    def bloque(self, ini, fs, vals, seq=None):
        if fs != self.fs:           # otra base de tiempo: se empieza de cero
            self.fs = fs
            self.datos.clear()
            self.saltos.clear()
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
        self.datos.extend((ini + k, v) for k, v in enumerate(vals))
        self.ultima = ini + len(vals) - 1
        # los saltos que ya salieron de la ventana pasan a la base
        while self.saltos and self.saltos[0][0] < self.datos[0][0]:
            self.base += self.saltos.pop(0)[1]
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
        """Posición en la traza del índice i del M4, con las pausas comprimidas."""
        return i - (self.base or 0) - sum(g for r, g, _ in self.saltos if i > r)


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
          f"muestras {len(st.datos)} en memoria, huecos {st.huecos}, "
          f"pausas {sum(1 for *_, pp in st.saltos if pp)}")
    if st.s:
        print("último estado:", " ".join(f"{k}={v}" for k, v in st.s.items()))
    print(f"eventos vistos {len(st.eventos)}, cambios del LED {cambios_led}"
          + ("" if led_ok else " (GPIO 38 no exportado: LED no leído)"))


# --------------------------------------------------------------------------
# Modo gráfico

def grafico(pantalla_completa):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib

    c = Canal()
    cb, por_que = abre_bin()
    st = Estado()
    if not cb:
        st.respuestas.append("sin binario: " + por_que[:40])
    exporta_led()

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

    win = Gtk.Window(title="Instrumento M4")
    win.set_default_size(800, 480)
    caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    win.add(caja)

    area = Gtk.DrawingArea()
    area.set_vexpand(True)
    caja.pack_start(area, True, True, 0)

    sup = PANEL_XFCE if pantalla_completa else 0

    def dibuja(w, cr):
        W, H = w.get_allocated_width(), w.get_allocated_height()
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        cr.translate(0, sup)
        H -= sup
        cab = 46
        # Cabecera: estado del M4
        led = lee_led()
        s = st.s
        cr.set_source_rgb(0.1, 0.1, 0.1)
        cr.select_font_face("Sans")
        cr.set_font_size(15)
        cr.move_to(8, 18)
        cr.show_text(f"fs={st.fs} SPS   "
                     f"tx={'sí' if s.get('tx') == '1' else 'no'}   "
                     f"sismos={s.get('sismos', '?')}  eventos={s.get('eventos', '?')}  "
                     f"perdidos={s.get('perdidos', '?')}   vía {st.via}"
                     + ("  calentando" if st.via == "binario" and st.flags & 2 else ""))
        if st.respuestas:                       # última respuesta del M4
            cr.set_font_size(11)
            cr.set_source_rgb(0.1, 0.45, 0.1)
            cr.move_to(W - 260, 18)
            cr.show_text(st.respuestas[-1][:36])
            cr.set_source_rgb(0.1, 0.1, 0.1)
            cr.set_font_size(15)
        cr.move_to(8, 38)
        carga = int(s["carga_ppm"]) / 1e4 if "carga_ppm" in s else int(s.get("carga_pm", 0)) / 10
        cr.show_text(f"carga M4={carga:.2f} %   "
                     f"peor muestra={s.get('peor_us', '?')} µs   "
                     f"jitter={s.get('jitter_us', '?')} µs   "
                     f"umbral={int(s.get('umbral_on', 0)) / 10:.1f}/"
                     f"{int(s.get('umbral_off', 0)) / 10:.1f}   "
                     f"ruido={s.get('ruido', '?')}")
        # LED (leído del GPIO, no del protocolo)
        cr.set_source_rgb(*((0.9, 0.1, 0.1) if led else (0.85, 0.85, 0.85)))
        cr.arc(W - 22, 22, 13, 0, 6.2832)
        cr.fill()
        cr.set_source_rgb(0.3, 0.3, 0.3)
        cr.set_font_size(10)
        cr.move_to(W - 40, 44)
        cr.show_text("LED" if led is not None else "LED n/d")

        # Traza: min/máx por columna
        y0, h = cab + 4, H - cab - 26
        cr.set_source_rgb(0.97, 0.97, 0.97)
        cr.rectangle(0, y0, W, h)
        cr.fill()
        n_vent = VENTANA_S * st.fs
        primera = st.pos(st.ultima) - n_vent + 1  # posición en x=0
        def x_de(i):
            return (st.pos(i) - primera) * W / n_vent
        m = [(i, v) for i, v in st.datos if st.pos(i) >= primera]
        # eventos sombreados
        for ini, fin, ratio, pico in st.eventos:
            f = fin if fin is not None else st.ultima
            if x_de(f) < 0:
                continue
            cr.set_source_rgba(1, 0.55, 0.1, 0.25)
            xa = max(0, x_de(ini))
            cr.rectangle(xa, y0, max(2, x_de(f) - xa), h)
            cr.fill()
        # uniones: pausas (gris) y pérdidas (rojo)
        cr.set_font_size(11)
        for r, g, por_pausa in st.saltos:
            x = x_de(r) + 0.5
            if x < 0:
                continue
            cr.set_source_rgb(*((0.55, 0.55, 0.55) if por_pausa else (0.85, 0.1, 0.1)))
            cr.set_dash([4, 3])
            cr.move_to(x, y0)
            cr.line_to(x, y0 + h)
            cr.stroke()
            cr.set_dash([])
            cr.move_to(min(x + 3, W - 80), y0 + 26)
            cr.show_text(f"pausa {g / st.fs:.0f} s" if por_pausa else f"perdidas {g}")
        if m:
            esc = max(100, max(abs(v) for _, v in m)) * 1.1
            cr.set_source_rgb(0.05, 0.2, 0.6)
            cr.set_line_width(1)
            cols = {}
            for i, v in m:
                cx = int(x_de(i))
                lo, hi = cols.get(cx, (v, v))
                cols[cx] = (min(lo, v), max(hi, v))
            for cx in sorted(cols):
                lo, hi = cols[cx]
                cr.move_to(cx + 0.5, y0 + h / 2 - hi / esc * h / 2)
                cr.line_to(cx + 0.5, y0 + h / 2 - lo / esc * h / 2 + 1)
            cr.stroke()
            cr.set_source_rgb(0.4, 0.4, 0.4)
            cr.set_font_size(11)
            cr.move_to(4, y0 + 12)
            cr.show_text(f"±{int(esc)} cuentas")
        # eje de tiempo
        cr.set_source_rgb(0.4, 0.4, 0.4)
        cr.set_font_size(11)
        for seg in range(0, VENTANA_S + 1, 5):
            x = W - seg * W / VENTANA_S
            cr.move_to(min(max(x - 10, 2), W - 30), y0 + h + 14)
            cr.show_text(f"-{seg} s" if seg else "0")

    area.connect("draw", dibuja)

    barra = Gtk.Box(spacing=4)
    caja.pack_start(barra, False, False, 2)

    def boton(texto, orden_fn):
        b = Gtk.Button(label=texto)
        b.connect("clicked", lambda *_: c.envia(orden_fn()))
        barra.pack_start(b, True, True, 0)
        return b

    def pausa_sigue():
        return "pausa" if st.s.get("tx") == "1" else "inicia"

    def umbral(delta):
        on = int(st.s.get("umbral_on", 30)) + delta
        on = min(max(on, 15), 200)
        return f"umbral {on} {max(10, on // 2)}"

    def ruido(f):
        r = int(st.s.get("ruido", 20))
        return f"ruido {max(0, min(100000, int(r * f) if r else 10))}"

    boton("¡Sismo!", lambda: "sismo")
    b_pausa = boton("Pausa", pausa_sigue)
    boton("10", lambda: "fs 10")
    boton("100", lambda: "fs 100")
    boton("250 SPS", lambda: "fs 250")
    boton("Umbral−", lambda: umbral(-5))
    boton("Umbral+", lambda: umbral(+5))
    boton("Ruido×2", lambda: ruido(2))
    boton("Ruido÷2", lambda: ruido(0.5))
    salir = Gtk.Button(label="✕")
    salir.connect("clicked", lambda *_: Gtk.main_quit())
    barra.pack_start(salir, True, True, 0)

    GLib.io_add_watch(c.fd, GLib.PRIORITY_DEFAULT, GLib.IO_IN, leer)
    if cb:
        GLib.io_add_watch(cb.fd, GLib.PRIORITY_DEFAULT, GLib.IO_IN, leer_bin)
        GLib.timeout_add(int(LATIDO_S * 1000), cb.latido)
    def refresca():
        area.queue_draw()
        b_pausa.set_label("Pausa" if st.s.get("tx", "1") == "1" else "Sigue")
        return True

    GLib.timeout_add(100, refresca)
    for o in ("hola", "inicia", "estado"):
        c.envia(o)

    win.connect("destroy", Gtk.main_quit)
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    if pantalla_completa:
        # xfwm deja el panel de XFCE por encima de una ventana a pantalla
        # completa: mejor ocupar exactamente el área útil, sin bordes.
        from gi.repository import Gdk
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
