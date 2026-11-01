"""Genera los dos cuadernos de Colab a partir de los módulos fuente."""
import nbformat as nbf

CORE = open('ecg_st_core.py', encoding='utf-8').read()
UI = open('ecg_st_ui.py', encoding='utf-8').read()

AUTOR = 'Víctor Junior Godínez-Vázquez'


def md(t):
    return nbf.v4.new_markdown_cell(t.strip())


def form(code):
    c = nbf.v4.new_code_cell(code.strip())
    c.metadata['cellView'] = 'form'
    return c


SETUP = f'''
#@title ⚙️ Paso 0 · Preparar el entorno (ejecute y espere ~30 s)
import os, sys, importlib, warnings
warnings.filterwarnings('ignore')
try:
    import wfdb
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', '-q', 'install', 'wfdb'], check=True)
_FUENTES = {{'ecg_st_core.py': {CORE!r},
            'ecg_st_ui.py': {UI!r}}}
for _n, _s in _FUENTES.items():
    with open(_n, 'w', encoding='utf-8') as _f:
        _f.write(_s)
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())
import ecg_st_core, ecg_st_ui
importlib.reload(ecg_st_core); importlib.reload(ecg_st_ui)
from ecg_st_core import *
from ecg_st_ui import *
if os.environ.get('ECG_ST_PRUEBA'):  # solo para pruebas del autor sin internet
    sys.path.insert(0, os.environ['ECG_ST_PRUEBA'])
    import prueba_mock; prueba_mock.parchar(globals())
print('Entorno listo.')
'''

LIC = f'''
---
**Autor:** {AUTOR} · Material docente · Texto CC BY 4.0 · Código MIT
**Datos:** PTB-XL v1.0.3 (PhysioNet, CC BY 4.0). Wagner P, et al. *Sci Data* 2020;7:154.
**Advertencia:** material exclusivamente docente; no usar para decisiones clínicas.
*Elaborado con asistencia de IA (Claude, Anthropic); el autor revisó el contenido y es responsable de él.*
'''

# ============================================================================
# CUADERNO DEL ALUMNO
# ============================================================================
al = nbf.v4.new_notebook()
al.cells = [
md(f'''
# Entorno virtual · Reconocimiento de la elevación del segmento ST
### Fase 1 — solo elevación del ST

**Contexto: Código Infarto (IMSS).** Ante una persona con dolor en el pecho de menos de 12 h de evolución,
el ECG de 12 derivaciones debe tomarse **en los primeros 10 minutos** de su llegada y leerse de inmediato:
si el trazo es compatible con **IAM con elevación del ST (IAM CEST)**, se establece el "tiempo 0" y se activa el
Código Infarto. Este entorno entrena exactamente ese paso: **reconocer la elevación del ST con rapidez y precisión**.

**Objetivos de aprendizaje.** Al terminar, usted podrá:
0. Ubicar el reconocimiento del ECG dentro del algoritmo del Código Infarto (meta: ECG en ≤ 10 min).
1. Identificar la **línea de base** (segmento PR) de cada derivación.
2. Ubicar el **punto J** (final del QRS).
3. Medir el **desnivel del ST en milímetros** y compararlo con el umbral que corresponde al paciente.
4. Decidir si hay elevación del ST en **≥ 2 derivaciones contiguas** y nombrar el **territorio**.

**Cómo usarlo.** No necesita programar. Menú **Entorno de ejecución → Ejecutar todas** (o `Ctrl + F9`).
Después baje por el cuaderno y trabaje cada módulo en orden. Los ECG son **reales** (base pública PTB-XL).
{LIC}
'''),
form(SETUP),
form('''
#@title 📂 Paso 1 · Cargar los ECG de la clase
#@markdown Si su profesor le dio un enlace al banco de casos, péguelo aquí; si no, deje vacío.
URL_BANCO = ""  #@param {type:"string"}
db, scp = cargar_metadatos()
banco = cargar_banco(URL_BANCO or None, db, scp, n=12)
'''),
md('''
## Módulo 0 · Código Infarto: dónde encaja lo que va a aprender

```
Persona con dolor en el pecho < 12 h
        │
        ▼
ECG de 12 derivaciones en ≤ 10 min desde la llegada   ← primer contacto (urgencias / atención médica continua)
        │
        ▼
¿Trazo compatible con IAM CEST?  ──── No ───►  Diagnóstico diferencial (repetir ECG si persiste el dolor)
        │ Sí
        ▼
Confirmar IAM CEST · "tiempo 0" · ACTIVAR CÓDIGO INFARTO
        │
        ▼
Reperfusión: ICP primaria (< 90 min, si hay hemodinamia en < 2 h) o fibrinólisis (< 30 min)
```

El rombo **"¿Trazo compatible con IAM CEST?"** es la decisión que usted va a entrenar. Cada minuto de retraso en
reconocer la elevación del ST es miocardio perdido; por eso la práctica (Módulo 5) mide también **su tiempo de
decisión** y le pide verificar si se cumplió la **meta de 10 minutos**.

*Esquema simplificado del Protocolo de Atención Integral Código Infarto del IMSS; consulte la versión vigente de
su institución para tiempos y criterios de reperfusión.*
'''),
md('''
## Módulo 1 · El papel del ECG

| En el papel | Equivale a |
|---|---|
| 1 cuadrito (1 mm) horizontal | **0.04 s** |
| 1 cuadro grande (5 mm) horizontal | **0.20 s** |
| 1 cuadrito (1 mm) vertical | **0.1 mV** |
| Pulso de calibración (10 mm de alto) | **1 mV** |

La velocidad estándar es **25 mm/s** y la ganancia **10 mm/mV**. **Antes de medir cualquier cosa, verifique
el pulso de calibración** (el rectángulo al inicio de cada renglón): si no mide 10 mm, todas sus medidas del ST
estarán equivocadas.

En este entorno, **1 mm de elevación del ST = 1 cuadrito vertical.**
'''),
form('''
#@title 👀 Observe un ECG de 12 derivaciones
_f = banco[banco['grupo'] == 'STE'].iloc[0]
_an1 = analizar_caso(_f)
graficar_12(_an1['senal'], _an1['fs'], 'ECG de ejemplo — observe el pulso de calibración y el formato 3 × 4')
plt.show()
'''),
md('''
## Módulo 2 · Anatomía del segmento ST

Tres puntos de referencia, siempre en este orden:

1. **Línea de base (isoeléctrica):** el **segmento PR**, entre el final de la onda P y el inicio del QRS.
   Es el "cero" contra el que se mide.
2. **Punto J:** donde **termina el QRS** y comienza el segmento ST (el cambio brusco de pendiente).
3. **Desnivel del ST:** la **distancia vertical entre el punto J y la línea de base**, en milímetros.
   Por arriba = elevación; por abajo = depresión.

> La Quinta Definición Universal del Infarto (2026) mide la elevación **en el punto J**.
'''),
form('''
#@title 🔬 Latido anotado (derivación con mayor elevación del ejemplo)
_lead = max([l for l in LEADS if l != 'aVR'], key=lambda l: _an1['st_mm'][l])
graficar_anatomia(_an1, _lead)
plt.show()
'''),
md('''
## Módulo 3 · Taller de medición

Ahora mida usted. Para cada derivación:
1. Mueva el control **Punto J** hasta donde termina el QRS (línea morada).
2. Cuente los cuadritos entre el punto J y la línea azul punteada (segmento PR) y escriba su medida.
3. Pulse **Comprobar**: verá el punto J de referencia (rojo) y la medida correcta.

Tolerancia: ±20 ms para el punto J y ±0.5 mm para el desnivel. Practique al menos 5 derivaciones de casos distintos.
'''),
form('''
#@title 📏 Taller de medición
taller = TallerMedicion(banco)
'''),
md('''
## Módulo 4 · Umbrales y derivaciones contiguas

**Criterio de IAM CEST** (Quinta Definición Universal del Infarto, ESC/ACC/AHA/WHF, 2026): elevación **nueva** del ST
en el punto J en **≥ 2 derivaciones contiguas**, **en ausencia de bloqueo de rama y/o hipertrofia ventricular
izquierda**, con estos umbrales:

| Derivaciones | Paciente | Umbral |
|---|---|---|
| **V2 y V3** | Hombre ≥ 40 años | ≥ **2.0 mm** |
| **V2 y V3** | Hombre < 40 años | ≥ **2.5 mm** |
| **V2 y V3** | Mujer (cualquier edad) | ≥ **1.5 mm** |
| **Todas las demás** | Cualquiera | ≥ **1.0 mm** |

**Además**, la elevación debe estar en **al menos 2 derivaciones contiguas** (que miran la misma región del corazón):

| Territorio | Derivaciones |
|---|---|
| **Inferior** | II, III, aVF |
| **Lateral** | I, aVL, V5, V6 |
| **Anterior** | V1, V2, V3, V4 |

Una sola derivación elevada **no** cumple el criterio. Dos derivaciones elevadas de territorios distintos
(p. ej., III y V2) **tampoco**. En esta fase **no evaluamos aVR**.

**"Nueva"** significa que no estaba en un ECG previo. Con un solo trazo no se puede saber; en la práctica clínica,
ante un paciente con síntomas, una elevación que cumple el criterio se trata como nueva hasta demostrar lo
contrario (compare con ECG previos cuando existan, sin retrasar la activación).
'''),
form('''
#@title ✏️ Ejercicios: ¿cumple el criterio de contigüidad?
ejercicios_contiguas()
'''),
md('''
## Módulo 5 · Práctica deliberada

Aquí aprende de verdad: muchos casos, respuesta inmediata. Cada caso llega como en urgencias, con una viñeta
breve (ficticia) de Código Infarto. Primero verifique si se cumplió la meta de **ECG en ≤ 10 min**; luego lea el
trazo. El cronómetro corre desde que aparece el ECG. Para cada ECG siga **siempre** los mismos 4 pasos:

1. **Calibración:** ¿10 mm = 1 mV?
2. **Línea de base y punto J** en cada derivación.
3. **Mida y compare** con el umbral del paciente (¡fíjese en el sexo y la edad para V2–V3!).
4. **Contigüidad:** ¿≥ 2 derivaciones del mismo territorio?

Responda, pulse **Revisar mi respuesta**, estudie la retroalimentación (latido mediano de cada derivación)
y pase al **Siguiente caso**. Aproximadamente la mitad de los casos tienen elevación del ST y la otra mitad son normales.
Meta sugerida: **20 casos** con ≥ 85 % de decisiones correctas. La rapidez importa, pero **primero la exactitud**:
un falso negativo retrasa la reperfusión y un falso positivo moviliza al equipo sin necesidad.
'''),
form('''
#@title 🫀 Práctica
practica = Practica(banco)
'''),
md(f'''
## Cierre

**Algoritmo de 4 pasos:** calibración → línea de base y punto J → medir contra el umbral del paciente → ≥ 2 contiguas.

**Lo que esta fase NO cubre** (no generalice todavía). Estos casos se excluyeron del banco a propósito y se
abordarán en fases posteriores:
- **Imitadores** de la elevación del ST: repolarización precoz, pericarditis, hipertrofia ventricular izquierda.
- **Bloqueo de rama y marcapasos:** BRIHH/BRDHH nuevo o presumiblemente nuevo con signos de isquemia; criterios de
  Sgarbossa y Sgarbossa modificados (razón ST/S ≤ 0.25).
- **Infarto posterior** (depresión del ST ≥ 1 mm en V1–V3 con R dominante, confirmado con elevación en V7–V9) y
  **de ventrículo derecho** (elevación en V3R–V6R). En sospecha de IAM CEST inferior, tome V3R–V4R y V7–V9.
- **Equivalentes de oclusión coronaria aguda** que reconoce la Quinta Definición Universal sin elevación clásica:
  ondas T hiperagudas, patrón de De Winter, síndrome de Wellens, patrón de Aslanger, signo de la "bandera
  sudafricana", y elevación en aVR.

Recuerde que hasta 1 de cada 4 pacientes tratados como IAM sin elevación del ST tiene una arteria ocluida: un ECG
que **no** cumple el criterio no descarta oclusión coronaria aguda.

**Recuerde:** el diagnóstico de infarto es clínico + ECG + biomarcadores, pero **la activación del Código Infarto
no espera a los biomarcadores**: un ECG que cumple el criterio en un paciente con síntomas exige activarlo sin
demora.

### Referencias
1. Mills NL, Newby LK, Zaman S, et al. Fifth Universal Definition of Myocardial Infarction (2026). *Circulation*. 2026.
   doi:10.1161/CIR.0000000000001477
2. Byrne RA, et al. 2023 ESC Guidelines for the management of acute coronary syndromes. *Eur Heart J*.
   2023;44(38):3720–3826.
3. Instituto Mexicano del Seguro Social. Protocolo de Atención Integral: Código Infarto.
4. Wagner P, et al. PTB-XL, a large publicly available electrocardiography dataset. *Sci Data*. 2020;7:154.
5. Goldberger AL, et al. PhysioBank, PhysioToolkit, and PhysioNet. *Circulation*. 2000;101:e215–e220.
6. Kligfield P, et al. Recommendations for the standardization and interpretation of the electrocardiogram, part I.
   *Circulation*. 2007;115:1306–1324.
{LIC}
'''),
]

# ============================================================================
# CUADERNO DEL INSTRUCTOR
# ============================================================================
ins = nbf.v4.new_notebook()
ins.cells = [
md(f'''
# Instructor · Banco de casos verificados para la clase de elevación del ST

Este cuaderno **no es para los alumnos**. Construye el banco de ECG que usa el entorno virtual.

**Procedimiento (rigor del estándar de referencia):**
1. Se buscan candidatos en PTB-XL usando sus etiquetas solo para **enriquecer** la búsqueda
   (declaraciones de lesión/infarto para casos; NORM puro para controles). Se excluyen registros con ruido,
   problemas de electrodos, marcapasos, BRIHH/BRDHH completos, HVI y WPW.
2. El algoritmo mide el ST en el punto J (latido mediano, filtrado de fase cero 0.05–40 Hz) y conserva:
   - **Casos:** ≥ 2 derivaciones contiguas por arriba del umbral de la Quinta Definición Universal (2026).
   - **Controles:** ninguna derivación por arriba del 60 % de su umbral (normales inequívocos).
3. **Usted verifica cada caso** (aceptar como STE / Control, o excluir) y corrige el punto J si hace falta.
   Solo los casos verificados llegan a los alumnos.
4. Exporte el CSV, súbalo a su GitHub y pegue el enlace *raw* en el Paso 1 del cuaderno del alumno.

> Recomendado: que un segundo médico verifique de forma independiente y reportar la concordancia.
{LIC}
'''),
form(SETUP),
form('''
#@title 📂 Cargar metadatos de PTB-XL y contar candidatos
db, scp = cargar_metadatos()
lesion, im, normal = candidatos(db, scp)
print(f'Registros en PTB-XL: {len(db)}')
print(f'Candidatos con declaración de lesión/STE: {len(lesion)}')
print(f'Candidatos adicionales con declaración de infarto: {len(im)}')
print(f'Controles normales puros: {len(normal)}')
'''),
form('''
#@title 🏗️ Construir banco provisional (5–15 min según tamaño)
N_CASOS = 30  #@param {type:"integer"}
N_CONTROLES = 30  #@param {type:"integer"}
SEMILLA = 2026  #@param {type:"integer"}
banco_prov = construir_banco(db, scp, n_ste=N_CASOS, n_ctrl=N_CONTROLES, semilla=SEMILLA,
                             max_revisar=20 * (N_CASOS + N_CONTROLES))
banco_prov.to_csv('casos_st_provisional.csv', index=False)
banco_prov.groupby('grupo').size()
'''),
md('''
## Verificación caso por caso
Para cada ECG: revise el trazo y los latidos medianos; corrija el punto J con el control si no coincide con el final
del QRS (las medidas se recalculan); elija **STE**, **Control** o **Excluir**; pulse **Guardar y siguiente**.
Al terminar, pulse **Exportar CSV**.
'''),
form('''
#@title ✅ Revisión del instructor
revision = RevisionInstructor(banco_prov)
'''),
form('''
#@title 📊 Resumen del banco verificado
b = revision.b
print(b[b['verificado']].groupby('grupo').size())
print('\\nTerritorios (casos STE):')
print(b[b['verificado'] & (b['grupo'] == 'STE')]['territorios'].value_counts())
'''),
]

for nb, nombre in ((al, 'clase_elevacion_ST.ipynb'), (ins, 'instructor_banco_casos.ipynb')):
    nb.metadata['colab'] = {'provenance': [], 'toc_visible': True}
    nb.metadata['kernelspec'] = {'name': 'python3', 'display_name': 'Python 3'}
    nb.metadata['language_info'] = {'name': 'python'}
    nbf.write(nb, nombre)
    print('escrito', nombre)
