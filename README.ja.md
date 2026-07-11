# mcp-sql-result-guard

[![test](https://github.com/rio123dx/mcp-sql-result-guard/actions/workflows/test.yml/badge.svg)](https://github.com/rio123dx/mcp-sql-result-guard/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

MCP SQLツールの最終結果から、設定した機微値がLLMへ届く可能性がある呼出しを停止する、軽量なCodex `PreToolUse`ガードレールです。

バージョン`0.2.0`向けの文書です。[English](README.md)

## 解決する問題

LLMにSQL分析を任せたいが、識別子などの生値をモデルへ返したくない。一方で、識別子を検索、結合、グループ化、並べ替え、件数集計に利用することまでは妨げたくない――この両立が本プロジェクトの目的です。

`mcp-sql-result-guard`は、**SQL内部での利用**と**値の出力**を分けて扱います。トップレベルの結果列またはDML `RETURNING`から値の流れを逆向きに追跡し、設定した列名にTSVポリシーを適用します。

主な想定読者は、データエンジニア、アナリティクスエンジニア、データプラットフォームエンジニア、およびLLMエージェントとデータウェアハウスをMCPで接続する開発者です。

## 代表的な判定

`user_id`が機微列として登録され、`aggregate_reduction`が許可されているとします。

| SQLパターン | 判定 | 理由 |
|---|---|---|
| `SELECT order_total FROM orders WHERE user_id IS NOT NULL` | 許可 | `user_id`は絞込みに使われるだけで、返されません。 |
| `SELECT SUM(user_id) FROM orders` | 許可 | `SUM`は明示的に許可された縮約です。 |
| `SELECT MIN(user_id) FROM orders` | 拒否 | `MIN`は入力値の一つを選択します。 |
| `SELECT MD5(user_id) FROM orders` | 拒否 | `user_id`由来の値が結果へ届きます。 |
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

## Quick start

現時点では、cloneしたソースツリーからインストールします。以下の例はPyPI配布を前提にしていません。matcherは、利用環境でCodexに表示されるMCP SQL実行ツールの正確な名前へ置き換えてください。

### WSL／Linux

リポジトリをcloneし、Python 3.10以上の仮想環境を作成して、ソースからインストールします。続いてサンプルのTSVとhook設定をプロジェクトへコピーします。

```bash
git clone https://github.com/rio123dx/mcp-sql-result-guard.git
cd mcp-sql-result-guard

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .

mkdir -p .codex/hooks
cp examples/rules/sensitive_columns.tsv .codex/hooks/sensitive_columns.tsv
cp examples/codex/config.toml .codex/config.toml
```

`.codex/config.toml`を開き、次の仮のmatcherを実際のMCP SQL実行ツール名へ置き換えます。

```toml
matcher = "^mcp__warehouse__execute_sql$"
```

標準入力から、許可SQLと拒否SQLをsmoke testします。

```bash
export MCP_SQL_RESULT_GUARD_RULES="$PWD/.codex/hooks/sensitive_columns.tsv"
export MCP_SQL_RESULT_GUARD_DIALECT=redshift
export MCP_SQL_RESULT_GUARD_FAIL_OPEN=true

printf '%s' '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT order_total FROM orders WHERE user_id IS NOT NULL"}}' \
  | ./.venv/bin/mcp-sql-result-guard

printf '%s' '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT user_id FROM orders"}}' \
  | ./.venv/bin/mcp-sql-result-guard
```

1つ目は標準出力が空になり、2つ目は`permissionDecision: "deny"`を含むJSONを返すのが期待結果です。

### Windows PowerShell

```powershell
git clone https://github.com/rio123dx/mcp-sql-result-guard.git
Set-Location mcp-sql-result-guard

py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install .

New-Item -ItemType Directory -Force .codex\hooks | Out-Null
Copy-Item examples\rules\sensitive_columns.tsv .codex\hooks\sensitive_columns.tsv
Copy-Item examples\codex\config.toml .codex\config.toml
Copy-Item examples\codex\run-sql-guard.ps1 .codex\hooks\run-sql-guard.ps1
```

`.codex\config.toml`のmatcherを実際のMCP SQL実行ツール名へ変更し、2つの判定をsmoke testします。

```powershell
$env:MCP_SQL_RESULT_GUARD_RULES = (Resolve-Path .codex\hooks\sensitive_columns.tsv)
$env:MCP_SQL_RESULT_GUARD_DIALECT = "redshift"
$env:MCP_SQL_RESULT_GUARD_FAIL_OPEN = "true"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$allow = '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT order_total FROM orders WHERE user_id IS NOT NULL"}}'
$allow | & .\.venv\Scripts\mcp-sql-result-guard.exe

$deny = '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT user_id FROM orders"}}'
$deny | & .\.venv\Scripts\mcp-sql-result-guard.exe
```

1つ目は標準出力が空になり、2つ目はdeny JSONを返すのが期待結果です。

### hookの有効化とレビュー

Codexは`.codex/config.toml`からプロジェクトhookを読み込みます。利用前に、コピーしたhook定義をCodex上でレビューして信頼してください。matcherはツール名に対する正規表現なので、MCP全体ではなくSQL実行ツールだけへ限定します。

解析失敗時の扱いも明示的に選択します。

- `MCP_SQL_RESULT_GUARD_FAIL_OPEN=true`（既定）: SQLまたはルールを解析できない場合、警告して許可します。
- `MCP_SQL_RESULT_GUARD_FAIL_OPEN=false`: 解析を完了できない場合に拒否します。

hookの探索、信頼レビュー、matcher、`PreToolUse`出力については[Codex hooksドキュメント](https://developers.openai.com/codex/hooks)を参照してください。

## 最小TSVルール

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
| DML `RETURNING` | 最終結果と同様に検査します。 |
| 複数の設定列 | 一致した各値経路を報告します。 |
| SQL・設定の解析失敗 | `MCP_SQL_RESULT_GUARD_FAIL_OPEN`に従い、警告して許可または拒否します。 |

実行可能な全マトリクスは[tests/data/sql_scenarios.tsv](tests/data/sql_scenarios.tsv)にあります。156シナリオの内訳は、allow 86件、deny 70件です。

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

- pytest: **199 passed / 199**
- SQLシナリオ: **156 passed / 156**
- expected allow: **86**
- expected deny: **70**

## ライセンス

MIT。詳細は[LICENSE](LICENSE)を参照してください。
