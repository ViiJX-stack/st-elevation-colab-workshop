# -*- coding: utf-8 -*-
"""
Motor del entorno virtual "Reconocimiento de elevación del segmento ST".
Fase 1: solo elevación del ST (sin imitadores, sin otros diagnósticos).

Datos: PTB-XL v1.0.3 (PhysioNet), ECG de 12 derivaciones, 10 s, 500 Hz, en mV.
Criterio: Quinta Definición Universal del Infarto (ESC/ACC/AHA/WHF, 2026): elevación
NUEVA del ST medida en el punto J, en >= 2 derivaciones contiguas, en ausencia de
bloqueo de rama y/o hipertrofia ventricular izquierda:
  >= 1 mm en todas las derivaciones excepto V2-V3;
  V2-V3: >= 2 mm hombres >= 40 años; >= 2.5 mm hombres < 40 años; >= 1.5 mm mujeres.

Autor: Víctor Junior Godínez-Vázquez. Código: licencia MIT.
Material docente; no usar para decisiones clínicas.
"""
import ast
import os

import numpy as np
import pandas as pd
from scipy import signal as sps
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

LEADS = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF',
         'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
PTBXL_DIR = 'ptb-xl/1.0.3/'
PTBXL_URL = 'https://physionet.org/files/ptb-xl/1.0.3/'

# Territorios (grupos de derivaciones contiguas) para la fase 1.
# aVR se excluye a propósito: su elevación aislada es otro tema (fase posterior).
TERRITORIOS = {
    'Inferior': ['II', 'III', 'aVF'],
    'Lateral': ['I', 'aVL', 'V5', 'V6'],
    'Anterior': ['V1', 'V2', 'V3', 'V4'],
}
PRECORDIALES = ['V1', 'V2', 'V3', 'V4', 'V5', 'V6']

# Colores del papel de ECG
_MINOR = '#f6c9c9'
_MAJOR = '#e58b8b'
_TRACE = '#111111'

_CACHE = {}


# ----------------------------------------------------------------------------
# Carga de datos
# ----------------------------------------------------------------------------
def cargar_metadatos():
    """Tabla de PTB-XL (una fila por ECG) y catálogo de declaraciones SCP."""
    db = pd.read_csv(PTBXL_URL + 'ptbxl_database.csv', index_col='ecg_id')
    db['scp_codes'] = db['scp_codes'].apply(ast.literal_eval)
    scp = pd.read_csv(PTBXL_URL + 'scp_statements.csv', index_col=0)
    return db, scp


def cargar_registro(filename_hr):
    """Devuelve (señal [n_muestras x 12] en mV en el orden de LEADS, fs)."""
    if filename_hr in _CACHE:
        return _CACHE[filename_hr]
    import wfdb
    carpeta, nombre = os.path.split(filename_hr)
    rec = wfdb.rdrecord(nombre, pn_dir=PTBXL_DIR + carpeta)
    nombres = [n.upper() for n in rec.sig_name]
    orden = [nombres.index(l.upper()) for l in LEADS]
    sig = np.asarray(rec.p_signal, dtype=float)[:, orden]
    sig = np.nan_to_num(sig)
    _CACHE[filename_hr] = (sig, rec.fs)
    return sig, rec.fs


# ----------------------------------------------------------------------------
# Procesamiento
# ----------------------------------------------------------------------------
def filtrar(sig, fs):
    """Filtrado de fase cero que preserva el segmento ST.
    Paso alto 0.05 Hz (recomendación AHA para no deformar el ST),
    paso bajo 40 Hz y muesca a 50 Hz (red eléctrica de Alemania, origen de PTB-XL).
    """
    hp = sps.butter(2, 0.05, btype='highpass', fs=fs, output='sos')
    lp = sps.butter(4, 40, btype='lowpass', fs=fs, output='sos')
    y = sps.sosfiltfilt(hp, sig, axis=0)
    y = sps.sosfiltfilt(lp, y, axis=0)
    b, a = sps.iirnotch(50, 30, fs=fs)
    y = sps.filtfilt(b, a, y, axis=0)
    return y


def detectar_R(sig, fs):
    """Picos de los complejos QRS a partir de la energía de la pendiente en las 12 derivaciones."""
    bp = sps.butter(2, [5, 20], btype='bandpass', fs=fs, output='sos')
    x = sps.sosfiltfilt(bp, sig, axis=0)
    env = np.sum(np.abs(np.diff(x, axis=0)), axis=1)
    w = max(1, int(0.08 * fs))
    env = np.convolve(env, np.ones(w) / w, mode='same')
    umbral = 0.35 * np.percentile(env, 99)
    picos, _ = sps.find_peaks(env, height=umbral, distance=int(0.30 * fs))
    # Refinar: máximo de la señal absoluta en derivación con mayor amplitud
    lead = int(np.argmax(np.ptp(sig, axis=0)))
    r = []
    for p in picos:
        a, b = max(0, p - int(0.06 * fs)), min(len(sig), p + int(0.06 * fs))
        r.append(a + int(np.argmax(np.abs(sig[a:b, lead] - np.median(sig[a:b, lead])))))
    return np.array(sorted(set(r)), dtype=int)


def latido_mediano(sig, fs, pre=0.30, post=0.50):
    """Latido mediano por derivación (reduce ruido; es lo que miden los electrocardiógrafos)."""
    r = detectar_R(sig, fs)
    a, b = int(pre * fs), int(post * fs)
    ventanas = [sig[p - a:p + b] for p in r if p - a >= 0 and p + b <= len(sig)]
    if len(ventanas) < 3:
        return None, len(ventanas)
    return np.median(np.stack(ventanas), axis=0), len(ventanas)


def puntos_fiduciales(med, fs, pre=0.30):
    """Inicio del QRS y punto J (fin del QRS) en el latido mediano."""
    g = np.sum(np.abs(np.gradient(med, axis=0)), axis=1)
    w = max(1, int(0.01 * fs))
    g = np.convolve(g, np.ones(w) / w, mode='same')
    r = int(pre * fs)
    zona = g[r - int(0.08 * fs): r + int(0.08 * fs)]
    umbral = 0.12 * zona.max()
    sostener = int(0.012 * fs)
    # Inicio: hacia atrás desde R
    onset = r - int(0.04 * fs)
    for i in range(r, r - int(0.15 * fs), -1):
        if np.all(g[i - sostener:i] < umbral):
            onset = i
            break
    # Punto J: hacia adelante desde R
    j = r + int(0.06 * fs)
    for i in range(r + int(0.02 * fs), r + int(0.16 * fs)):
        if np.all(g[i:i + sostener] < umbral):
            j = i
            break
    return onset, j


def analizar(sig, fs, edad=None, sexo=None, ajuste_J_ms=0):
    """Mide el desnivel del ST en el punto J en cada derivación.

    sexo: 'H' (hombre) o 'M' (mujer).  ajuste_J_ms: corrección manual del instructor.
    Devuelve dict con latido mediano, puntos fiduciales y ST (mm) por derivación.
    """
    y = filtrar(sig, fs)
    med, n = latido_mediano(y, fs)
    if med is None:
        return None
    onset, j = puntos_fiduciales(med, fs)
    j = j + int(round(ajuste_J_ms * fs / 1000))
    b0, b1 = onset - int(0.025 * fs), onset - int(0.005 * fs)
    base = np.median(med[b0:b1], axis=0)
    stj = np.mean(med[j:j + int(0.004 * fs) + 1], axis=0)
    st60 = med[min(len(med) - 1, j + int(0.06 * fs))]
    st_mm = (stj - base) * 10.0
    umb = umbrales(edad, sexo)
    elev = {l: bool(st_mm[i] >= umb[l]) for i, l in enumerate(LEADS) if l != 'aVR'}
    elev['aVR'] = False
    cumple, territorios = criterio(elev)
    ruido_base = float(np.max(np.std(med[b0:b1], axis=0)) * 10)
    return {
        'med': med, 'fs': fs, 'onset': onset, 'j': j, 'r': int(0.30 * fs),
        'base': base, 'st_mm': {l: float(round(v, 2)) for l, v in zip(LEADS, st_mm)},
        'st60_mm': {l: float(round(v, 2)) for l, v in zip(LEADS, (st60 - base) * 10)},
        'umbral': umb, 'elevadas': [l for l in LEADS if elev[l]],
        'cumple': cumple, 'territorios': territorios, 'n_latidos': n,
        'qrs_ms': round((j - onset) * 1000 / fs), 'ruido_base_mm': round(ruido_base, 2),
        'senal': y,
    }


def umbrales(edad=None, sexo=None):
    """Umbral (mm) por derivación según la Quinta Definición Universal (2026)."""
    u = {l: 1.0 for l in LEADS}
    if sexo == 'M':
        v = 1.5
    elif sexo == 'H':
        v = 2.0 if (edad is None or edad >= 40) else 2.5
    else:
        v = 2.0
    u['V2'] = u['V3'] = v
    return u


def criterio(elevadas):
    """¿Hay elevación en >= 2 derivaciones contiguas? Devuelve (bool, territorios)."""
    if isinstance(elevadas, (list, set, tuple)):
        s = set(elevadas)
    else:
        s = {l for l, v in elevadas.items() if v}
    s.discard('aVR')
    terr = [t for t, ls in TERRITORIOS.items() if len(s & set(ls)) >= 2]
    # Contigüidad precordial a través del límite anterior/lateral (V4-V5)
    if {'V4', 'V5'} <= s and not terr:
        terr = ['Anterior', 'Lateral']
    return (len(terr) > 0), terr


def sexo_ptbxl(valor):
    """PTB-XL codifica sexo como 0 = hombre, 1 = mujer (verificar en la documentación)."""
    try:
        return 'H' if int(valor) == 0 else 'M'
    except (TypeError, ValueError):
        return None


def edad_ptbxl(valor):
    """PTB-XL anonimiza edades > 89 años como 300."""
    try:
        e = float(valor)
    except (TypeError, ValueError):
        return None
    if np.isnan(e):
        return None
    return 90.0 if e >= 300 else e


# ----------------------------------------------------------------------------
# Gráficas en papel de ECG (25 mm/s, 10 mm/mV, 1 mm = 0.04 s = 0.1 mV)
# ----------------------------------------------------------------------------
def _papel(ax, x0, x1, y0, y1):
    menores, mayores = [], []
    for k, x in enumerate(np.arange(x0, x1 + 1e-9, 0.04)):
        (mayores if k % 5 == 0 else menores).append([(x, y0), (x, y1)])
    ys = np.arange(np.floor(y0 * 10) / 10, y1 + 1e-9, 0.1)
    for y in ys:
        k = int(round(y * 10))
        (mayores if k % 5 == 0 else menores).append([(x0, y), (x1, y)])
    ax.add_collection(LineCollection(menores, colors=_MINOR, linewidths=0.4, zorder=0))
    ax.add_collection(LineCollection(mayores, colors=_MAJOR, linewidths=0.9, zorder=0))
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect(0.4)  # 1 mV (10 mm) mide 0.4 veces 1 s (25 mm)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def graficar_12(sig, fs, titulo=None, resaltar=None, ancho=16):
    """Trazo estándar 3 x 4 (2.5 s por columna) + tira de ritmo DII."""
    columnas = [['I', 'II', 'III'], ['aVR', 'aVL', 'aVF'],
                ['V1', 'V2', 'V3'], ['V4', 'V5', 'V6']]
    sep = 3.0
    alto = 4 * sep
    fig, ax = plt.subplots(figsize=(ancho, ancho * alto * 0.4 / 10.4 + 0.4))
    _papel(ax, -0.4, 10.0, -alto + 1.2, 1.2)
    n = int(2.5 * fs)
    t = np.arange(n) / fs
    for c, col in enumerate(columnas):
        for f, lead in enumerate(col):
            y0 = -f * sep
            i = LEADS.index(lead)
            seg = sig[c * n:(c + 1) * n, i]
            seg = seg - np.median(sig[:, i])
            ax.plot(c * 2.5 + t, y0 + seg, color=_TRACE, lw=0.9)
            color = '#c0392b' if resaltar and lead in resaltar else '#1a1a1a'
            peso = 'bold' if resaltar and lead in resaltar else 'normal'
            ax.text(c * 2.5 + 0.05, y0 + 0.75, lead, fontsize=11, color=color, weight=peso)
            if c > 0:
                ax.plot([c * 2.5, c * 2.5], [y0 - 0.3, y0 + 0.3], color=_TRACE, lw=1)
    # Tira de ritmo
    y0 = -3 * sep
    ii = sig[:int(10 * fs), 1] - np.median(sig[:, 1])
    ax.plot(np.arange(len(ii)) / fs, y0 + ii, color=_TRACE, lw=0.9)
    ax.text(0.05, y0 + 0.75, 'II', fontsize=11)
    # Pulso de calibración 1 mV x 0.2 s
    for f in range(4):
        y0 = -f * sep
        ax.plot([-0.35, -0.3, -0.3, -0.1, -0.1, -0.05],
                [y0, y0, y0 + 1, y0 + 1, y0, y0], color=_TRACE, lw=1)
    if titulo:
        ax.set_title(titulo, fontsize=12, loc='left')
    fig.text(0.99, 0.01, '25 mm/s · 10 mm/mV', ha='right', fontsize=8, color='#555')
    plt.tight_layout()
    return fig


def graficar_latidos(an, derivaciones=None, mostrar_medida=True, columnas=6, ancho=16):
    """Latido mediano de cada derivación con línea isoeléctrica, punto J y ST sombreado."""
    derivaciones = derivaciones or LEADS
    fs, med = an['fs'], an['med']
    t = (np.arange(len(med)) - an['r']) / fs
    filas = int(np.ceil(len(derivaciones) / columnas))
    fig, axes = plt.subplots(filas, columnas, figsize=(ancho, filas * 2.9))
    axes = np.atleast_1d(axes).ravel()
    for k, lead in enumerate(derivaciones):
        ax = axes[k]
        i = LEADS.index(lead)
        y = med[:, i] - an['base'][i]
        _papel(ax, -0.20, 0.44, -1.2, 1.6)
        ax.plot(t, y, color=_TRACE, lw=1.3)
        ax.axhline(0, color='#2471a3', ls='--', lw=1)
        tj = t[an['j']]
        if mostrar_medida:
            sel = (t >= tj) & (t <= tj + 0.08)
            st = an['st_mm'][lead]
            elev = lead in an['elevadas']
            ax.fill_between(t[sel], 0, y[sel], color='#e74c3c' if elev else '#95a5a6', alpha=0.35)
            ax.plot(tj, y[an['j']], 'o', color='#c0392b', ms=5)
            ax.set_title(f"{lead}: ST {st:+.1f} mm (umbral {an['umbral'][lead]:.1f})",
                         fontsize=10, color='#c0392b' if elev else '#333')
        else:
            ax.set_title(lead, fontsize=10)
    for ax in axes[len(derivaciones):]:
        ax.axis('off')
    plt.tight_layout()
    return fig


def graficar_anatomia(an, lead='V2', ancho=5.5):
    """Latido mediano anotado: onda P, segmento PR (línea de base), QRS, punto J, ST y onda T."""
    fs, med = an['fs'], an['med']
    i = LEADS.index(lead)
    t = (np.arange(len(med)) - an['r']) / fs
    y = med[:, i] - an['base'][i]
    x0, x1 = -0.22, 0.46
    y0 = float(np.clip(np.floor((y.min() - 0.2) * 2) / 2, -1.2, -0.5))
    y1 = float(np.clip(np.ceil((y.max() + 0.4) * 2) / 2, 1.0, 1.8))
    fig, ax = plt.subplots(figsize=(ancho, ancho * (y1 - y0) * 0.4 / (x1 - x0)))
    _papel(ax, x0, x1, y0, y1)
    ax.plot(t, y, color=_TRACE, lw=1.6)
    ax.axhline(0, color='#2471a3', ls='--', lw=1.2)
    to, tj = t[an['onset']], t[an['j']]
    ax.axvspan(to - 0.025, to - 0.005, color='#2471a3', alpha=0.15)
    ax.axvspan(to, tj, color='#f1c40f', alpha=0.15)
    ax.plot(tj, y[an['j']], 'o', color='#c0392b', ms=8)
    ax.annotate('', xy=(tj + 0.004, y[an['j']]), xytext=(tj + 0.004, 0),
                arrowprops=dict(arrowstyle='<->', color='#c0392b', lw=1.5))
    ax.text(x0 + 0.01, -0.45, 'Segmento PR = línea de base\n(línea azul punteada)',
            color='#2471a3', fontsize=10, ha='left')
    ax.text((to + tj) / 2, y1 - 0.25, 'QRS', ha='center', fontsize=10, color='#7d6608')
    ax.text(tj + 0.015, y[an['j']] + 0.15, f"Punto J\nST = {an['st_mm'][lead]:+.1f} mm",
            color='#c0392b', fontsize=10)
    ax.set_title(f'Anatomía del segmento ST — derivación {lead}', loc='left')
    plt.tight_layout()
    return fig
