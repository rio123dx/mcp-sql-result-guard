# mcp-sql-result-guard

SQLの中で機微カラムを使うこと自体は妨げず、**MCPがLLMへ返す最終結果列に機微値が流れる可能性があるときだけ停止する**Codex `PreToolUse` hookです。

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
-- 拒否: user_idの値を最終結果へ返す
SELECT user_id
FROM orders;
```

```sql
-- 許可: CTE内では保持するが最終出力しない
WITH scoped AS (
    SELECT user_id, amount
    FROM orders
)
SELECT SUM(amount)
FROM scoped;
```

```sql
-- 拒否: 別名にしても値の経路を追う
WITH scoped AS (
    SELECT user_id AS internal_key
    FROM orders
)
SELECT internal_key
FROM scoped;
```

## 特徴

- 機微カラムをTSVへ追加できる
- `COUNT`、`COUNT DISTINCT`、近似件数をカラム単位で許可できる
- `deny`と`warn`を選べる
- CTE、副問合せ、多段別名、UNION、ウィンドウ関数、`RETURNING`を静的に検査する
- 基表の最終`SELECT *`はスキーマ不明として停止できる
- SQLGlotの方言を環境変数で指定できる
- Codex hookの標準入力・標準出力形式を結合テストしている

## インストール

```bash
python -m pip install .
```

開発用:

```bash
python -m pip install -e ".[dev]"
python -m pytest
python scripts/run_scenarios.py
```

## ルール例

```tsv
enabled	column_pattern	allow	action	note
1	user_id	count,count_distinct,approx_count	deny	ユーザーIDをLLMへ返さない
1	email_address	count,count_distinct,approx_count	deny	メールアドレスをLLMへ返さない
1	phone_*	count,count_distinct	deny	電話番号系カラム
1	__SELECT_STAR__		deny	未解決の最終SELECT *を停止
```

## 環境変数

| 変数 | 既定値 | 内容 |
|---|---|---|
| `MCP_SQL_RESULT_GUARD_RULES` | 同梱サンプル | TSVルールのパス |
| `MCP_SQL_RESULT_GUARD_DIALECT` | `redshift` | SQLGlotの読込方言 |
| `MCP_SQL_RESULT_GUARD_FAIL_OPEN` | `true` | 解析失敗時に警告で通す。`false`なら拒否 |

## テスト

- pytest: 150件
- SQLシナリオ: 117件

Redshift方言を中心に回帰テストしています。その他の方言は、利用前に固有構文のテスト追加を推奨します。

## 注意

これは軽量な事故防止hookです。DB権限、マスキング、MCPサーバー側の制御、監査を置き換えるものではありません。また、特定IDの存在推測や集計結果からの再識別まで防ぐ設計ではありません。

MIT License.
