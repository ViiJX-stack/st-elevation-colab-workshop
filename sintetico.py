"""Generador de ECG sintéticos SOLO para pruebas del código (no se usa en clase)."""
import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ecg_st_core import LEADS

def g(t, mu, sd, a):
    return a * np.exp(-0.5 * ((t - mu) / sd) ** 2)

R_AMP = dict(I=0.8, II=1.2, III=0.5, aVR=-0.9, aVL=0.4, aVF=0.8,
             V1=0.3, V2=0.6, V3=0.9, V4=1.4, V5=1.3, V6=1.0)
S_AMP = dict(I=-0.1, II=-0.15, III=-0.1, aVR=0.0, aVL=-0.1, aVF=-0.1,
             V1=-1.0, V2=-1.2, V3=-0.8, V4=-0.4, V5=-0.2, V6=-0.1)

def ecg(st_mm=None, fs=500, hr=72, seed=0, ruido=0.015, deriva=0.15):
    rng = np.random.default_rng(seed)
    st_mm = st_mm or {}
    n = 10 * fs
    t = np.arange(n) / fs
    rr = 60 / hr
    sig = np.zeros((n, 12))
    for k in range(int(10 / rr) + 2):
        r0 = 0.4 + k * rr + rng.normal(0, 0.01)
        for i, l in enumerate(LEADS):
            pol = -1 if l == 'aVR' else 1
            x = (g(t, r0 - 0.16, 0.02, 0.12 * pol) +
                 g(t, r0 - 0.025, 0.008, -0.08 * pol) +
                 g(t, r0, 0.011, R_AMP[l]) +
                 g(t, r0 + 0.028, 0.009, S_AMP[l]) +
                 g(t, r0 + 0.28, 0.05, 0.25 * pol))
            e = st_mm.get(l, 0) / 10.0
            if e:
                # plateau desde el punto J (~r0+0.045) que se funde con la T
                ramp = 1 / (1 + np.exp(-(t - (r0 + 0.040)) / 0.003))
                caida = 1 / (1 + np.exp((t - (r0 + 0.34)) / 0.03))
                x = x + e * ramp * caida
            sig[:, i] += x
    sig += rng.normal(0, ruido, sig.shape)
    sig += deriva * np.sin(2 * np.pi * 0.25 * t + rng.uniform(0, 6))[:, None]
    return sig, fs
