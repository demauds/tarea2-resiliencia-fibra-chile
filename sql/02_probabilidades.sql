-- Probabilidad de falla por enlace según el terremoto 8.8 (27F, Maule 2010)
-- Modelo de fallas geográficas de Agarwal et al. (2013): p(d) = max(0, 1 - d / R), R = 250 km
DROP TABLE IF EXISTS probabilidad_falla;
CREATE TABLE probabilidad_falla AS
SELECT e.gid,
       e.source,
       e.target,
       ST_Distance(e.geom::geography, s.geom::geography) / 1000.0 AS dist_epicentro_km,
       GREATEST(0.0, 1.0 - (ST_Distance(e.geom::geography, s.geom::geography) / 1000.0) / 250.0)
           AS prob_falla
FROM enlaces e
CROSS JOIN (SELECT geom FROM sismo WHERE mag = 8.8 LIMIT 1) s;

ALTER TABLE probabilidad_falla ADD PRIMARY KEY (gid);

-- Se actualiza la columna prob_falla de enlaces (los que quedan fuera del radio siguen en 0)
UPDATE enlaces e
   SET prob_falla = p.prob_falla
  FROM probabilidad_falla p
 WHERE e.gid = p.gid;
