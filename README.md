# Resiliencia de la Internet chilena ante el terremoto 8.8

Tarea 2 de Algoritmos de Ruteo y Redes Resilientes.

## Datos utilizados

La infraestructura corresponde a la base de datos del proyecto Yafún, levantada por NIC Labs para el "Estudio y Recomendaciones sobre la resiliencia de la infraestructura de la Internet chilena" (CORFO 15BPE-47225, 2018) y entregada por SUBTEL en la respuesta a la solicitud de acceso a la información AN002T0005610 (archivo Respuesta_T5610). De los cuatro shapefiles que trae la respuesta se usó solo `fibra_optica_detectada`, ya que es el único que representa tendidos de fibra óptica, los otros tres son caminos con postación eléctrica, caminos sin postación y trayectos en ferry, que el estudio usó para calcular costos de construcción y no para la conectividad existente. La capa tiene 1.915 tramos en EPSG:4326 que suman 10.313 km.

El sismo se descargó desde el buscador de USGS en formato GeoJSON (`data/sismo_8.8.geojson`), es el evento `official20100227063411530_30`, magnitud 8.8, ocurrido el 27 de febrero de 2010 a las 03:34 hora de Chile, con epicentro en -36.122, -72.898 y 22,9 km de profundidad.

## Nodos clave

Los nodos clave están en `data/nodos_clave.csv` y se separaron según el rol que cumplen con la información. Generan información los puntos de entrada de contenido y tráfico internacional, que son Arica y Valparaíso por el aterrizaje de cables submarinos, Los Andes por el cruce terrestre de fibra hacia Argentina y el data center de Google en Quilicura, esto ya que el estudio Yafún cita a SUBTEL indicando que la red se conecta al backbone internacional por cables submarinos y desde Santiago hacia Argentina, además el informe de Redes Regionales Sudamericanas del curso menciona el data center de Quilicura.

Para los nodos que intercambian información se tomaron los puntos de intercambio de tráfico (IXP) nombrados en el informe de Redes Regionales, que son PIT Santiago y NAP Chile en Santiago, PIT Concepción y PIT Curicó. Como nodos que reciben información se usaron las 16 capitales regionales, desde Arica hasta Punta Arenas, ya que son los puntos de consumo.

Algunas ciudades cumplen más de un rol, por lo cual quedan 19 nodos clave en total. Las coordenadas son las del centro de cada ciudad, igual que el estudio Yafún que usó la plaza de armas de cada comuna como nodo central (supuesto S1). Cada nodo clave se asocia al vértice de la topología más cercano, todos quedan a menos de 1 km de la red con excepción de Quilicura (3,7 km) y Santiago (9,2 km), esto debido a que Yafún no levantó los tendidos dentro del Gran Santiago y en el estudio se supusieron esas conexiones (supuesto S2). Santiago y Quilicura quedan asociados al mismo vértice. Si un nodo clave queda a más de 10 km de la red se considera sin acceso, lo que en este caso no ocurre.

## Topología

La topología se arma en `sql/01_topologia.sql` con `pgr_createTopology` sobre la tabla `enlaces`, usando la misma tolerancia de las clases (0.0001 grados, aproximadamente 11 m). El resultado son 1.915 enlaces y 2.068 vértices en la tabla `enlaces_vertices_pgr`. La red queda separada en 168 componentes, esto coincide con el estudio Yafún, que concluye que la red de fibra del país no es conexa ya que en muchos tramos la fibra no pudo verificarse de forma continua desde el camino.

`pgr_createTopology` existe hasta pgRouting 3.8 y se eliminó en la versión 4.0, por lo que se necesita pgRouting 3.x. El `docker-compose.yml` usa una imagen con pgRouting 3.8.

## ATTR

El ATTR (Average Two-Terminal Reliability) se calcula en `attr.py` como la cantidad de pares de nodos clave conectados dividida por el total de pares sin repetir, que con 19 nodos son 171 pares.

Con la infraestructura en operación el ATTR es 0,0234, ya que solo 4 de los 171 pares están conectados: La Serena con Santiago, La Serena con Quilicura, Santiago con Quilicura y Chillán con Concepción. El resto de los nodos clave están en componentes distintas.

## Modelo de falla

Se usó el modelo probabilístico de fallas geográficas de Agarwal et al. ("The Resilience of WDM Networks to Probabilistic Geographical Failures", IEEE/ACM Transactions on Networking, 21(5), 2013), en el cual la probabilidad de que un componente falle es una función no creciente de la distancia entre el epicentro y el componente. En sus experimentos los autores usan dos funciones, una lineal y una gaussiana, y aquí se eligió la lineal:

```
p(enlace) = max(0, 1 - d / R)
```

donde `d` es la distancia mínima en km entre el epicentro y el enlace y `R` es el radio de efecto, de modo que `d / R` es la distancia normalizada, los autores definen `d` como la distancia euclidiana entre el epicentro y el componente. En el paper el epicentro es una variable ya que buscan la ubicación que más daña la red, mientras que en este trabajo se fijó en el epicentro real del 27F. El radio tampoco viene del paper, ya que en sus experimentos lo van variando, por lo cual se eligió R = 250 km, esto debido a que USGS informa que la ruptura del 27F se extendió cerca de 500 km a lo largo de la costa y 250 km es la mitad de ese largo medido desde el epicentro. Cada enlace de la topología se toma como un componente que falla de forma independiente de los demás.

El cálculo está en `sql/02_probabilidades.sql` y deja la tabla `probabilidad_falla`. Quedan 560 de los 1.915 enlaces con probabilidad mayor a 0, con un promedio de 0,442 entre ellos y un máximo de 0,867 en el enlace más cercano al epicentro, que está a 33,3 km. El archivo `main.sql` tiene la tabla con la probabilidad de falla de cada enlace (gid, source, target, distancia al epicentro y probabilidad).

## ATTR después del terremoto

Como cada enlace falla con su probabilidad, el ATTR después del sismo es un valor esperado, el cual se estimó con 10.000 simulaciones de Monte Carlo (semilla 2010). En cada simulación se sortea qué enlaces fallan y se calcula el ATTR de la red que queda.

El ATTR después del terremoto 8.8 es 0,0175, es decir 3 de los 171 pares. El par Chillán con Concepción quedó desconectado en las 10.000 simulaciones, ya que la componente que une ambas ciudades tiene 188 de sus 201 enlaces dentro del radio del sismo y basta con que falle uno de los enlaces del camino para cortarlo. Los pares entre La Serena, Santiago y Quilicura se mantienen, esto debido a que todos los enlaces de su componente están a más de 365 km del epicentro. Tomando la resiliencia como PostFalla - PreFalla, el resultado es 0,0175 - 0,0234 = -0,0058.

## Ejecución

### Con Docker (recomendado)

Solo se necesita Docker. El comando levanta PostgreSQL con PostGIS 3.5 y pgRouting 3.8 (la imagen `pgrouting/pgrouting:17-3.5-3.8`, que incluye `pgr_createTopology`) y ejecuta `main.py` contra esa base de datos:

```bash
docker compose up --build
```

Al terminar quedan `main.sql` y `mapa.html` en la carpeta del proyecto, y `mapa.html` se abre con doble clic. Como el contenedor no puede abrir el navegador, el mapa se genera con `--sin-navegador`. La base de datos queda disponible en el puerto 5433 del computador (usuario `postgres`, clave `postgres`, base `tarea2`) por si se quiere mirar con QGIS o psql. Para borrar todo lo que creó Docker:

```bash
docker compose down -v
```

La imagen de la base de datos solo existe para amd64, por lo que en un Mac con procesador Apple Silicon corre emulada y es más lenta.

### Sin Docker

Se necesita PostgreSQL con PostGIS, pgRouting 3.x (para `pgr_createTopology`) y Python 3 con los paquetes de `requirements.txt`.

```bash
pip install -r requirements.txt
```

```bash
PGHOST=localhost PGPORT=5432 PGUSER=postgres PGPASSWORD=postgres PGDATABASE=postgres python main.py
```

En Windows (PowerShell) las variables se definen antes con `$env:PGHOST="localhost"` y las demás igual.

### Pasos de main.py

`main.py` carga el shapefile de fibra con `pyshp`, arma la topología, carga los nodos clave y el sismo (el GeoJSON se carga como jsonb y se convierte con `ST_GeomFromGeoJSON`), calcula las probabilidades, genera `main.sql`, muestra en consola el ATTR antes y después, y genera `mapa.html`, que se abre en el navegador. El mapa está hecho con Leaflet y tiene capas para los enlaces en operación, el daño del terremoto (cada enlace coloreado según su probabilidad de falla), el epicentro con el radio del modelo y los nodos clave, además de un recuadro con los dos valores de ATTR. Con `--sin-navegador` se genera el mapa sin abrirlo.

## Archivos

- `main.py`: ejecuta todo el proceso.
- `attr.py`: cálculo del ATTR en operación y del ATTR esperado después del sismo.
- `docker-compose.yml`, `Dockerfile`: base de datos y ejecución con Docker.
- `sql/01_topologia.sql`: topología con `pgr_createTopology`.
- `sql/02_probabilidades.sql`: probabilidad de falla de cada enlace.
- `main.sql`: probabilidades de falla generadas.
- `mapa_plantilla.html`: plantilla Leaflet que usa `main.py` para generar `mapa.html`.
- `data/`: fibra óptica de Yafún, sismo 8.8 de USGS y nodos clave.
