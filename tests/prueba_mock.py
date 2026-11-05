"""Sustituye PhysioNet por ECG sintéticos para probar los cuadernos sin internet."""
import os, sys
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from sintetico import ecg

PATRONES = [
    {'V1': 2, 'V2': 3.5, 'V3': 3.5, 'V4': 2.5},
    {'II': 2.2, 'III': 2.8, 'aVF': 2.5, 'aVL': -1.0},
    {'I': 1.6, 'aVL': 2.0, 'V5': 1.5, 'V6': 1.4},
    {'V2': 2.5, 'V3': 3, 'V4': 3, 'V5': 2},
]


def metadatos():
    filas = []
    for k in range(1, 61):
        if k <= 24:
            codes = {'INJAS': 100.0, 'SR': 0.0}
        elif k <= 28:
            codes = {'INJAS': 100.0, 'CLBBB': 100.0}
        else:
            codes = {'NORM': 100.0, 'SR': 0.0}
        filas.append({'ecg_id': k, 'filename_hr': f'records500/00000/{k:05d}_hr',
                      'age': 30 + (k * 7) % 55, 'sex': k % 2, 'scp_codes': codes,
                      'baseline_drift': np.nan, 'static_noise': np.nan, 'burst_noise': np.nan,
                      'electrodes_problems': np.nan, 'pacemaker': np.nan})
    db = pd.DataFrame(filas).set_index('ecg_id')
    scp = pd.DataFrame({'description': ['subendocardial injury in anteroseptal leads', 'normal ECG',
                                        'sinus rhythm', 'complete left bundle branch block'],
                        'diagnostic_class': ['MI', 'NORM', np.nan, 'CD']},
                       index=['INJAS', 'NORM', 'SR', 'CLBBB'])
    return db, scp


def registro(filename_hr):
    k = int(filename_hr[-8:-3])
    st = PATRONES[k % 4] if k <= 28 else {}
    return ecg(st, seed=k, hr=60 + (k * 3) % 40)


def parchar(ns):
    import ecg_st_core, ecg_st_ui
    ecg_st_core.cargar_metadatos = metadatos
    ecg_st_core.cargar_registro = registro
    ecg_st_ui.cargar_registro = registro
    ns['cargar_metadatos'] = metadatos
    ns['cargar_registro'] = registro
