# Documentación Técnica: Simulador de Estación de Peaje

Este documento explica en detalle cómo el código fuente `simulador_peaje.py` modela matemáticamente y lógicamente el caso de estudio del Trabajo Práctico.

## 1. Importación de Librerías
```python
import simpy
import random
import numpy as np
from scipy import stats
```
- **`simpy`**: Es el motor principal de la simulación de eventos discretos. Maneja el reloj virtual (`env.now`) y los recursos (las cabinas).
- **`random`**: Genera los números pseudoaleatorios para los tiempos de servicio y los intervalos de llegada.
- **`numpy` / `scipy`**: Se utilizan al finalizar las simulaciones para procesar los arreglos de datos (tiempos de espera) y calcular la media y el Intervalo de Confianza al 95%.

---

## 2. Configuración y Tiempos (`PeajeConfig` y `tiempo_servicio`)
```python
class PeajeConfig:
    LLEGADAS = {
        'gran_porte': {'pico': 60.0, 'no_pico': 120.0},
        ...
    }

def tiempo_servicio(tipo):
    if tipo == 'gran_porte': return random.uniform(45.0, 55.0)
    ...
```
- **Mapeo del TP**: Representa las tasas de llegada y tiempos de servicio provistos en el PDF.
- **Detalle de Llegadas**: El diccionario guarda los segundos entre llegadas (distribución exponencial). *Nota: Los tiempos del PDF se multiplicaron por 2, asumiendo que el flujo enunciado es el total de la autovía y se reparte 50/50 entre la estación Ascendente y Descendente, evitando un colapso matemático irreal.*
- **Distribuciones**: Se implementaron exactamente como lo pide el PDF: `random.uniform` (Uniforme), `random.expovariate` (Exponencial) y `random.triangular` (Triangular).

---

## 3. Infraestructura (`class Estacion`)
```python
class Estacion:
    def __init__(self, env, nombre):
        self.cabinas = [simpy.Resource(env, capacity=1) for _ in range(3)]
        self.cabinas_base = 1
        self.cabinas_extra_activas = 0
```
- **Mapeo del TP**: *"Hay dos estaciones (A y D) y en cada una de ellas hay tres cabinas"*.
- Las cabinas son instancias separadas de `simpy.Resource`. Esto permite que se abran o se cierren independientemente, y que los vehículos puedan "ver" qué cola está más corta.

---

## 4. Control de Horarios Base (`gestor_horario_base`)
```python
def gestor_horario_base(env, estacion):
    # Lógica para A (7 a 9) y D (19 a 20)
```
- **Mapeo del TP**: *"Se utiliza solamente una (cabina) en todo el día y dos de 7 a 9 en A y 19 a 20 en D"*.
- **Funcionamiento**: Este proceso corre en paralelo (como un reloj). Cuando la hora virtual (`env.now`) entra en horario pico, cambia `cabinas_base = 2`. Al terminar la hora pico, la devuelve a 1.

---

## 5. El Supervisor Dinámico (`supervisor_dinamico`)
```python
def supervisor_dinamico(env, estacion, costo_list):
    ...
    if espera_media > 180.0 and estacion.cabinas_activas < 3:
        estacion.cabinas_extra_activas = 1
        costo_list.append(100)
        yield env.timeout(10.0 * 60)
```
- **Mapeo del TP**: *"Se sabe que habilitar una cabina extra (la tercera) le cuesta al concesionario 100 $/10 minutos ... y solo puede hacerlo en lapsos de tiempo no inferiores a 10 minutos"*.
- **Funcionamiento**:
  1. Se despierta cada 10 minutos virtuales.
  2. Calcula el promedio de espera de los autos que cruzaron en esos últimos 10 minutos.
  3. Si la media superó los 180 segundos (3 minutos), habilita temporalmente una cabina extra (`cabinas_extra_activas = 1`) y registra un gasto de $100.
  4. La mantiene abierta por 10 minutos exactos y luego vuelve a evaluar.

---

## 6. Lógica del Vehículo (`vehiculo`)
```python
abiertas = estacion.cabinas[:estacion.cabinas_activas]
mejor_cabina = min(abiertas, key=lambda c: len(c.queue))

with mejor_cabina.request() as req:
    yield req
    espera = env.now - llegada
    stats_list.append(espera)
```
- **Comportamiento Racional**: El auto no va a una cabina al azar; evalúa cuáles están abiertas y elige matemáticamente la que tiene la cola más corta (`len(c.queue)`).
- **Recolección de Datos**: Una vez que llega su turno, calcula cuánto esperó (`env.now - llegada`) y lo guarda en las listas de estadísticas para poder saber al final del día quién superó los 3 minutos y quién no.

---

## 7. Motor Estadístico (`main`)
```python
ic_base = stats.t.interval(0.95, df=n_replicas-1, loc=media_base, scale=stats.sem(res_base))
```
- **Mapeo del TP**: *"Demuestre su respuesta con un grado de confianza del 95%"*.
- **Funcionamiento**: Ejecuta la simulación entera dos veces por cada réplica (Escenario con Supervisor apagado vs. Supervisor encendido). Almacena los resultados y utiliza la distribución T de Student (`stats.t.interval`) para generar el margen de error estadísticamente válido al 95%.
- Finalmente, compara el gasto en dólares del supervisor versus la cantidad de multas que logró evitar para calcular la **Multa de Equilibrio**.
