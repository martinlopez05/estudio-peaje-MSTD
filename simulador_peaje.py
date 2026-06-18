import simpy
import random
import numpy as np
from scipy import stats

# Constantes de tiempo
DIA_EN_SEGUNDOS = 24 * 3600

class PeajeConfig:
    LLEGADAS = {
        'gran_porte': {'pico': 60.0, 'no_pico': 120.0},
        'grandes': {'pico': 80.0, 'no_pico': 140.0},
        'pequenos': {'pico': 50.0, 'no_pico': 80.0},
        'motos': {'pico': 760.0, 'no_pico': 760.0}
    }

def tiempo_servicio(tipo):
    if tipo == 'gran_porte':
        return random.uniform(45.0, 55.0)
    elif tipo in ['grandes', 'motos']:
        return random.expovariate(1.0 / 30.0)
    elif tipo == 'pequenos':
        return random.triangular(15.0, 35.0, 20.0)
    return 0.0

class Estacion:
    def __init__(self, env, nombre):
        self.env = env
        self.nombre = nombre
        self.cabinas = [simpy.Resource(env, capacity=1) for _ in range(3)]
        self.cabinas_base = 1
        self.cabinas_extra_activas = 0
        
        self.vehiculos_atendidos_recientes = []

    @property
    def cabinas_activas(self):
        return min(3, self.cabinas_base + self.cabinas_extra_activas)

def gestor_horario_base(env, estacion):
    while True:
        hora_actual = (env.now % DIA_EN_SEGUNDOS) / 3600.0
        if estacion.nombre == 'A':
            if 7.0 <= hora_actual < 9.0:
                estacion.cabinas_base = 2
                yield env.timeout((9.0 - hora_actual) * 3600)
            else:
                estacion.cabinas_base = 1
                next_event = 7.0 if hora_actual < 7.0 else 24.0 + 7.0
                yield env.timeout((next_event - hora_actual) * 3600)
        elif estacion.nombre == 'D':
            if 19.0 <= hora_actual < 20.0:
                estacion.cabinas_base = 2
                yield env.timeout((20.0 - hora_actual) * 3600)
            else:
                estacion.cabinas_base = 1
                next_event = 19.0 if hora_actual < 19.0 else 24.0 + 19.0
                yield env.timeout((next_event - hora_actual) * 3600)

def supervisor_dinamico(env, estacion, costo_list):
    """
    Cada 10 minutos evalúa la espera media de los vehículos recientes.
    Si supera los 180s (3 min), abre una cabina extra por 10 minutos (si hay disponibles).
    """
    while True:
        # Evaluar espera media de los últimos 10 minutos
        espera_media = 0.0
        if estacion.vehiculos_atendidos_recientes:
            espera_media = np.mean(estacion.vehiculos_atendidos_recientes)
        
        # Limpiamos para el próximo intervalo
        estacion.vehiculos_atendidos_recientes = []
        
        if espera_media > 180.0 and estacion.cabinas_activas < 3:
            # Habilitar cabina extra
            estacion.cabinas_extra_activas = 1
            costo_list.append(100) # $100 por 10 mins
            yield env.timeout(10.0 * 60)
            # Deshabilitar cabina extra
            estacion.cabinas_extra_activas = 0
        else:
            yield env.timeout(10.0 * 60)

def generador_vehiculos(env, estacion, tipo, stats_list):
    while True:
        hora_actual = (env.now % DIA_EN_SEGUNDOS) / 3600.0
        pico = False
        if estacion.nombre == 'A' and 7.0 <= hora_actual < 9.0:
            pico = True
        elif estacion.nombre == 'D' and 19.0 <= hora_actual < 20.0:
            pico = True
            
        estado = 'pico' if pico else 'no_pico'
        tasa = PeajeConfig.LLEGADAS[tipo][estado]
        
        yield env.timeout(random.expovariate(1.0 / tasa))
        env.process(vehiculo(env, estacion, tipo, stats_list))

def vehiculo(env, estacion, tipo, stats_list):
    llegada = env.now
    
    abiertas = estacion.cabinas[:estacion.cabinas_activas]
    mejor_cabina = min(abiertas, key=lambda c: len(c.queue))
    
    with mejor_cabina.request() as req:
        yield req
        espera = env.now - llegada
        stats_list.append(espera)
        estacion.vehiculos_atendidos_recientes.append(espera)
        
        yield env.timeout(tiempo_servicio(tipo))

def correr_simulacion(escenario_dinamico):
    env = simpy.Environment()
    
    estacion_a = Estacion(env, 'A')
    estacion_d = Estacion(env, 'D')
    
    env.process(gestor_horario_base(env, estacion_a))
    env.process(gestor_horario_base(env, estacion_d))
    
    costos_extra_a = []
    costos_extra_d = []
    
    if escenario_dinamico:
        env.process(supervisor_dinamico(env, estacion_a, costos_extra_a))
        env.process(supervisor_dinamico(env, estacion_d, costos_extra_d))
    
    stats_a = []
    stats_d = []
    
    for tipo in PeajeConfig.LLEGADAS.keys():
        env.process(generador_vehiculos(env, estacion_a, tipo, stats_a))
        env.process(generador_vehiculos(env, estacion_d, tipo, stats_d))
        
    env.run(until=DIA_EN_SEGUNDOS)
    
    esperas_a = np.array(stats_a)
    esperas_d = np.array(stats_d)
    
    multados = np.sum(esperas_a > 180) + np.sum(esperas_d > 180)
    costo_total = sum(costos_extra_a) + sum(costos_extra_d)
    
    return multados, costo_total

def main():
    print("Iniciando simulacion de Peaje (30 replicas por escenario)...")
    n_replicas = 30
    
    res_base = []
    res_dinamico = []
    costos_dinamico = []
    
    for i in range(n_replicas):
        m_base, _ = correr_simulacion(escenario_dinamico=False)
        res_base.append(m_base)
        
        m_din, c_din = correr_simulacion(escenario_dinamico=True)
        res_dinamico.append(m_din)
        costos_dinamico.append(c_din)

    media_base = np.mean(res_base)
    media_din = np.mean(res_dinamico)
    media_costo = np.mean(costos_dinamico)
    
    ic_base = stats.t.interval(0.95, df=n_replicas-1, loc=media_base, scale=stats.sem(res_base))
    ic_din = stats.t.interval(0.95, df=n_replicas-1, loc=media_din, scale=stats.sem(res_dinamico))
    
    print("\n--- RESULTADOS (Vehiculos esperando > 3 min) ---")
    print(f"Escenario Base:     Media = {media_base:.2f} | IC 95%: ({ic_base[0]:.2f}, {ic_base[1]:.2f})")
    print(f"Escenario Dinamico: Media = {media_din:.2f} | IC 95%: ({ic_din[0]:.2f}, {ic_din[1]:.2f})")
    
    dif_multados = media_base - media_din
    
    print("\n--- ANALISIS ECONOMICO ---")
    print(f"Costo extra promedio por abrir 3ra cabina: ${media_costo:.2f} / dia")
    print(f"Vehiculos salvados de multa: {dif_multados:.2f} / dia")
    
    if dif_multados > 0:
        multa_eq = media_costo / dif_multados
        print(f"Valor de MULTA DE EQUILIBRIO: ${multa_eq:.2f} por vehiculo")
    else:
        print("La estrategia dinamica no logro reducir el numero de multados.")

if __name__ == '__main__':
    main()
