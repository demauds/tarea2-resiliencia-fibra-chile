-- Convierte la tabla fibra en topología de red con pgRouting 3.x
CREATE EXTENSION IF NOT EXISTS pgrouting;

DROP TABLE IF EXISTS enlaces_vertices_pgr;
DROP TABLE IF EXISTS enlaces;
CREATE TABLE enlaces AS
SELECT gid, id AS id_yafun, geom
FROM fibra;

ALTER TABLE enlaces ADD PRIMARY KEY (gid);
ALTER TABLE enlaces ADD COLUMN source integer;
ALTER TABLE enlaces ADD COLUMN target integer;
ALTER TABLE enlaces ADD COLUMN largo_km double precision;
-- Probabilidad de falla de cada enlace, parte en 0 y se actualiza en 02_probabilidades.sql
ALTER TABLE enlaces ADD COLUMN prob_falla double precision NOT NULL DEFAULT 0;
UPDATE enlaces SET largo_km = ST_Length(geom::geography) / 1000.0;

-- Misma tolerancia usada en clases (0.0001 grados, ~11 m)
-- pgr_createTopology crea también los índices de source y target
SELECT pgr_createTopology('enlaces', 0.0001, the_geom := 'geom', id := 'gid');
