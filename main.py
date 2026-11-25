import argparse
import csv
import json
import os
import webbrowser
from pathlib import Path

import psycopg
import shapefile

from attr import attr_operacion, attr_terremoto

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
SQL = BASE / "sql"
SHP_FIBRA = DATA / "fibra_optica_detectada.shp"
SISMO = DATA / "sismo_8.8.geojson"
NODOS = DATA / "nodos_clave.csv"
MAX_DIST_NODO_KM = 10.0
SIMULACIONES = 10000


def conectar():
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
        dbname=os.getenv("PGDATABASE", "postgres"),
        autocommit=True,
    )


def cargar_fibra(cur):
    sf = shapefile.Reader(str(SHP_FIBRA), encoding="latin1")
    cur.execute("""
        DROP TABLE IF EXISTS fibra;
        CREATE TABLE fibra (
            gid serial PRIMARY KEY,
            id varchar(254),
            geom geometry(LineString, 4326)
        )
    """)
    filas = []
    for sr in sf.shapeRecords():
        coords = ",".join(f"{x} {y}" for x, y in sr.shape.points)
        wkt = f"LINESTRING({coords})"
        filas.append((sr.record["id"], wkt))

    cur.executemany(
        "INSERT INTO fibra (id, geom) VALUES (%s, ST_GeomFromText(%s, 4326))",
        filas,
    )
    cur.execute("CREATE INDEX fibra_geom_idx ON fibra USING gist (geom)")


def crear_topologia(cur):
    cur.execute((SQL / "01_topologia.sql").read_text(encoding="utf-8"))


def revisar_conectividad(cur):
    cur.execute("""
        SELECT count(*), count(*) FILTER (WHERE n = 2), max(n)
          FROM (
              SELECT component, count(*) AS n
                FROM pgr_connectedComponents(
                    'SELECT gid AS id, source, target, 1 AS cost, 1 AS reverse_cost FROM enlaces'
                )
               GROUP BY component
          ) c
    """)
    return cur.fetchone()


def cargar_nodos(cur):
    cur.execute("""
        DROP TABLE IF EXISTS nodos_clave;
        CREATE TABLE nodos_clave (
            id serial PRIMARY KEY,
            nombre text,
            rol text,
            descripcion text,
            geom geometry(Point, 4326),
            vertice integer,
            dist_red_km double precision
        )
    """)
    with open(NODOS, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cur.execute(
                "INSERT INTO nodos_clave (nombre, rol, descripcion, geom) "
                "VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))",
                (r["nombre"], r["rol"], r["descripcion"], float(r["lon"]), float(r["lat"])),
            )

    cur.execute("""
        UPDATE nodos_clave n
           SET vertice = c.vid,
               dist_red_km = c.km
          FROM (
              SELECT k.id,
                     v.id AS vid,
                     ST_Distance(k.geom::geography, v.the_geom::geography) / 1000.0 AS km
                FROM nodos_clave k
                CROSS JOIN LATERAL (
                    SELECT id, the_geom
                      FROM enlaces_vertices_pgr
                     ORDER BY the_geom <-> k.geom
                     LIMIT 1
                ) v
          ) c
         WHERE n.id = c.id
    """)


def cargar_sismo(cur):
    cur.execute("""
        DROP TABLE IF EXISTS sismo_json;
        CREATE TABLE sismo_json (data jsonb);
        DROP TABLE IF EXISTS sismo;
    """)
    cur.execute("INSERT INTO sismo_json VALUES (%s)", (SISMO.read_text(encoding="utf-8"),))
    cur.execute("""
        CREATE TABLE sismo AS
        SELECT f->>'id' AS id,
               (f->'properties'->>'mag')::numeric AS mag,
               f->'properties'->>'place' AS lugar,
               to_timestamp((f->'properties'->>'time')::bigint / 1000.0) AS fecha,
               (f->'geometry'->'coordinates'->>2)::numeric AS profundidad_km,
               ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(f->'geometry')), 4326) AS geom
          FROM sismo_json, LATERAL jsonb_array_elements(data->'features') AS f
    """)


def calcular_probabilidades(cur):
    cur.execute((SQL / "02_probabilidades.sql").read_text(encoding="utf-8"))


def texto_sql(valor):
    if valor is None:
        return "NULL"
    return "'" + str(valor).replace("'", "''") + "'"


def escribir_main_sql(cur):
    cur.execute("""
        SELECT e.gid, e.id_yafun, e.source, e.target, e.largo_km,
               p.dist_epicentro_km, e.prob_falla, ST_AsText(e.geom)
          FROM enlaces e
          JOIN probabilidad_falla p USING (gid)
         ORDER BY e.gid
    """)
    filas = cur.fetchall()
    lineas = [
        "-- Infraestructura de fibra óptica (Yafún) con la probabilidad de falla de cada enlace",
        "-- Terremoto 8.8 del 27/02/2010, modelo p = max(0, 1 - d/250 km),",
        "-- d = distancia mínima epicentro-enlace. source y target vienen de pgr_createTopology.",
        "CREATE EXTENSION IF NOT EXISTS postgis;",
        "DROP TABLE IF EXISTS enlaces;",
        "CREATE TABLE enlaces (",
        "    gid integer PRIMARY KEY,",
        "    id_yafun varchar(254),",
        "    source integer,",
        "    target integer,",
        "    largo_km double precision,",
        "    dist_epicentro_km double precision,",
        "    prob_falla double precision NOT NULL DEFAULT 0,",
        "    geom geometry(LineString, 4326)",
        ");",
        "INSERT INTO enlaces (gid, id_yafun, source, target, largo_km, dist_epicentro_km, prob_falla, geom) VALUES",
    ]
    valores = [
        f"({g}, {texto_sql(i)}, {s}, {t}, {l:.3f}, {d:.3f}, {p:.6f}, ST_GeomFromText('{w}', 4326))"
        for g, i, s, t, l, d, p, w in filas
    ]
    lineas.append(",\n".join(valores) + ";")
    lineas.append("CREATE INDEX enlaces_geom_idx ON enlaces USING gist (geom);")
    (BASE / "main.sql").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return len(filas)


def mostrar_sismo(cur):
    cur.execute("""
        SELECT id, mag, lugar, fecha AT TIME ZONE 'America/Santiago',
               profundidad_km, round(ST_Y(geom)::numeric, 3), round(ST_X(geom)::numeric, 3)
          FROM sismo
    """)
    print("   Tabla sismo:")
    print("   id | mag | lugar | fecha (hora Chile) | profundidad km | lat | lon")
    for fila in cur.fetchall():
        print("   " + " | ".join(str(x) for x in fila))


def mostrar_enlaces_afectados(cur, n=5):
    cur.execute("""
        SELECT count(*) FILTER (WHERE prob_falla > 0),
               count(*) FILTER (WHERE prob_falla = 0),
               avg(prob_falla) FILTER (WHERE prob_falla > 0)
          FROM enlaces
    """)
    afectados, sin_falla, promedio = cur.fetchone()
    print(f"   {afectados} enlaces con p > 0 (promedio {promedio:.3f}), {sin_falla} con p = 0")
    for titulo, orden in (("más afectados", "DESC"), ("menos afectados con p > 0", "ASC")):
        cur.execute(f"""
            SELECT e.gid, e.source, e.target, round(e.largo_km::numeric, 2),
                   round(p.dist_epicentro_km::numeric, 1), round(e.prob_falla::numeric, 6)
              FROM enlaces e
              JOIN probabilidad_falla p USING (gid)
             WHERE e.prob_falla > 0
             ORDER BY e.prob_falla {orden}, e.gid
             LIMIT {n}
        """)
        print(f"   Enlaces {titulo}:")
        print("   gid | source | target | largo km | dist. epicentro km | prob. falla")
        for fila in cur.fetchall():
            print("   " + " | ".join(str(x) for x in fila))


def leer_nodos(cur):
    cur.execute("""
        SELECT nombre, rol, descripcion, vertice, dist_red_km,
               ST_X(geom), ST_Y(geom)
          FROM nodos_clave
         ORDER BY id
    """)
    return cur.fetchall()


def calcular_attr(cur, nodos):
    vertices = [v if d <= MAX_DIST_NODO_KM else None for _, _, _, v, d, _, _ in nodos]
    cur.execute("SELECT source, target FROM enlaces")
    antes = attr_operacion(cur.fetchall(), vertices)
    cur.execute("SELECT source, target, prob_falla FROM probabilidad_falla")
    despues = attr_terremoto(cur.fetchall(), vertices, simulaciones=SIMULACIONES)
    return antes, despues


def generar_mapa(cur, nodos, antes, despues):
    cur.execute("""
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', json_agg(
                json_build_object(
                    'type', 'Feature',
                    'geometry', ST_AsGeoJSON(e.geom)::json,
                    'properties', json_build_object(
                        'gid', e.gid,
                        'largo_km', round(e.largo_km::numeric, 2),
                        'dist_km', round(p.dist_epicentro_km::numeric, 1),
                        'prob', round(p.prob_falla::numeric, 4)
                    )
                )
            )
        )
        FROM enlaces e
        JOIN probabilidad_falla p USING (gid)
    """)
    enlaces = cur.fetchone()[0]
    cur.execute(
        "SELECT ST_X(geom), ST_Y(geom), mag, lugar, fecha::date, profundidad_km "
        "FROM sismo WHERE mag = 8.8"
    )
    lon, lat, mag, lugar, fecha, prof = cur.fetchone()
    datos = {
        "enlaces": enlaces,
        "nodos": [
            {"nombre": n, "rol": r, "desc": d, "dist": round(km, 2), "lon": x, "lat": y}
            for n, r, d, _, km, x, y in nodos
        ],
        "sismo": {
            "lon": lon,
            "lat": lat,
            "mag": float(mag),
            "lugar": lugar,
            "fecha": str(fecha),
            "prof": float(prof),
            "radio_km": 250,
        },
        "attr": {
            "antes": antes[0],
            "pares": antes[2],
            "conectados": antes[1],
            "despues": despues[0],
        },
    }
    html = (BASE / "mapa_plantilla.html").read_text(encoding="utf-8")
    salida = BASE / "mapa.html"
    salida.write_text(html.replace("__DATOS_MAPA__", json.dumps(datos, ensure_ascii=False)), encoding="utf-8")
    return salida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-navegador", action="store_true", help="no abrir el mapa")
    args = ap.parse_args()

    with conectar() as con, con.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        print("1) Cargando fibra óptica (Yafún) ...")
        cargar_fibra(cur)
        print("2) Creando topología ...")
        crear_topologia(cur)
        cur.execute("SELECT count(*) FROM enlaces")
        n_enl = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM enlaces_vertices_pgr")
        n_ver = cur.fetchone()[0]
        print(f"   {n_enl} enlaces, {n_ver} vértices (pgr_createTopology)")
        comp, aisladas, mayor = revisar_conectividad(cur)
        print(f"   {comp} componentes conexas, {aisladas} de solo dos vértices, "
              f"la mayor con {mayor} vértices")
        print("3) Cargando nodos clave y sismo 8.8 ...")
        cargar_nodos(cur)
        cargar_sismo(cur)
        mostrar_sismo(cur)
        print("4) Calculando probabilidades de falla ...")
        calcular_probabilidades(cur)
        mostrar_enlaces_afectados(cur)
        n = escribir_main_sql(cur)
        print(f"   main.sql generado con {n} enlaces (geometría y probabilidad de falla)")
        nodos = leer_nodos(cur)
        print("5) Calculando ATTR ...")
        antes, despues = calcular_attr(cur, nodos)
        attr_post, error, prob_par = despues
        print(f"   ATTR en operación : {antes[0]:.4f} ({antes[1]} de {antes[2]} pares conectados)")
        print(f"   ATTR post 8.8     : {attr_post:.4f} (esperado, {SIMULACIONES} simulaciones, "
              f"error estándar {error:.6f})")
        dif = attr_post - antes[0]
        print(f"   Diferencia        : {dif:.4f} ({dif / antes[0] * 100:.1f} %)")
        print("   Pares conectados antes del sismo y probabilidad de seguir conectados:")
        for i, j in antes[3]:
            print(f"     {nodos[i][0]} - {nodos[j][0]}: {prob_par.get((i, j), 0.0):.4f}")
        mapa = generar_mapa(cur, nodos, antes, despues)
        print(f"6) Mapa: {mapa}")
    if not args.sin_navegador:
        webbrowser.open(mapa.as_uri())


if __name__ == "__main__":
    main()
