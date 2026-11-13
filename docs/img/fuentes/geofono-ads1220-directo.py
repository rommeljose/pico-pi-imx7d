import sys
import schemdraw
import schemdraw.elements as elm
schemdraw.config(fontsize=12, font='DejaVu Sans')
salida = sys.argv[1]

with schemdraw.Drawing(show=False) as d:
    d.config(unit=3)
    # --- geófono: bobina ---
    elm.Line().at((0, 0)).right(0.0001)
    L = elm.Inductor2(loops=4).at((0, 0)).down(4).label('Bobina\n375 Ω', loc='top', ofst=0.3)
    elm.Label().at((0.6, 1.3)).label('GEÓFONO  SM-6, 10 Hz', fontsize=13, halign='center')
    elm.Line().at((0, 0)).right(2)
    elm.Dot()
    Rsh = elm.Resistor().at((2, 0)).down(4).label('R5  1 kΩ\namortiguamiento\n(β ≈ 0,7)', loc='bottom', ofst=0.25)
    elm.Line().at((0, -4)).right(2)
    elm.Dot()
    # --- rama superior: AIN0 ---
    elm.Line().at((2, 0)).right(3)
    R1 = elm.Resistor().at((5, 0)).right(3).label('R1  1 kΩ')
    elm.Line().at((8, 0)).right(2.5)
    elm.Dot().at((9.5, 0))
    # --- rama inferior: AIN1 ---
    elm.Line().at((2, -4)).right(1.5)
    elm.Dot().at((3.5, -4)).label('V$_{MID}$ ≈ 1,65 V', loc='top', ofst=0.15)
    elm.Line().at((3.5, -4)).right(1.5)
    R2 = elm.Resistor().at((5, -4)).right(3).label('R2  1 kΩ')
    elm.Line().at((8, -4)).right(2.5)
    elm.Dot().at((9.5, -4))
    # --- filtro diferencial ---
    elm.Capacitor().at((9.5, 0)).down(4).label('C1\n100 nF', loc='top', ofst=0.2)
    # --- polarización a media tensión ---
    elm.Line().at((3.5, -4)).down(2.5)
    elm.Dot().at((3.5, -6.5))
    R4 = elm.Resistor().at((3.5, -6.5)).down(3).label('R4\n10 kΩ', loc='bottom', ofst=0.2)
    elm.Ground().at((3.5, -9.5))
    elm.Line().at((3.5, -6.5)).left(1.5)
    C2 = elm.Capacitor(polar=True).at((2, -6.5)).down(3).label('C2 10 µF\n(+ arriba)', loc='top', ofst=0.2)
    elm.Ground().at((2, -9.5))
    R3 = elm.Resistor().at((3.5, -6.5)).right(3.5).label('R3  10 kΩ', loc='bottom')
    elm.Line().at((7, -6.5)).right(1)
    elm.Vdd().at((8, -6.5)).label('AVDD 3,3 V\n(VCC del módulo)', ofst=0.1)
    # --- módulo ADS1220 ---
    ic = elm.Ic(pins=[elm.IcPin(name='AIN3', side='left', slot='1/4'),
                      elm.IcPin(name='AIN2', side='left', slot='2/4'),
                      elm.IcPin(name='AIN1', side='left', slot='3/4'),
                      elm.IcPin(name='AIN0', side='left', slot='4/4'),
                      elm.IcPin(name='CS', side='right', slot='1/6'),
                      elm.IcPin(name='SCLK', side='right', slot='2/6'),
                      elm.IcPin(name='DOUT', side='right', slot='3/6'),
                      elm.IcPin(name='DIN', side='right', slot='4/6'),
                      elm.IcPin(name='GND', side='right', slot='5/6'),
                      elm.IcPin(name='VCC', side='right', slot='6/6')],
                edgepadW=0.6, pinspacing=1.33, w=5.5, leadlen=0.8,
                label='CJMCU-1220 (ADS1220)', lblloc='top', lblofst=0.3).anchor('AIN0').at((12, 0.0001))
    elm.Line().at((9.5, 0)).to(ic.AIN0)
    elm.Line().at((9.5, -4)).right(1.5)
    elm.Line().at((11, -4)).to((11, ic.AIN1[1]))
    elm.Line().at((11, ic.AIN1[1])).to(ic.AIN1)
    # pines digitales -> J8
    j8 = {'VCC': 'J8-1  (3,3 V)', 'GND': 'J8-20 o 25', 'DIN': 'J8-19  MOSI',
          'DOUT': 'J8-21  MISO', 'SCLK': 'J8-23', 'CS': 'J8-26'}
    for p, t in j8.items():
        a = getattr(ic, p)
        elm.Line().at(a).right(1.2)
        elm.Label().at((a[0] + 1.35, a[1])).label(t, halign='left')
    elm.Label().at((ic.AIN3[0] - 0.8, ic.AIN3[1] - 3.2)).label(
        'AIN2, AIN3, DRDY, REFP0/REFN0: sin conectar\nCLK a DGND (oscilador interno)', fontsize=10, halign='left')
    # --- notas ---
    elm.Label().at((-2.8, -11.6)).label(
        'Del geófono a R1/R2: cable apantallado y trenzado; la malla a GND SOLO en el lado del ADS1220.\n'
        'Todas las masas (GND del módulo, R4, C2, malla) van al mismo GND de J8 (20 o 25).\n'
        'Ninguna entrada AIN puede bajar de 0 V ni pasar de 3,3 V: por eso V$_{MID}$ centra la bobina.\n'
        'Si el geófono trae 3 hilos: los 2 de la bobina a la red de arriba; el de carcasa/masa, a la malla.  [VERIFICAR]',
        fontsize=10.5, halign='left')
    d.save(salida, dpi=160, transparent=False)
