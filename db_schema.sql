-- ================================================================
-- spotify.duckdb Schema 导出
-- 导出时间: 2026-09-26 16:03
-- 文件 SHA256: 61d7eaf626380c7705da36418edc5f1a471f18b8f4c0e9c34d495a2eaeb006d8
-- ================================================================

-- 用户对象总数: 4

-- ── VIEW: artist_panel ──
-- 定义: CREATE VIEW artist_panel AS SELECT artists AS artist, "year" AS yr, avg(valence) AS mean_valence, avg(energy) AS mean_energy, count_star() AS n_tracks FROM raw_tracks WHERE (("year" IS NOT NULL) AND (artists IS NOT NULL)) GROUP BY 1, 2;
CREATE VIEW artist_panel (
    artist                   VARCHAR         -- null:YES key:-     
    yr                       BIGINT          -- null:YES key:-     
    mean_valence             DOUBLE          -- null:YES key:-     
    mean_energy              DOUBLE          -- null:YES key:-     
    n_tracks                 BIGINT          -- null:YES key:-     
);
-- 行数: 58,236

-- ── VIEW: decade_features ──
-- 定义: CREATE VIEW decade_features AS SELECT (("year" // 10) * 10) AS "decade", ((("year" // 10) * 10) = 2020) AS is_partial_decade, avg(danceability) AS mean_danceability, avg(energy) AS mean_energy, count_star() AS n FROM raw_tracks WHERE ("year" IS NOT NULL) GROUP BY 1, 2 ORDER BY 1;
CREATE VIEW decade_features (
    decade                   BIGINT          -- null:YES key:-     
    is_partial_decade        BOOLEAN         -- null:YES key:-     
    mean_danceability        DOUBLE          -- null:YES key:-     
    mean_energy              DOUBLE          -- null:YES key:-     
    n                        BIGINT          -- null:YES key:-     
);
-- 行数: 11

-- ── VIEW: raw_tracks ──
-- 定义: CREATE VIEW raw_tracks AS SELECT * FROM read_csv_auto('E:\产品\曲风数据分析\archive\data.csv', ("header" = CAST('t' AS BOOLEAN)), (ignore_errors = CAST('t' AS BOOLEAN)));
CREATE VIEW raw_tracks (
    valence                  DOUBLE          -- null:YES key:-     
    year                     BIGINT          -- null:YES key:-     
    acousticness             DOUBLE          -- null:YES key:-     
    artists                  VARCHAR         -- null:YES key:-     
    danceability             DOUBLE          -- null:YES key:-     
    duration_ms              BIGINT          -- null:YES key:-     
    energy                   DOUBLE          -- null:YES key:-     
    explicit                 BIGINT          -- null:YES key:-     
    id                       VARCHAR         -- null:YES key:-     
    instrumentalness         DOUBLE          -- null:YES key:-     
    key                      BIGINT          -- null:YES key:-     
    liveness                 DOUBLE          -- null:YES key:-     
    loudness                 DOUBLE          -- null:YES key:-     
    mode                     BIGINT          -- null:YES key:-     
    name                     VARCHAR         -- null:YES key:-     
    popularity               BIGINT          -- null:YES key:-     
    release_date             VARCHAR         -- null:YES key:-     
    speechiness              DOUBLE          -- null:YES key:-     
    tempo                    DOUBLE          -- null:YES key:-     
);
-- 行数: 170,653

-- ── VIEW: yearly_aggregates ──
-- 定义: CREATE VIEW yearly_aggregates AS SELECT "year" AS yr, avg(valence) AS mean_valence, avg(energy) AS mean_energy, avg(danceability) AS mean_danceability, count_star() AS n FROM raw_tracks WHERE ("year" IS NOT NULL) GROUP BY 1 ORDER BY 1;
CREATE VIEW yearly_aggregates (
    yr                       BIGINT          -- null:YES key:-     
    mean_valence             DOUBLE          -- null:YES key:-     
    mean_energy              DOUBLE          -- null:YES key:-     
    mean_danceability        DOUBLE          -- null:YES key:-     
    n                        BIGINT          -- null:YES key:-     
);
-- 行数: 100
