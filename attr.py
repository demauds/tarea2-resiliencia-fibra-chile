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


def contar_pares(padre, nodos):
    pares = list(combinations(range(len(nodos)), 2))
    conectados = 0
    for i, j in pares:
        if nodos[i] is not None and nodos[j] is not None:
            if encontrar(padre, nodos[i]) == encontrar(padre, nodos[j]):
                conectados += 1
    return conectados / len(pares), conectados, len(pares)


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

    total = 0.0
    for _ in range(simulaciones):
        padre = padre_base.copy()
        for s, t, p in expuestos:
            if rng.random() >= p:
                unir(padre, s, t)
        total += contar_pares(padre, nodos)[0]

    return total / simulaciones
