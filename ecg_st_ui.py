# -*- coding: utf-8 -*-
"""Banco de casos y entorno interactivo (ipywidgets) para la clase de elevación del ST."""
import io
import random
import time

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import ipywidgets as W
from IPython.display import display, clear_output, Markdown

from ecg_st_core import (LEADS, TERRITORIOS, cargar_registro, analizar, graficar_12,
                         graficar_latidos, criterio, umbrales, sexo_ptbxl, edad_ptbxl)

EXCLUIR_CODIGOS = {'CLBBB', 'ILBBB', 'CRBBB', 'LVH', 'WPW', 'PACE'}
COLUMNAS_RUIDO = ['baseline_drift', 'static_noise', 'burst_noise',
                  'electrodes_problems', 'pacemaker']


# ----------------------------------------------------------------------------
# Banco de casos
# ----------------------------------------------------------------------------
def candidatos(db, scp):
    """Selecciona candidatos a 'elevación del ST' y a 'control normal' en PTB-XL.

    La etiqueta de PTB-XL solo sirve para ENRIQUECER la búsqueda: la clasificación
    final la hace la medición en el punto J y, después, el instructor.
    """
    desc = scp['description'].astype(str).str.lower()
    cod_lesion = set(scp.index[desc.str.contains('injury') | (scp.index == 'STE_')])
    cod_im = set(scp.index[scp.get('diagnostic_class', pd.Series(index=scp.index)).astype(str) == 'MI'])

    limpio = pd.Series(True, index=db.index)
    for c in COLUMNAS_RUIDO:
        if c in db.columns:
            limpio &= db[c].isna()
    sin_excluir = db['scp_codes'].apply(lambda d: not (set(d) & EXCLUIR_CODIGOS))
    base = db[limpio & sin_excluir]

    lesion = base[base['scp_codes'].apply(lambda d: bool(set(d) & cod_lesion))]
    im = base[base['scp_codes'].apply(lambda d: bool(set(d) & cod_im)) & ~base.index.isin(lesion.index)]
    normal = base[base['scp_codes'].apply(
        lambda d: d.get('NORM', 0) >= 100 and set(d) <= {'NORM', 'SR'})]
    return lesion, im, normal


def _fila(ecg_id, r, an, grupo):
    fila = {'ecg_id': int(ecg_id), 'filename_hr': r['filename_hr'],
            'edad': edad_ptbxl(r.get('age')), 'sexo': sexo_ptbxl(r.get('sex')),
            'grupo': grupo, 'ajuste_J_ms': 0, 'verificado': False, 'comentario': '',
            'derivaciones_elevadas': ' '.join(an['elevadas']),
            'territorios': ' '.join(an['territorios']), 'qrs_ms': an['qrs_ms'],
            'ruido_base_mm': an['ruido_base_mm']}
    fila.update({f'st_{l}': an['st_mm'][l] for l in LEADS})
    return fila


def construir_banco(db, scp, n_ste=30, n_ctrl=30, semilla=2026, max_revisar=400, verbose=True):
    """Banco PROVISIONAL: casos donde la medición confirma >= 2 derivaciones contiguas
    elevadas y controles normales sin ninguna derivación por arriba de su umbral."""
    lesion, im, normal = candidatos(db, scp)
    rng = np.random.default_rng(semilla)
    pool_ste = list(rng.permutation(lesion.index)) + list(rng.permutation(im.index))
    pool_ctrl = list(rng.permutation(normal.index))
    filas, revisados = [], 0
    for grupo, pool, meta in (('STE', pool_ste, n_ste), ('Control', pool_ctrl, n_ctrl)):
        k = 0
        for ecg_id in pool:
            if k >= meta or revisados >= max_revisar:
                break
            revisados += 1
            r = db.loc[ecg_id]
            try:
                sig, fs = cargar_registro(r['filename_hr'])
                an = analizar(sig, fs, edad_ptbxl(r.get('age')), sexo_ptbxl(r.get('sex')))
            except Exception as e:  # registro dañado o error de red
                if verbose:
                    print('  omitido', ecg_id, type(e).__name__)
                continue
            if an is None or an['ruido_base_mm'] > 0.3 or not (60 <= an['qrs_ms'] <= 120):
                continue
            if grupo == 'STE' and not an['cumple']:
                continue
            if grupo == 'Control':
                margen = {l: an['umbral'][l] * 0.6 for l in LEADS}
                if any(an['st_mm'][l] >= margen[l] for l in LEADS if l != 'aVR'):
                    continue
            filas.append(_fila(ecg_id, r, an, grupo))
            k += 1
            if verbose:
                print(f'{grupo:8s} {k:3d}/{meta}  ecg_id={ecg_id}  {an["territorios"]}')
    banco = pd.DataFrame(filas)
    if verbose:
        print(f'\nRegistros revisados: {revisados}. Banco: {len(banco)} casos.')
    return banco


def cargar_banco(url=None, db=None, scp=None, n=12):
    """Banco verificado (CSV del instructor) o, si no hay, uno provisional pequeño."""
    if url:
        banco = pd.read_csv(url)
        if 'verificado' in banco.columns and banco['verificado'].any():
            banco = banco[banco['verificado']]
        banco = banco[banco['grupo'].isin(['STE', 'Control'])]
        display(Markdown(f'**Banco verificado por el instructor:** {len(banco)} casos.'))
        return banco.reset_index(drop=True)
    display(Markdown('⚠️ **Banco PROVISIONAL** (medición automática, sin verificación del instructor). '
                     'Construyendo... tarda 1–3 minutos.'))
    banco = construir_banco(db, scp, n_ste=n, n_ctrl=n, verbose=False)
    display(Markdown(f'Listo: {len(banco)} casos.'))
    return banco


def analizar_caso(fila):
    sig, fs = cargar_registro(fila['filename_hr'])
    edad = None if pd.isna(fila.get('edad')) else float(fila['edad'])
    sexo = fila.get('sexo') if isinstance(fila.get('sexo'), str) else None
    return analizar(sig, fs, edad, sexo, ajuste_J_ms=float(fila.get('ajuste_J_ms', 0) or 0))


def _paciente(fila):
    sexo = {'H': 'Hombre', 'M': 'Mujer'}.get(fila.get('sexo'), 'Sexo no registrado')
    edad = '' if pd.isna(fila.get('edad')) else f", {int(fila['edad'])} años"
    return sexo + edad


# ----------------------------------------------------------------------------
# Revisión del instructor
# ----------------------------------------------------------------------------
class RevisionInstructor:
    """Recorre el banco provisional: aceptar / rechazar / corregir el punto J."""

    def __init__(self, banco):
        self.b = banco.copy().reset_index(drop=True)
        self.i = 0
        self.out = W.Output()
        self.aj = W.IntSlider(value=0, min=-40, max=40, step=2, description='Ajuste J (ms)',
                              continuous_update=False, layout=W.Layout(width='420px'))
        self.grupo = W.ToggleButtons(options=['STE', 'Control', 'Excluir'], description='Clasificación')
        self.com = W.Text(description='Comentario', layout=W.Layout(width='600px'))
        b_ok = W.Button(description='Guardar y siguiente', button_style='success')
        b_ant = W.Button(description='◀ Anterior')
        b_exp = W.Button(description='Exportar CSV', button_style='info')
        self.estado = W.HTML()
        b_ok.on_click(self._guardar)
        b_ant.on_click(lambda _: self._ir(self.i - 1))
        b_exp.on_click(self._exportar)
        self.aj.observe(lambda _: self._mostrar(), names='value')
        display(W.VBox([self.estado, W.HBox([self.grupo, self.aj]), self.com,
                        W.HBox([b_ant, b_ok, b_exp]), self.out]))
        self._ir(0)

    def _ir(self, i):
        self.i = max(0, min(len(self.b) - 1, i))
        f = self.b.loc[self.i]
        self.aj.unobserve_all()
        self.aj.value = int(f['ajuste_J_ms'])
        self.aj.observe(lambda _: self._mostrar(), names='value')
        self.grupo.value = f['grupo'] if f['grupo'] in ('STE', 'Control') else 'Excluir'
        self.com.value = str(f['comentario']) if isinstance(f['comentario'], str) else ''
        self._mostrar()

    def _mostrar(self):
        f = self.b.loc[self.i].copy()
        f['ajuste_J_ms'] = self.aj.value
        an = analizar_caso(f)
        n_ver = int(self.b['verificado'].sum())
        self.estado.value = (f"<b>Caso {self.i + 1}/{len(self.b)}</b> · ecg_id {f['ecg_id']} · "
                             f"{_paciente(f)} · propuesta automática: <b>{self.b.loc[self.i, 'grupo']}</b> · "
                             f"verificados: {n_ver}")
        with self.out:
            clear_output(wait=True)
            graficar_12(an['senal'], an['fs'], f"ecg_id {f['ecg_id']} — {_paciente(f)}",
                        resaltar=an['elevadas'])
            plt.show()
            graficar_latidos(an)
            plt.show()
            print('Cumple criterio:', an['cumple'], '| Territorios:', an['territorios'],
                  '| QRS', an['qrs_ms'], 'ms | ruido basal', an['ruido_base_mm'], 'mm')
        self._an = an

    def _guardar(self, _):
        an = self._an
        self.b.loc[self.i, 'ajuste_J_ms'] = self.aj.value
        self.b.loc[self.i, 'grupo'] = self.grupo.value
        self.b.loc[self.i, 'comentario'] = self.com.value
        self.b.loc[self.i, 'verificado'] = self.grupo.value != 'Excluir'
        self.b.loc[self.i, 'derivaciones_elevadas'] = ' '.join(an['elevadas'])
        self.b.loc[self.i, 'territorios'] = ' '.join(an['territorios'])
        for l in LEADS:
            self.b.loc[self.i, f'st_{l}'] = an['st_mm'][l]
        if self.grupo.value == 'STE' and not an['cumple']:
            with self.out:
                print('⚠️ Marcó STE pero la medición no cumple el criterio; revise el punto J.')
        self._ir(self.i + 1)

    def _exportar(self, _):
        nombre = 'casos_st_verificados.csv'
        self.b.to_csv(nombre, index=False)
        with self.out:
            print(f'Guardado {nombre}: {int(self.b["verificado"].sum())} verificados de {len(self.b)}.')
        try:
            from google.colab import files
            files.download(nombre)
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Módulo: medir el ST en una derivación
# ----------------------------------------------------------------------------
class TallerMedicion:
    """El alumno ubica el punto J y estima el desnivel; el entorno compara con la referencia."""

    def __init__(self, banco):
        self.ste = banco[banco['grupo'] == 'STE'].reset_index(drop=True)
        self.out = W.Output()
        self.caso = W.Dropdown(options=[(f'Caso {k + 1}', k) for k in range(len(self.ste))],
                               description='ECG')
        self.lead = W.Dropdown(options=[l for l in LEADS if l != 'aVR'], value='V2',
                               description='Derivación')
        self.j = W.IntSlider(value=60, min=0, max=160, step=2, description='Punto J (ms tras R)',
                             style={'description_width': 'initial'}, continuous_update=False,
                             layout=W.Layout(width='480px'))
        self.mm = W.FloatText(value=0.0, step=0.5, description='Tu medida (mm)',
                              style={'description_width': 'initial'})
        b = W.Button(description='Comprobar', button_style='primary')
        b.on_click(self._comprobar)
        for w in (self.caso, self.lead):
            w.observe(lambda _: self._cargar(), names='value')
        self.j.observe(lambda _: self._dibujar(False), names='value')
        display(W.VBox([W.HBox([self.caso, self.lead]), self.j, W.HBox([self.mm, b]), self.out]))
        self._cargar()

    def _cargar(self):
        self.an = analizar_caso(self.ste.loc[self.caso.value])
        # Sugerir la derivación más elevada al cambiar de caso
        self._dibujar(False)

    def _dibujar(self, revelar):
        an, lead = self.an, self.lead.value
        i = LEADS.index(lead)
        fs, med = an['fs'], an['med']
        t = (np.arange(len(med)) - an['r']) / fs * 1000
        y = (med[:, i] - an['base'][i]) * 10  # en mm
        from ecg_st_core import _papel
        with self.out:
            clear_output(wait=True)
            fig, ax = plt.subplots(figsize=(7, 5.2))
            _papel(ax, -0.22, 0.46, -1.2, 1.8)
            ax.plot(t / 1000, y / 10, color='#111', lw=1.6)
            ax.axhline(0, color='#2471a3', ls='--', lw=1)
            jj = an['r'] + int(self.j.value * fs / 1000)
            ax.axvline(t[jj] / 1000, color='#8e44ad', lw=1.2)
            ax.plot(t[jj] / 1000, y[jj] / 10, 's', color='#8e44ad', ms=7, label='Tu punto J')
            if revelar:
                ax.axvline(t[an['j']] / 1000, color='#c0392b', ls=':', lw=1.5)
                ax.plot(t[an['j']] / 1000, y[an['j']] / 10, 'o', color='#c0392b', ms=8,
                        label='Punto J de referencia')
            ax.legend(loc='upper right', fontsize=9)
            ax.set_title(f'{lead} — {_paciente(self.ste.loc[self.caso.value])}', loc='left')
            plt.show()
            if revelar:
                ref = an['st_mm'][lead]
                tuyo = self.mm.value
                umb = an['umbral'][lead]
                dif_j = (jj - an['j']) * 1000 / fs
                ok_mm = abs(tuyo - ref) <= 0.5
                ok_j = abs(dif_j) <= 20
                display(Markdown(
                    f"- **Punto J:** {'✅' if ok_j else '❌'} el tuyo está a {dif_j:+.0f} ms del de referencia "
                    f"(tolerancia ±20 ms = medio cuadrito).\n"
                    f"- **Desnivel:** {'✅' if ok_mm else '❌'} tú: {tuyo:+.1f} mm · referencia: {ref:+.1f} mm "
                    f"(tolerancia ±0.5 mm).\n"
                    f"- **Umbral en {lead}** para este paciente: {umb:.1f} mm → "
                    f"{'**supera** el umbral' if ref >= umb else 'no supera el umbral'}."))

    def _comprobar(self, _):
        self._dibujar(True)


# ----------------------------------------------------------------------------
# Módulo: derivaciones contiguas
# ----------------------------------------------------------------------------
EJERCICIOS_CONTIGUAS = [
    (['II', 'aVF'], 'Sí — Inferior'),
    (['V2', 'V3'], 'Sí — Anterior'),
    (['III', 'V2'], 'No — no son contiguas'),
    (['I', 'aVL'], 'Sí — Lateral'),
    (['aVF'], 'No — solo una derivación'),
    (['V5', 'V6'], 'Sí — Lateral'),
    (['II', 'V4'], 'No — no son contiguas'),
]


def ejercicios_contiguas():
    opciones = ['Sí — Inferior', 'Sí — Anterior', 'Sí — Lateral',
                'No — no son contiguas', 'No — solo una derivación']
    cajas = []
    for k, (ls, resp) in enumerate(EJERCICIOS_CONTIGUAS):
        r = W.RadioButtons(options=opciones, value=None, layout=W.Layout(width='260px'))
        fb = W.HTML()

        def _cb(cambio, resp=resp, fb=fb):
            if cambio['new'] == resp:
                fb.value = '✅ Correcto'
            else:
                fb.value = f'❌ Respuesta: <b>{resp}</b>'
        r.observe(_cb, names='value')
        cajas.append(W.VBox([W.HTML(f'<b>{k + 1}.</b> ST elevado (por arriba del umbral) en: '
                                    f'<b>{", ".join(ls)}</b>'), r, fb],
                            layout=W.Layout(border='1px solid #ddd', padding='6px', margin='4px')))
    display(W.GridBox(cajas, layout=W.Layout(grid_template_columns='repeat(3, 330px)')))


# ----------------------------------------------------------------------------
# Módulo: práctica deliberada
# ----------------------------------------------------------------------------
VINETAS = [
    'dolor opresivo retroesternal de {h} h de evolución, irradiado al brazo izquierdo, con diaforesis',
    'dolor torácico opresivo de {h} h que inició en reposo',
    'malestar epigástrico, náusea y disnea de {h} h de evolución',
    'dolor en el pecho de {h} h que no cede con el reposo, acompañado de ansiedad',
    'sensación de ardor en el pecho de {h} h, irradiada a mandíbula',
]
DEC_SI = 'Sí: compatible con IAM CEST → activar Código Infarto'
DEC_NO = 'No: no cumple criterio → diagnóstico diferencial'


class Practica:
    """Casos aleatorios (50 % con elevación, 50 % normales) dentro de una viñeta de Código Infarto,
    con cronómetro de decisión y retroalimentación inmediata. Las viñetas son ficticias."""

    def __init__(self, banco, semilla=None):
        self.banco = banco.reset_index(drop=True)
        self.rng = random.Random(semilla)
        self.vistos = []
        self.marcador = {'n': 0, 'decision': 0, 'territorio': 0, 'meta': 0, 'tiempos': []}
        self.out_ecg, self.out_fb = W.Output(), W.Output()
        self.vineta = W.HTML()
        self.meta = W.ToggleButtons(options=['Sí, ≤ 10 min', 'No, > 10 min'], value=None,
                                    description='1) ¿Se cumplió la meta de ECG en ≤ 10 min?',
                                    style={'description_width': 'initial'})
        self.dec = W.RadioButtons(options=[DEC_SI, DEC_NO], value=None,
                                  description='2) ¿Trazo compatible con IAM CEST?',
                                  style={'description_width': 'initial'},
                                  layout=W.Layout(width='720px'))
        self.ders = {l: W.Checkbox(value=False, description=l, indent=False,
                                   layout=W.Layout(width='70px'))
                     for l in LEADS if l != 'aVR'}
        self.terr = {t: W.Checkbox(value=False, description=t, indent=False,
                                   layout=W.Layout(width='110px')) for t in TERRITORIOS}
        b_rev = W.Button(description='Revisar mi respuesta', button_style='primary')
        b_sig = W.Button(description='Siguiente caso ▶', button_style='success')
        b_rev.on_click(self._revisar)
        b_sig.on_click(lambda _: self._nuevo())
        self.score = W.HTML()
        panel = W.VBox([
            self.score, self.vineta, self.meta, self.out_ecg, self.dec,
            W.HTML('3) Derivaciones con ST elevado (marque las que superan su umbral):'),
            W.HBox(list(self.ders.values())),
            W.HTML('4) Territorio:'), W.HBox(list(self.terr.values())),
            W.HBox([b_rev, b_sig]), self.out_fb])
        display(panel)
        self._nuevo()

    def _elegir(self):
        grupo = 'STE' if self.rng.random() < 0.5 else 'Control'
        pool = [k for k in self.banco.index[self.banco['grupo'] == grupo] if k not in self.vistos]
        if not pool:
            pool = [k for k in self.banco.index if k not in self.vistos]
        if not pool:
            self.vistos = []
            pool = list(self.banco.index)
        k = self.rng.choice(pool)
        self.vistos.append(k)
        return k

    def _nuevo(self):
        self.k = self._elegir()
        self.fila = self.banco.loc[self.k]
        self.an = analizar_caso(self.fila)
        self.revisado = False
        self.dec.value = None
        self.meta.value = None
        h = self.rng.choice([1, 2, 3, 4, 6, 8, 10])
        self.min_ecg = self.rng.choice([3, 4, 6, 7, 9, 10, 12, 15, 18])
        texto = self.rng.choice(VINETAS).format(h=h)
        self.vineta.value = (
            f"<div style='border-left:4px solid #6a1b9a;padding:6px 10px;background:#f6effa;color:#222'>"
            f"<b>Urgencias · Código Infarto.</b> {_paciente(self.fila)}. Llega por {texto}. "
            f"El ECG de 12 derivaciones se tomó <b>{self.min_ecg} min</b> después de su llegada. "
            f"<i>(Viñeta ficticia con fines docentes.)</i></div>")
        for c in list(self.ders.values()) + list(self.terr.values()):
            c.value = False
        with self.out_fb:
            clear_output()
        with self.out_ecg:
            clear_output(wait=True)
            n = self.marcador['n'] + 1
            graficar_12(self.an['senal'], self.an['fs'], f'Caso {n} — {_paciente(self.fila)}')
            plt.show()
        self._marcador()
        self.t0 = time.time()

    def _marcador(self):
        m = self.marcador
        if m['n']:
            self.score.value = (f"<b>Casos revisados:</b> {m['n']} · <b>Decisión correcta:</b> "
                                f"{m['decision']}/{m['n']} ({100 * m['decision'] / m['n']:.0f} %) · "
                                f"<b>Territorio correcto:</b> {m['territorio']}/{m['n']} · "
                                f"<b>Meta ≤ 10 min:</b> {m['meta']}/{m['n']} · "
                                f"<b>Tiempo mediano para decidir:</b> {np.median(m['tiempos']):.0f} s")
        else:
            self.score.value = '<b>Práctica:</b> lea el ECG y responda.'

    def _revisar(self, _):
        if self.dec.value is None or self.meta.value is None:
            with self.out_fb:
                clear_output()
                print('Responda primero las preguntas 1 (meta de 10 min) y 2 (¿compatible con IAM CEST?).')
            return
        an, fila = self.an, self.fila
        verdad = fila['grupo'] == 'STE'
        ref_ders = set(an['elevadas']) - {'aVR'}
        ref_terr = set(an['territorios']) if verdad else set()
        suyo = self.dec.value == DEC_SI
        meta_ok = self.min_ecg <= 10
        ok_meta = (self.meta.value.startswith('Sí')) == meta_ok
        sus_ders = {l for l, c in self.ders.items() if c.value}
        sus_terr = {t for t, c in self.terr.items() if c.value}
        ok_dec = suyo == verdad
        ok_terr = sus_terr == ref_terr
        if not self.revisado:
            self.marcador['n'] += 1
            self.marcador['decision'] += int(ok_dec)
            self.marcador['territorio'] += int(ok_terr)
            self.marcador['meta'] += int(ok_meta)
            self.marcador['tiempos'].append(time.time() - self.t0)
            self.revisado = True
        self._marcador()
        aciertos = sorted(sus_ders & ref_ders, key=LEADS.index)
        omitidas = sorted(ref_ders - sus_ders, key=LEADS.index)
        sobran = sorted(sus_ders - ref_ders, key=LEADS.index)
        u = an['umbral']
        with self.out_fb:
            clear_output(wait=True)
            seg = self.marcador['tiempos'][-1]
            accion = ('**Activar Código Infarto** y establecer el "tiempo 0"' if verdad
                      else 'No activar por ECG; continuar **diagnóstico diferencial** (repetir ECG si persiste el dolor)')
            display(Markdown(
                f"### {'✅' if ok_dec else '❌'} Este ECG **{'sí' if verdad else 'no'}** cumple el criterio "
                f"de elevación del ST → {accion}\n"
                f"- Meta de ECG ≤ 10 min: {'✅' if ok_meta else '❌'} el ECG se tomó a los {self.min_ecg} min "
                f"({'meta cumplida' if meta_ok else 'meta NO cumplida'}). · Su tiempo de decisión: {seg:.0f} s\n"
                f"- Umbrales para este paciente ({_paciente(fila)}): V2–V3 ≥ {u['V2']:.1f} mm; "
                f"resto ≥ 1.0 mm, en ≥ 2 derivaciones contiguas.\n"
                f"- Derivaciones con ST elevado (referencia): **{', '.join(sorted(ref_ders, key=LEADS.index)) or 'ninguna'}**\n"
                f"- Bien identificadas: {', '.join(aciertos) or '—'} · Omitidas: {', '.join(omitidas) or '—'} · "
                f"Marcadas de más: {', '.join(sobran) or '—'}\n"
                f"- Territorio: {'✅' if ok_terr else '❌'} referencia: **{', '.join(sorted(ref_terr)) or 'ninguno'}**"))
            graficar_12(an['senal'], an['fs'], 'Derivaciones con ST elevado en rojo',
                        resaltar=ref_ders)
            plt.show()
            display(Markdown('**Latido mediano por derivación** (línea azul = segmento PR; punto rojo = '
                             'punto J; sombra = desnivel del ST):'))
            graficar_latidos(an)
            plt.show()
