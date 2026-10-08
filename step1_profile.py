import duckdb, hashlib, pathlib
from pathlib import Path

# 你的实际路径
CSV = r"E:\产品\曲风数据分析\archive\data.csv"
con = duckdb.connect(r"E:\产品\曲风数据分析\spotify.duckdb")

# 只读挂载
con.execute(f"""
CREATE OR REPLACE VIEW raw_tracks AS
SELECT * FROM read_csv_auto('{CSV}', header=true, ignore_errors=true)
""")

# 0. 打印真实列名
cols = [c[0] for c in con.execute("DESCRIBE raw_tracks").fetchall()]
print("=" * 60)
print("data.csv 真实列名:")
for i, c in enumerate(cols):
    print(f"  {i+1:2d}. {c}")
print("=" * 60)

# 1. 规模与年份范围（release_date 解析）
e01 = con.execute("""
SELECT count(*) AS n_rows,
       min(CAST(release_date AS DATE)) AS y_min,
       max(CAST(release_date AS DATE)) AS y_max,
       count(DISTINCT id) AS n_distinct_id
FROM raw_tracks
WHERE release_date IS NOT NULL
""").fetchdf()
print("\n【1】规模与年份范围:")
print(e01)

# 2. 重复与缺失
e02 = con.execute("""
SELECT count(*) - count(DISTINCT id) AS dup_id,
       sum(CASE WHEN release_date IS NULL THEN 1 ELSE 0 END) AS null_date,
       sum(CASE WHEN popularity IS NULL THEN 1 ELSE 0 END) AS null_pop,
       sum(CASE WHEN valence IS NULL THEN 1 ELSE 0 END) AS null_valence,
       sum(CASE WHEN tempo IS NULL THEN 1 ELSE 0 END) AS null_tempo,
       sum(CASE WHEN energy IS NULL THEN 1 ELSE 0 END) AS null_energy
FROM raw_tracks
""").fetchdf()
print("\n【2】重复与缺失:")
print(e02)

# 3. 越界值
e03 = con.execute("""
SELECT sum(CASE WHEN popularity NOT BETWEEN 0 AND 100 THEN 1 ELSE 0 END) AS bad_pop,
       sum(CASE WHEN valence NOT BETWEEN 0 AND 1 THEN 1 ELSE 0 END) AS bad_valence,
       sum(CASE WHEN energy NOT BETWEEN 0 AND 1 THEN 1 ELSE 0 END) AS bad_energy,
       sum(CASE WHEN tempo NOT BETWEEN 40 AND 260 THEN 1 ELSE 0 END) AS bad_tempo
FROM raw_tracks
""").fetchdf()
print("\n【3】越界值:")
print(e03)

# 4. 每年样本量（用 EXTRACT(YEAR FROM ...) 从 date 提年份）
e04 = con.execute("""
SELECT EXTRACT(YEAR FROM CAST(release_date AS DATE))::INT AS yr,
       count(*) AS n
FROM raw_tracks
WHERE release_date IS NOT NULL
GROUP BY 1
ORDER BY 1
""").fetchdf()
print("\n【4】每年样本量:")
print(e04.to_string(index=False))

# 5. 数据指纹
h = hashlib.sha256(pathlib.Path(CSV).read_bytes()).hexdigest()
print(f"\n【5】SHA256: {h}")

# 6. 关键检查：有没有 genre 列
has_genre = any('genre' in c.lower() for c in cols)
print(f"\n【6】data.csv 是否含 genre 列: {has_genre}")
if has_genre:
    print("    → 包含的列:", [c for c in cols if 'genre' in c.lower()])

print("\n" + "=" * 60)
print("✅ 体检完成")
print("=" * 60)