# Entorno virtual · Reconocimiento de la elevación del segmento ST (Fase 1)

Clase interactiva en Google Colab para que estudiantes de medicina aprendan a **reconocer la elevación del segmento ST** con ECG reales de 12 derivaciones (base pública PTB-XL, PhysioNet). Fase 1: **solo elevación del ST**, enmarcada en el **Código Infarto** del IMSS (ECG en ≤ 10 min desde la llegada → ¿trazo compatible con IAM CEST? → activar); los imitadores y otros diagnósticos se excluyen a propósito.

| Cuaderno | Para | Qué hace |
|---|---|---|
| `clase_elevacion_ST.ipynb` | Alumnos | 6 módulos: Código Infarto → papel del ECG → anatomía del ST → taller de medición → umbrales y contigüidad → práctica deliberada con viñeta de Código Infarto, cronómetro y retroalimentación |
| `instructor_banco_casos.ipynb` | Profesor | Construye el banco de casos, permite verificar cada ECG y corregir el punto J, exporta `casos_st_verificados.csv` |

## Cómo usarlo
1. **Profesor:** abra `instructor_banco_casos.ipynb` en Colab → *Entorno de ejecución → Ejecutar todas* → verifique los casos → **Exportar CSV**.
2. Suba el CSV a este repositorio y copie su enlace *raw*.
3. **Alumnos:** abren `clase_elevacion_ST.ipynb`, pegan el enlace en el Paso 1 y ejecutan todo. Sin enlace, el cuaderno arma un banco provisional (no verificado) y lo advierte.

No requiere instalar nada; los ECG se descargan de PhysioNet al momento.

## Método
- **Criterio:** Quinta Definición Universal del Infarto (2026): elevación nueva en el punto J, sin bloqueo de rama ni HVI, en ≥ 2 derivaciones contiguas; ≥ 1 mm, excepto V2–V3 (≥ 2 mm hombres ≥ 40 años; ≥ 2.5 mm hombres < 40; ≥ 1.5 mm mujeres).
- **Señal:** filtrado de fase cero 0.05–40 Hz + muesca 50 Hz (preserva el ST); latido mediano; línea de base = segmento PR; punto J = fin del QRS por energía de pendiente en 12 derivaciones.
- **Contexto mexicano:** el cuaderno compara el criterio con la clasificación electrocardiográfica de RENASICA III (umbral único de 2 mm en V1–V3; elevación transitoria vs persistente).
- **Territorios (fase 1):** inferior (II, III, aVF), lateral (I, aVL, V5, V6), anterior (V1–V4); aVR no se evalúa.
- **Banco:** etiquetas de PTB-XL solo para enriquecer la búsqueda; se excluyen ruido, problemas de electrodos, marcapasos, bloqueos completos de rama, HVI y WPW. La clasificación final la verifica el instructor.

## Estructura
- `ecg_st_core.py` — carga, filtrado, mediciones, criterio y gráficas en papel de ECG (25 mm/s, 10 mm/mV).
- `ecg_st_ui.py` — banco de casos y widgets (taller, ejercicios, práctica, revisión del instructor).
- `build_nb.py` — genera los cuadernos (incrusta ambos módulos en la celda de preparación).
- `tests/` — ECG sintéticos para probar el código sin internet (no se usan en clase).

## Referencias
1. Mills NL, Newby LK, Zaman S, et al. Fifth Universal Definition of Myocardial Infarction (2026). *Circulation*. 2026. doi:10.1161/CIR.0000000000001477
2. Byrne RA, et al. 2023 ESC Guidelines for the management of acute coronary syndromes. *Eur Heart J*. 2023;44(38):3720–3826.
3. Instituto Mexicano del Seguro Social. Protocolo de Atención Integral de Código Infarto. Actualización. México: IMSS; octubre de 2025.
4. Jerjes-Sánchez C, Martínez-Sánchez C, Borrayo-Sánchez G, Carrillo-Calvillo J, Juárez-Herrera U, Quintanilla-Gutiérrez J. Third national registry of acute coronary syndromes (RENASICA III). *Arch Cardiol Mex*. 2015;85:207–214.
5. Wagner P, et al. PTB-XL, a large publicly available electrocardiography dataset. *Sci Data*. 2020;7:154.
6. Goldberger AL, et al. PhysioBank, PhysioToolkit, and PhysioNet. *Circulation*. 2000;101:e215–e220.
7. Kligfield P, et al. Recommendations for the standardization and interpretation of the electrocardiogram, part I. *Circulation*. 2007;115:1306–1324.

**Licencia:** texto CC BY 4.0; código MIT. Datos PTB-XL bajo CC BY 4.0.
**Advertencia:** material exclusivamente docente; no usar para decisiones clínicas.

*Elaborado con asistencia de IA (Claude, Anthropic); el autor revisó el contenido y es responsable de él.*
