import random
from itertools import combinations


def encontrar(padre, x):
    while padre.get(x, x) != x:
        padre[x] = padre.get(padre[x], padre[x])
        x = padre[x]
    return x


def unir(padre, a, b):
    ra, rb = encontrar(padre, a), encontrar(padre, b)
    if ra != rb:
        padre[ra] = rb


def pares_conectados(padre, nodos):
    pares = []
    for i, j in combinations(range(len(nodos)), 2):
        if nodos[i] is not None and nodos[j] is not None:
            if encontrar(padre, nodos[i]) == encontrar(padre, nodos[j]):
                pares.append((i, j))
    return pares


def contar_pares(padre, nodos):
    total = len(nodos) * (len(nodos) - 1) // 2
    pares = pares_conectados(padre, nodos)
    return len(pares) / total, len(pares), total, pares


def attr_operacion(enlaces, nodos):
    padre = {}
    for s, t in enlaces:
        unir(padre, s, t)
    return contar_pares(padre, nodos)


def attr_terremoto(enlaces_prob, nodos, simulaciones=10000, semilla=2010):
    rng = random.Random(semilla)
    padre_base = {}
    expuestos = []

    for s, t, p in enlaces_prob:
        if p <= 0:
            unir(padre_base, s, t)
        else:
            expuestos.append((s, t, p))

    suma = 0.0
    suma_cuad = 0.0
    veces = {}
    for _ in range(simulaciones):
        padre = padre_base.copy()
        for s, t, p in expuestos:
            if rng.random() >= p:
                unir(padre, s, t)
        valor, _, _, pares = contar_pares(padre, nodos)
        suma += valor
        suma_cuad += valor * valor
        for par in pares:
            veces[par] = veces.get(par, 0) + 1

    media = suma / simulaciones
    # error estándar de la media: s / raíz(N)
    varianza = max(0.0, (suma_cuad - simulaciones * media * media) / (simulaciones - 1))
    error = (varianza / simulaciones) ** 0.5
    prob_par = {par: v / simulaciones for par, v in veces.items()}
    return media, error, prob_par
