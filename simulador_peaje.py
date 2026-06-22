import simpy #maneja el tiempo y los servidores
import random #Genera los numeros pseudoaleatorios
import numpy as np
from scipy import stats
#tanto numpy como scipy se utilizan para calculos de media

# Constantes de tiempo
DIA_EN_SEGUNDOS = 24 * 3600

class PeajeConfig:
    LLEGADAS = {
        'gran_porte': {'pico': 60.0, 'no_pico': 120.0},
        'grandes': {'pico': 80.0, 'no_pico': 140.0},
        'pequenos': {'pico': 50.0, 'no_pico': 80.0},
        'motos': {'pico': 760.0, 'no_pico': 760.0}
    }##las tasas de llegadas se duplican ya que se supone que los tiempos que daba 
    ##enunciado eran la tasa de llegada entre las dos estaciones. Por ejemplo:
    #un vehiculo de gran porte que tiene una tasa de llegada de 30 segundos, significa 
    #que llega a UNA de las estaciones cada 30 segundos pero para una estacion individual
    #el vehiculo de gran porte llega a la otra estacion en 30 segundos y 30 segundos
    #despues llega a la actual, entonces el tiempo promedio de llegada es de 60 segundos.
    #se supone esto debido a que si se tomaran los tiempos que dice la consigna, el sistema 
    #seria explosivo 
   ##'gran_porte': {'pico': 60.0, 'no_pico': 120.0},
       ## 'grandes': {'pico': 80.0, 'no_pico': 140.0},
       ## 'pequenos': {'pico': 50.0, 'no_pico': 80.0},
        ##'motos': {'pico': 760.0, 'no_pico': 760.0}
    #}##las tasas de llegadas se duplican ya que se supone que los tiempos que daba """
def tiempo_servicio(tipo):##segun el vehiculo que llega se le da un tiempo de servicio aleatorio
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
        self.cabinas = [simpy.Resource(env, capacity=1) for _ in range(3)]##crea 3 cabinas o servidores con capacidad de atender 1 vehiculo a la vez
        self.cabinas_base = 1
        self.cabinas_extra_activas = 0
        self.vehiculos_atendidos_recientes = []##guarda el tiempo de espera de los vehiculos atendidos en los ultimos 10 min, luego se reinicia
        #cuando un vehiculo ingresa a la cola comienza el contador, cuando es atendido se frena y se guarda en el array

    @property
    def cabinas_activas(self):##devuelve las cabinas activas en este momento
        return min(3, self.cabinas_base + self.cabinas_extra_activas)#como maximo devuelve 3. Devuelve cabinas_base (1) + cabinas_extra(0 o 2)

def gestor_horario_base(env, estacion):
    while True:
        hora_actual = (env.now % DIA_EN_SEGUNDOS) / 3600.0##convierte el tiempo actual en las horas del dia
        if estacion.nombre == 'A':##si es la estacion A
            if 7.0 <= hora_actual < 9.0:##si la hora actual es entre las 7 y las 9 (horario pico)
                estacion.cabinas_base = 2##abre 1 cabina, hay 2 abiertas en total
                yield env.timeout((9.0 - hora_actual) * 3600)##espera a que sean las 9am
            else:##si no es horario pico
                estacion.cabinas_base = 1##solo una cabina abierta
                next_event = 7.0 if hora_actual < 7.0 else 24.0 + 7.0##si la hora_actual es menor a 
                #las 7 am, significa que tiene que esperar hasta las 7, caso contrario (hora_actual>9am) espera hasta el otro dia (24+7) 
                yield env.timeout((next_event - hora_actual) * 3600)##el hilo de esta funcion espera hasta el horario indicado
        elif estacion.nombre == 'D':
            if 19.0 <= hora_actual < 20.0:##si es horario pico (19pm a 20pm)
                estacion.cabinas_base = 2##abre 1 cabina, hay 2 abiertas en total
                yield env.timeout((20.0 - hora_actual) * 3600)##espera a que sean las 20pm
            else:##si no es horario pico
                estacion.cabinas_base = 1##una sola cabina abierta
                next_event = 19.0 if hora_actual < 19.0 else 24.0 + 19.0##si la hora actual es menor a 19pm, 
                ##la proxima hora pico es a las 19pm, caso contrario (hora_actual>20pm), espera hasta el otro dia (24+19)
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
            espera_media = np.mean(estacion.vehiculos_atendidos_recientes)##calcula la espera media 
            ##de los ultimos 10 minutos con el array que contiene el tiempo de espera de los vehiculos
            #que estuvieron en la cola los ultimos 10 min

        
        # Limpiamos para el próximo intervalo
        estacion.vehiculos_atendidos_recientes = []
        
        if espera_media > 180.0 and estacion.cabinas_activas < 3:##si la espera media es mayor a 180 (3 min)
            ##y hay menos de 3 cabinas activas
            # Habilitar cabina extra
            estacion.cabinas_extra_activas = 1
            costo_list.append(100) # $100 por 10 mins
            yield env.timeout(10.0 * 60)##espera 10 min
            # Deshabilitar cabina extra
            estacion.cabinas_extra_activas = 0##pasados los 10 min cierra la cabina extra para volver
            #a analizar si la tiene que volver a abrir
        else:##si la espera media es menor a 180 segundos (3 min) o las cabinas activas que hay son 3
            ##(no puede haber mas de 3 cabinas)
            yield env.timeout(10.0 * 60)##no abre ninguna cabina extra y espera 10 min para volver a hacer 
            ##el analisis


def generador_vehiculos(env, estacion, tipo, stats_list):##hay 4 generadores de vehiculos (uno por tipo) corriendo
    ##en paralelo para cada estacion
    while True:
        hora_actual = (env.now % DIA_EN_SEGUNDOS) / 3600.0##obtiene la hora actual
        pico = False
        if estacion.nombre == 'A' and 7.0 <= hora_actual < 9.0:##se fija si es el horario pico
            pico = True
        elif estacion.nombre == 'D' and 19.0 <= hora_actual < 20.0:##se fija si es el horario pico
            pico = True
            
        estado = 'pico' if pico else 'no_pico'##convierte el booleano pico en String 'pico' en caso
        ##de que sea horario pico o en 'no_pico' en caso de que no sea horario pico
        tasa = PeajeConfig.LLEGADAS[tipo][estado] ##busca la tasa de llegada para el tipo de vehiculo 
        ##actual y segun si es horario pico o no
        
        yield env.timeout(random.expovariate(1.0 / tasa))##genera un numero aleatorio siguiendo una 
        ##distribucion exponencial segun el lambda que es 1/tasa. Y espera ese tiempo aleatorio
        env.process(vehiculo(env, estacion, tipo, stats_list))##una vez que pasa ese tiempo aleatorio
        ##se envia el vehiculo a la simulacion

def vehiculo(env, estacion, tipo, stats_list):
    llegada = env.now ##registra el momento de la llegada
    
    abiertas = estacion.cabinas[:estacion.cabinas_activas]##toma las cabinas activas
    mejor_cabina = min(abiertas, key=lambda c: len(c.queue))#elige la cabina que tiene la 
    ##cola mas corta
    
    with mejor_cabina.request() as req:##el vehiculo pide turno en la mejor cabina
        yield req##el vehiculo se queda esperando hasta que la cabina este libre
        espera = env.now - llegada##una vez atendido, se calcula la espera que tuvo en cola
        stats_list.append(espera)##agrega ese tiempo de espera a la lista del tiempo de 
        #espera que tuvo cada vehiculo
        estacion.vehiculos_atendidos_recientes.append(espera)##se agrega ese tiempo de espera
        ##a la lista de los autos atendidos en los ultimos 10 min (utilizada para saber si 
        #conviene abrir una tercera cabina)
        
        yield env.timeout(tiempo_servicio(tipo))##simula el tiempo de servicio

def correr_simulacion(escenario_dinamico):##recibe un booleano: si es true, se simula
    ##con una posible apertura de una tercera cabina en los casos en los cuales, 
    #en un periodo de 10 min el tiempo medio de espera en la cola sea mayor a 3 min
    env = simpy.Environment()##se crea el entorno simpy, la libreria que permite
    ##manejar el tiempo y los servidores
    
    estacion_a = Estacion(env, 'A')##crea la estacion A 
    estacion_d = Estacion(env, 'D')##crea la estacion B 
    
    env.process(gestor_horario_base(env, estacion_a))##se incializan las estaciones 
    ##base indicadas segun si es hora pico o no
    env.process(gestor_horario_base(env, estacion_d))##se incializan las estaciones 
    ##base indicadas segun si es hora pico o no
    
    costos_extra_a = []##costos de abrir la tercer cabina en la estacion A
    costos_extra_d = []##costos de abrir la tercer cabina en la estacion D
    
    if escenario_dinamico:##si el booleano es True
        env.process(supervisor_dinamico(env, estacion_a, costos_extra_a))##lanza
        #el proceso supervisor que abre la tercer cabina en caso de que el promedio 
        #de espera supere los 3 minutos
        env.process(supervisor_dinamico(env, estacion_d, costos_extra_d))##lanza
        #el proceso supervisor que abre la tercer cabina en caso de que el promedio 
        #de espera supere los 3 minutos
    
    stats_a = []##lista donde se van guardando los tiempos de espera en la cola de cada 
    #vehiculo en la estacion A
    stats_d = []##lista donde se van guardando los tiempos de espera en la cola de cada 
    #vehiculo en la estacion D
    
    for tipo in PeajeConfig.LLEGADAS.keys():##por cada tipo de vehiculo
        env.process(generador_vehiculos(env, estacion_a, tipo, stats_a))##se van generando
        ##vehiculos de ese tipo que van llegando aleatoriamente a la estacion A
        env.process(generador_vehiculos(env, estacion_d, tipo, stats_d))##se van generando
        ##vehiculos de ese tipo que van llegando aleatoriamente a la estacion D
        
    env.run(until=DIA_EN_SEGUNDOS)##corre la simulacion en la cual se simula un dia entero
    
    esperas_a = np.array(stats_a)##se convierten las listas de espera de la estacion A 
    ##a Arrays de tipo numpy (libreria que hace la matematica descriptiva)
    esperas_d = np.array(stats_d)##se convierten las listas de espera de la estacion D 
    ##a Arrays de tipo numpy (libreria que hace la matematica descriptiva)
    
    multados = np.sum(esperas_a > 180) + np.sum(esperas_d > 180)##cuenta la cantidad de
    #vehiculos que esperaron mas de 180 seg (3 min) en la cola de ambas estaciones

    costo_total = sum(costos_extra_a) + sum(costos_extra_d)##suma los costos de abrir 
    #la tercera cabina tanto para A como para D
    
    return multados, costo_total

def main():
    print("Iniciando simulacion de Peaje (30 replicas por escenario)...")
    n_replicas = 30
    
    res_base = []##aca se guardan la cantidad de multados en todas las iteraciones
    res_dinamico = []##aca se guardan la cantidad de multados en la simulacion dinamica
    costos_dinamico = []##aca se guardan los costos de abrir la tercer 
    
    for i in range(n_replicas):
        random.seed(i)
        m_base, _ = correr_simulacion(escenario_dinamico=False)##corre la simulacion sin
        ##la posibilidad de abrir la tercer cabina
        res_base.append(m_base)##agrega el resultado al array
        
        random.seed(i)
        m_din, c_din = correr_simulacion(escenario_dinamico=True)##corre la simulacion
        ##con la posibilidad de abrir la tercer cabina
        res_dinamico.append(m_din)##agrega la cantidad autos que estuvieron mas de 3 min
        ##en la cola, por los cuales el duenio recibiria una multa
        costos_dinamico.append(c_din)##agrega los costos por abrir la tercer cabina

    media_base = np.mean(res_base)##calcula el promedio de vehiculos que esperaron mas 
    #de 3 min en la cola en la simulacion sin tercer cabina
    media_din = np.mean(res_dinamico)##calcula el promedio de vehiculos que esperaron mas 
    #de 3 min en la cola en la simulacion con tercer cabina
    media_costo = np.mean(costos_dinamico)##calcula el promedio de costos por abrir 
    #la tercer cabina

    ic_base = stats.t.interval(0.95, df=n_replicas-1, loc=media_base, scale=stats.sem(res_base))
    #usando la distribucion t de student se afirma con un 95% de confianza que el
    #promedio de autos multados (esperaron mas de 3 min en la cola) esta entre ic_base[0]
    #(limite inferior) y ic_base[1] (limite superior) en la simulacion sin posibilidad
    #de abrir tercer cabina
    ic_din = stats.t.interval(0.95, df=n_replicas-1, loc=media_din, scale=stats.sem(res_dinamico))
    #usando la distribucion t de student se afirma con un 95% de confianza que el
    #promedio de autos multados (esperaron mas de 3 min en la cola) esta entre ic_din[0]
    #(limite inferior) y ic_din[1] (limite superior) en la simulacion con posibilidad
    #de abrir tercer cabina

    ##se usa t de student ya que para usar la normal se requiere conocer el desvio 
    #estandar real de la poblacion, el cual no tenemos. A medida que el numero de iteraciones
    #crece, la t de student se va pareciendo cada vez mas a la normal. La t de student requiere
    #la media muestral y el desvio estandar muestral. Para poder aplicar el teorema central
    #del limite necesito que la muestra se repita mas de 30 veces.

    #Teorema Central del Limite: Dice que si tomás muchas muestras independientes de 
    #cualquier distribución (no importa su forma), la distribución de las medias de 
    #esas muestras se aproxima a una distribución normal, sin importar cómo sea la 
    #distribución original.

    #En la simulación, cada réplica devuelve un número de multados. No se sabe qué 
    #distribución tienen esos números. Pero el TCL garantiza que la media de las 30 
    #réplicas se distribuye normalmente, lo que permite aplicar los métodos estadísticos
    #del intervalo de confianza.
    
    print("\n--- RESULTADOS (Vehiculos esperando > 3 min) ---")
    print(f"Escenario Base:     Media = {media_base:.2f} | IC 95%: ({ic_base[0]:.2f}, {ic_base[1]:.2f})")
    print(f"Escenario Dinamico: Media = {media_din:.2f} | IC 95%: ({ic_din[0]:.2f}, {ic_din[1]:.2f})")
    
    dif_multados = media_base - media_din##se obtiene la diferencia de multados entre
    #la simulacion dinamica y la base
    
    print("\n--- ANALISIS ECONOMICO ---")
    print(f"Costo extra promedio por abrir 3ra cabina: ${media_costo:.2f} / dia")
    ##
    print(f"Vehiculos salvados de multa: {dif_multados:.2f} / dia")
    
    if dif_multados > 0:
        multa_eq = media_costo / dif_multados
        print(f"Valor de MULTA DE EQUILIBRIO: ${multa_eq:.2f} por vehiculo")
    else:
        print("La estrategia dinamica no logro reducir el numero de multados.")

if __name__ == '__main__':
    main()
##si corremos la simulacion con los valores reales de la tasa de llegadas
##obtenemos que hay mas multados en la simulacion dinamica que en la base
##esto es raro debido a que la tasa de arribos es igual para los dos, lo que
##cambia es que en la simulacion dinamica hay mas cabinas para atender
##lo que deberia hacer que suba el tiempo de servicio y hay menos multados
##es ilogico pero tiene una explicacion->en la simulacion base (con una cabina
##y dos en horario pico), el promedio de autos multados se saca en base a una
##lista, en la cual se agregan los tiempos desde que el vehiculo llego a 
##la cola hasta que fue atendido. El problema es que en la simulacion base
##hay mucho vehiculos que no se llegan a atender para cuando termina el dia
##por lo tanto no se incluyen en esta lista, en cambio en el caso dinamico,
##como hay mas servidores, se atienden mas autos, por lo que se aniaden 
##mas autos multados a la lista y por eso el promedio es mas alto
##pero en realidad, obviamente hay mas tiempo de espera y mas autos multados
##en el caso base que tiene menos servidores.
