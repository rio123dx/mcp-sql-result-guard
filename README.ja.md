# mcp-sql-result-guard

SQLの中で機微カラムを使うこと自体は妨げず、**MCPがLLMへ返す最終結果列に機微値が流れる可能性があるときだけ停止する**Codex `PreToolUse` hookです。

CTE・副問合せ・中間集約・中間の`SELECT *`で機微値を扱っていても、トップレベルの結果列または`RETURNING`へ届かなければ許可します。

- 詳細な導入・運用手順: [docs/ja/manual.md](docs/ja/manual.md)
- 設計: [docs/architecture.md](docs/architecture.md)
- 制約: [docs/limitations.md](docs/limitations.md)

## 判定例

```sql
-- 許可: user_idはWHERE条件に使うだけ
SELECT amount
FROM orders
WHERE user_id = 'u1';
```

```sql
-- 許可: LISTAGG結果をCTE内で作るが、最終出力しない
WITH x AS (
    SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids
    FROM orders
)
SELECT COUNT(*)
FROM x;
```

```sql
-- 拒否: LISTAGG結果をCTE越しに最終出力する
WITH x AS (
    SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids
    FROM orders
)
SELECT ids
FROM x;
```

## 集約関数の扱い

TSVで`aggregate_reduction`を許可すると、次の統計・論理縮約を最終結果へ返せます。

- `COUNT`、`COUNT DISTINCT`、近似重複除外件数
- `SUM`、`AVG`
- `STDDEV`系、`VARIANCE`系
- `CORR`、`COVAR_POP`、`COVAR_SAMP`
- `BOOL_AND`、`BOOL_OR`

一方、入力値または入力値の集合を返しうるものは、最終結果へ到達した場合に拒否します。

- `MIN`、`MAX`、`ANY_VALUE`
- `LISTAGG`、`GROUP_CONCAT`、`STRING_AGG`
- `ARRAY_AGG`、JSON・オブジェクト集約
- `MEDIAN`、`PERCENTILE_CONT`、`PERCENTILE_DISC`、`MODE`
- 近似パーセンタイル・上位値集合
- `MIN_BY`、`MAX_BY`、未知の集約関数

未知の関数を一律許可せず、既知の安全な縮約だけを明示的に許可する方式です。

## `SELECT *`の扱い

- `WITH x AS (SELECT * FROM users) SELECT COUNT(*) FROM x`: 最終値を返さないため許可
- `WITH x AS (SELECT amount, name FROM users) SELECT * FROM x`: 既知の安全列だけなので許可
- `WITH x AS (SELECT user_id, amount FROM users) SELECT * FROM x`: 機微列が最終出力されるため拒否
- `SELECT * FROM users`: 基表の列構成が不明なので、`__SELECT_STAR__`ルールで拒否可能

## 特徴

- 機微カラムをTSVへ追加できる
- 安全な縮約集約を`aggregate_reduction`で許可できる
- 従来の`count`、`count_distinct`、`approx_count`も後方互換で利用できる
- `deny`と`warn`を選べる
- CTE、副問合せ、多段別名、UNION、ウィンドウ関数、`RETURNING`を静的に検査する
- 基表の最終`SELECT *`はスキーマ不明として停止できる
- SQLGlotの方言を環境変数で指定できる

## インストール

```bash
python -m pip install .
```

開発用:

```bash
python -m pip install -e ".[dev]"
python -m pip check
python -m pytest
python scripts/run_scenarios.py
python -m build
```

## ルール例

```tsv
enabled	column_pattern	allow	action	note
1	user_id	aggregate_reduction	deny	ユーザーIDをLLMへ返さない
1	email_address	aggregate_reduction	deny	メールアドレスをLLMへ返さない
1	phone_*	aggregate_reduction	deny	電話番号系カラム
1	__SELECT_STAR__		deny	未解決の最終SELECT *を停止
```

`aggregate_reduction`はCOUNT系も含む包括指定です。COUNTだけを許可したい場合は、従来どおり`count,count_distinct,approx_count`を指定できます。

## 環境変数

| 変数 | 既定値 | 内容 |
|---|---|---|
| `MCP_SQL_RESULT_GUARD_RULES` | 同梱サンプル | TSVルールのパス |
| `MCP_SQL_RESULT_GUARD_DIALECT` | `redshift` | SQLGlotの読込方言 |
| `MCP_SQL_RESULT_GUARD_FAIL_OPEN` | `true` | 解析失敗時に警告で通す。`false`なら拒否 |

## テスト

- pytest: 194件
- SQLシナリオ: 151件
- Actions: Python 3.10〜3.13でpytest・シナリオ・パッケージビルドを実行

## 注意

これは軽量な事故防止hookです。`SUM`や`AVG`などの縮約結果でも、小さいグループ、条件を変えた反復照会、差分比較によって情報を推測できる場合があります。DB権限、マスキング、最小集計件数、MCPサーバー側の制御、監査を置き換えるものではありません。

MIT License.
