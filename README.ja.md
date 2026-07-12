# mcp-sql-result-guard

[![test](https://github.com/rio123dx/mcp-sql-result-guard/actions/workflows/test.yml/badge.svg)](https://github.com/rio123dx/mcp-sql-result-guard/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

MCP SQLツールの最終結果から、設定した機微値がLLMへ届く可能性がある呼出しを停止する、軽量なCodex `PreToolUse`ガードレールです。

バージョン`0.2.0`向けの文書です。[English](README.md)

## 解決する問題

LLMにSQL分析を任せたいが、識別子などの生値をモデルへ返したくない。一方で、識別子を検索、結合、グループ化、並べ替え、件数集計に利用することまでは妨げたくない――`mcp-sql-result-guard`は、この両立を支える軽量なガードレールです。

`mcp-sql-result-guard`は、**SQL内部での利用**と**値の出力**を分けて扱います。トップレベルの結果列またはDML `RETURNING`から値の流れを逆向きに追跡し、設定した列名にTSVポリシーを適用します。

## 代表的な判定

`user_id`が機微列として登録され、`aggregate_reduction`が許可されているとします。

| SQLパターン | 判定 | 理由 |
|---|---|---|
| `SELECT order_total FROM orders WHERE user_id IS NOT NULL` | 許可 | `user_id`は絞込みに使われるだけで、返されません。 |
| `SELECT SUM(user_id) FROM orders` | 許可 | `SUM`は明示的に許可された縮約です。 |
| `SELECT MIN(user_id) FROM orders` | 拒否 | `MIN`は入力値の一つを選択します。 |
| `SELECT MD5(user_id) FROM orders` | 拒否 | `user_id`由来の値が結果へ届きます。 |
| `WITH x AS (SELECT user_id FROM users) INSERT INTO archive SELECT user_id FROM x` | 許可 | INSERT入力は書込み先へ保存され、MCP結果セットには返されません。 |
| `UPDATE orders SET reviewed = true RETURNING user_id` | 拒否 | `RETURNING`が機微値を返します。 |

同じ出力指向の原則はCTEにも適用されます。

```sql
-- 許可: LISTAGGの結果を最終結果より前に捨てる
WITH collected AS (
    SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids
    FROM orders
)
SELECT COUNT(*)
FROM collected;
```

```sql
-- 拒否: 収集した値がCTEの別名を通って最終結果へ届く
WITH collected AS (
    SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids
    FROM orders
)
SELECT ids
FROM collected;
```

## Quick Start

1. Python 3.10以上を使い、Codexから見える`PATH`へCLIをインストールします。hookは`mcp-sql-result-guard`をコマンド名で起動します。

   ```bash
   python -m pip install "git+https://github.com/rio123dx/mcp-sql-result-guard.git@v0.2.0"
   ```

   hook設定前に、WSL／Linuxでは`command -v mcp-sql-result-guard`、Windows PowerShellでは`Get-Command mcp-sql-result-guard`でコマンドを解決できることを確認します。

2. 利用するプロジェクトに`.codex/hooks/sensitive_columns.tsv`を作成します。

   ```tsv
   enabled	column_pattern	allow	action	note
   1	user_id	aggregate_reduction	deny	ユーザー識別子をモデルへ返さない
   1	__SELECT_STAR__		deny	未解決の最終SELECT *を拒否する
   ```

3. `.codex/config.toml`へhook設定を追加します。

   ```toml
   [features]
   hooks = true

   [[hooks.PreToolUse]]
   matcher = "^mcp__warehouse__execute_sql$"

   [[hooks.PreToolUse.hooks]]
   type = "command"
   command = 'MCP_SQL_RESULT_GUARD_RULES="$(git rev-parse --show-toplevel)/.codex/hooks/sensitive_columns.tsv" MCP_SQL_RESULT_GUARD_DIALECT=redshift MCP_SQL_RESULT_GUARD_FAIL_OPEN=true mcp-sql-result-guard'
   command_windows = "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& (Join-Path (git rev-parse --show-toplevel) '.codex\\hooks\\run-sql-guard.ps1')\""
   timeout = 10
   statusMessage = "Checking SQL result columns for configured sensitive values"
   ```

   Windowsでは、[サンプルwrapper](examples/codex/run-sql-guard.ps1)を`.codex/hooks/run-sql-guard.ps1`として保存します。

4. `matcher`を実際のMCP SQL実行ツール名へ変更し、Codexでproject-local hookをレビューして信頼します。

Codexが対象MCPツールを呼ぶ直前にSQLを静的解析し、拒否判定ならMCP呼出し前に停止します。[動作確認](docs/ja/manual.md#81-hook単体のsmoke-test)を行ってから利用してください。

### fail-open／fail-closedとhookの適用範囲

matcherはツール名に対する正規表現なので、MCP全体ではなくSQL実行ツールだけへ限定します。

解析失敗時の扱いも明示的に選択します。

- `MCP_SQL_RESULT_GUARD_FAIL_OPEN=true`（既定）: SQLまたはルールを解析できない場合、警告して許可します。
- `MCP_SQL_RESULT_GUARD_FAIL_OPEN=false`: 解析を完了できない場合に拒否します。

hookの探索、信頼レビュー、matcher、`PreToolUse`出力については[Codex hooksドキュメント](https://developers.openai.com/codex/hooks)を参照してください。

## TSV保護ルール

ルールはUTF-8のタブ区切りです。[サンプルポリシー](examples/rules/sensitive_columns.tsv)をプロジェクトで管理するパスへコピーし、架空のパターンを実際に保護したい列へ置き換えます。

```tsv
enabled	column_pattern	allow	action	note
1	user_id	aggregate_reduction	deny	ユーザー識別子をモデルへ返さない
1	email_address	aggregate_reduction	deny	メールアドレスをモデルへ返さない
1	__SELECT_STAR__		deny	未解決の最終SELECT *を拒否する
```

| 列 | 内容 |
|---|---|
| `enabled` | `1`、`true`、`yes`、`on`で有効になります。 |
| `column_pattern` | 大文字小文字を区別しない列名パターンです。`*`ワイルドカードを利用できます。 |
| `allow` | `aggregate_reduction`、`count`、`count_distinct`、`approx_count`をカンマ区切りで指定します。 |
| `action` | `deny`は呼出しを停止し、`warn`はモデルへ文脈を追加して許可します。 |
| `note` | hookの応答へ含める説明です。 |

通常の列ルールは上から評価され、最初に一致した行が採用されます。`__SELECT_STAR__`は、最終結果に残る未解決の基表STAR向けの特別ルールです。

## 判定モデルの概要

SQLGlotでSQLを解析し、最終結果列または`RETURNING`から、別名、CTE、副問合せ、集合演算、関数、集約を通る値の経路を逆向きに追跡します。

`aggregate_reduction`が許可するのは、次の既知の縮約だけです。

- `COUNT`、`COUNT(DISTINCT ...)`、近似重複除外件数
- `SUM`、`AVG`
- `STDDEV`、`STDDEV_POP`、`STDDEV_SAMP`
- `VARIANCE`、`VAR_POP`、`VAR_SAMP`
- `CORR`、`COVAR_POP`、`COVAR_SAMP`
- `BOOL_AND`、`BOOL_OR`

次は値を保持しうるため、設定した入力が最終出力へ届く場合は拒否します。

- `MIN`、`MAX`、`ANY_VALUE`
- `LISTAGG`、`GROUP_CONCAT`、`STRING_AGG`
- `ARRAY_AGG`、JSON／オブジェクト収集集約
- `MEDIAN`、`PERCENTILE_CONT`、`PERCENTILE_DISC`、`MODE`
- 近似パーセンタイル、top-k関数
- `MIN_BY`、`MAX_BY`、`ARG_MIN`、`ARG_MAX`
- 未知の集約関数、UDF相当の呼出し

判定はallowlist方式です。未知の集約を安全とは見なしません。件数だけを許可し、より広い縮約を許可しない場合は、従来の`count`、`count_distinct`、`approx_count`を利用できます。

## 主な対応ケース

| グループ | 挙動 |
|---|---|
| `WHERE`、`JOIN`、`GROUP BY`、`ORDER BY`、述語 | 設定列が計算の制御だけに使われる場合は許可します。 |
| CTE・副問合せ | 中間値は利用後に捨てられます。最終出力へ届く別名・射影は追跡します。 |
| 安全な縮約 | 一致するTSVルールが必要なmaskを許可している場合だけ許可します。 |
| 生値、ハッシュ、cast、連結、部分文字列 | 値由来の情報が結果へ届くため拒否します。 |
| 値選択・値収集型の集約 | `aggregate_reduction`があっても、最終出力では拒否します。 |
| `UNION`、`INTERSECT`、`EXCEPT` | 出力に関わる各分岐を検査します。 |
| 派生表の`SELECT *` | 既知の射影を展開して検査します。 |
| 未解決の最終基表`SELECT *` | `__SELECT_STAR__`に従います。 |
| INSERT入力 | 生値、加工値、CTE、副問合せ、`VALUES`を含め、書込み先へ保存するだけなら許可します。 |
| DML `RETURNING` | 最終結果と同様に検査します。 |
| 複数の設定列 | 一致した各値経路を報告します。 |
| SQL・設定の解析失敗 | `MCP_SQL_RESULT_GUARD_FAIL_OPEN`に従い、警告して許可または拒否します。 |

実行可能なマトリクスは[基本シナリオ](tests/data/sql_scenarios.tsv)と[INSERTシナリオ](tests/data/insert_scenarios.tsv)にあります。合計164シナリオの内訳は、allow 93件、deny 71件です。

## 制約とセキュリティ境界

本プロジェクトはbest-effortの実行前ガードレールです。機密性を保証するものではなく、次の代替にはなりません。

- DBロールの最小権限化
- カラムマスキング、行／列レベルセキュリティ
- MCPサーバー側の認可・SQLポリシー
- 最小集団サイズ、privacy budgetなどの制御
- SQL・結果の監査ログ
- 実行後の結果フィルタリング

許可した集約でも、小集団、反復照会、差分、外部知識との組合せから情報が推測される場合があります。UDF、ストアドプロシージャ、動的SQL、`UNLOAD`、外部出力、副作用、別ツールを経由する同等アクセスは、信頼できる保護範囲の外です。既定かつ主な回帰テスト方言はRedshiftです。他方言へ依存する前に、方言固有シナリオを追加してください。

本番導入前に[制約と脅威モデル](docs/limitations.md)と[セキュリティポリシー](SECURITY.md)を確認してください。

## 詳細文書

- [日本語導入・運用マニュアル](docs/ja/manual.md)
- [アーキテクチャ](docs/architecture.md)
- [制約と脅威モデル](docs/limitations.md)
- [セキュリティポリシー](SECURITY.md)
- [回帰テストレポート](docs/test-report.md)
- [サンプル一覧](examples/README.md)
- [コントリビューションガイド](CONTRIBUTING.md)

## 開発・テスト

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip check
python -m pytest
python scripts/run_scenarios.py
python -m build
```

現在の回帰テスト数:

- pytest: **209 passed / 209**
- SQLシナリオ: **164 passed / 164**
- expected allow: **93**
- expected deny: **71**

## ライセンス

MIT。詳細は[LICENSE](LICENSE)を参照してください。
