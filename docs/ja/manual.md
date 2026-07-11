# 導入・運用マニュアル

## 1. このhookの目的

`mcp-sql-result-guard`は、CodexがMCPのSQL実行ツールを呼ぶ直前にSQLを静的解析し、設定した機微カラムの値が最終結果へ流れる可能性があるときに呼出しを止めます。

禁止したいのは「SQL内での利用」ではなく「LLMへ返る値」です。

| SQLでの利用 | 標準判定 |
|---|---|
| `WHERE user_id = ...` | 許可 |
| `JOIN ... ON a.user_id = b.user_id` | 許可 |
| CTE・副問合せ内部で保持し、最終出力しない | 許可 |
| `SUM(user_id)`などの安全な縮約集約 | `aggregate_reduction`で許可されていれば許可 |
| `SELECT user_id` | 拒否 |
| `SELECT MD5(user_id)` | 拒否 |
| CTEで別名へ変えて最終出力 | 拒否 |
| CTE内部だけの危険な集約・`SELECT *` | 最終出力しなければ許可 |
| 最終結果の未解決`SELECT *` | `__SELECT_STAR__`ルールに従う |

## 2. 導入前に決めること

### 2.1 対象MCPツール

Codexのhook matcherはMCPツール名に対する正規表現です。広く`mcp__server__.*`へ掛けるより、SQLを実行するツールだけへ限定するほうが誤動作が少なくなります。

例:

```toml
matcher = "^mcp__warehouse__execute_sql$"
```

実際の名前はCodexのツール表示やhook入力ログで確認してください。

### 2.2 機微カラム

初期導入では、確実に値を返したくない列だけをTSVへ登録します。例:

- ユーザーID
- 会員ID
- メールアドレス
- 電話番号
- 端末識別子
- 注文者を一意に特定できる外部キー

### 2.3 解析失敗時の扱い

- `MCP_SQL_RESULT_GUARD_FAIL_OPEN=true`: 警告して実行を通す
- `MCP_SQL_RESULT_GUARD_FAIL_OPEN=false`: 解析できなければ拒否する

軽く始めるなら`true`、強制力が必要ならテストを積んだうえで`false`が自然です。

## 3. インストール

### 3.1 仮想環境

WSL/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
```

開発・テストも行う場合:

```bash
python -m pip install -e ".[dev]"
```

## 4. TSVルール

### 4.1 書式

タブ区切りです。UTF-8とUTF-8 BOMの両方を読めます。

```tsv
enabled	column_pattern	allow	action	note
1	user_id	aggregate_reduction	deny	ユーザーIDをLLMへ返さない
1	email_address	aggregate_reduction	deny	メールアドレスをLLMへ返さない
1	phone_*	aggregate_reduction	deny	電話番号系
1	__SELECT_STAR__		deny	未解決の最終SELECT *を停止
```

### 4.2 各列

| 列 | 内容 |
|---|---|
| `enabled` | `1`、`true`、`yes`、`on`で有効。`0`等で無効 |
| `column_pattern` | 大文字小文字を区別しない列名。`phone_*`のようなワイルドカード可 |
| `allow` | `aggregate_reduction`、`count`、`count_distinct`、`approx_count`をカンマ区切り |
| `action` | `deny`なら停止、`warn`なら警告だけ |
| `note` | Codexへ返す説明 |

通常のカラムルールは上から最初に一致した行が採用されます。個別名を上、広いワイルドカードを下へ置くと管理しやすくなります。

### 4.3 `aggregate_reduction`

```tsv
1	user_id	aggregate_reduction	deny	...
```

`aggregate_reduction`は、機微列を既知の統計値・論理値へ縮約した最終出力を許可します。

許可対象:

- `COUNT`、`COUNT(DISTINCT ...)`、近似重複除外件数
- `SUM`、`AVG`
- `STDDEV`、`STDDEV_POP`、`STDDEV_SAMP`
- `VARIANCE`、`VAR_POP`、`VAR_SAMP`
- `CORR`、`COVAR_POP`、`COVAR_SAMP`
- `BOOL_AND`、`BOOL_OR`

`aggregate_reduction`はCOUNT系を含む包括指定です。既存設定との互換性のため、`count`、`count_distinct`、`approx_count`も引き続き利用できます。

COUNT系だけを許可し、`SUM`や`AVG`を許可しない場合:

```tsv
1	user_id	count,count_distinct,approx_count	deny	...
```

### 4.4 最終出力時に拒否する集約

入力値そのもの、入力値の一つ、または入力値の集合を返しうる集約は、`aggregate_reduction`を指定していても許可しません。

- `MIN`、`MAX`、`ANY_VALUE`
- `LISTAGG`、`GROUP_CONCAT`、`STRING_AGG`
- `ARRAY_AGG`、JSON・オブジェクト集約
- `MEDIAN`、`PERCENTILE_CONT`、`PERCENTILE_DISC`、`MODE`
- 近似パーセンタイル、上位値集合
- `MIN_BY`、`MAX_BY`、`ARG_MIN`、`ARG_MAX`
- 未知の集約関数、ユーザー定義関数

安全性はallowlistで判定します。SQLGlotが集約として解析したという理由だけで一律許可はしません。

### 4.5 CTE・副問合せでの集約

判定対象はトップレベルの結果列と`RETURNING`です。中間式を作っただけでは拒否しません。

```sql
-- 許可: LISTAGG結果を作るが、最終結果へ出さない
WITH x AS (
    SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids
    FROM users
)
SELECT COUNT(*)
FROM x;
```

```sql
-- 拒否: CTEの別名を通して最終結果へ出す
WITH x AS (
    SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids
    FROM users
)
SELECT ids
FROM x;
```

同じ原則は`MIN`、`MAX`、パーセンタイル、未知の関数にも適用されます。危険な式でも出力が捨てられれば許可し、最終結果へ届けば拒否します。

### 4.6 SELECT STAR

```tsv
1	__SELECT_STAR__		deny	未解決の最終SELECT *を停止
```

- `WITH x AS (SELECT * FROM base_table) SELECT COUNT(*) FROM x`: STARの列値を最終出力しないので許可
- `WITH x AS (SELECT name, amount FROM t) SELECT * FROM x`: 派生列を追跡し、機微列がなければ許可
- `WITH x AS (SELECT user_id, amount FROM t) SELECT * FROM x`: 派生STARから機微列が最終出力されるため拒否
- `SELECT * FROM base_table`: 列構成不明なので拒否
- `SELECT COUNT(*) FROM t`: 件数なのでSTAR出力とは扱わない

## 5. Codex設定

`.codex/config.toml`へ追加します。

```toml
[features]
hooks = true

[[hooks.PreToolUse]]
matcher = "^mcp__warehouse__execute_sql$"

[[hooks.PreToolUse.hooks]]
type = "command"
command = 'MCP_SQL_RESULT_GUARD_RULES="$(git rev-parse --show-toplevel)/.codex/hooks/sensitive_columns.tsv" MCP_SQL_RESULT_GUARD_DIALECT=redshift mcp-sql-result-guard'
timeout = 10
statusMessage = "Checking the final SQL result for sensitive values"
```

プロジェクトローカルhookは、Codexでプロジェクトとhook定義を信頼した後に実行されます。hookやコマンドを変更した場合は再レビューが必要になることがあります。

### Windows

Windowsでは環境変数設定と実行をまとめた`.ps1`を用意し、`command_windows`から絶対パスで呼ぶ方式が扱いやすいです。

例 `run-sql-guard.ps1`:

```powershell
$env:MCP_SQL_RESULT_GUARD_RULES = Join-Path $PSScriptRoot "sensitive_columns.tsv"
$env:MCP_SQL_RESULT_GUARD_DIALECT = "redshift"
$env:MCP_SQL_RESULT_GUARD_FAIL_OPEN = "true"
& "$PSScriptRoot\..\..\.venv\Scripts\mcp-sql-result-guard.exe"
exit $LASTEXITCODE
```

設定例:

```toml
command_windows = 'powershell -NoProfile -ExecutionPolicy Bypass -File "C:\work\project\.codex\hooks\run-sql-guard.ps1"'
```

## 6. 動作確認

### 6.1 許可ケース

```bash
printf '%s' '{
  "hook_event_name":"PreToolUse",
  "tool_name":"mcp__warehouse__execute_sql",
  "tool_input":{"sql":"SELECT name FROM users WHERE user_id = '\''u1'\''"}
}' | MCP_SQL_RESULT_GUARD_RULES=examples/rules/sensitive_columns.tsv mcp-sql-result-guard
```

標準出力が空なら許可です。

### 6.2 拒否ケース

```bash
printf '%s' '{
  "hook_event_name":"PreToolUse",
  "tool_name":"mcp__warehouse__execute_sql",
  "tool_input":{"sql":"SELECT user_id FROM users"}
}' | MCP_SQL_RESULT_GUARD_RULES=examples/rules/sensitive_columns.tsv mcp-sql-result-guard
```

`permissionDecision: deny`を含むJSONが返ります。

## 7. テスト

```bash
python -m pip check
python -m pytest
python scripts/run_scenarios.py
python -m build
```

現在の構成では:

- pytest 194件
- SQLシナリオ 151件

シナリオは`tests/data/sql_scenarios.tsv`にあり、期待値とSQLを一覧できます。

## 8. 運用手順

### カラム追加

1. TSVへ行を追加
2. ローカルでpytestとシナリオを実行
3. `warn`で観測したい場合はactionを変更
4. コードレビュー
5. 配布・反映
6. Codexでhook定義を再レビュー

### バージョン更新

依存ライブラリSQLGlotの更新は解析結果を変える可能性があります。バージョン更新時は151シナリオを必ず再実行し、方言固有SQLも追加してください。

### 監査向けに残す情報

- リポジトリのコミットSHA
- TSVルールのコミットSHA
- PythonとSQLGlotのバージョン
- pytest・シナリオ結果
- Codex matcher
- fail-open / fail-closed設定

## 9. よくある問題

### hookが動かない

- `[features] hooks = true`を確認
- プロジェクトが信頼済みか確認
- matcherが実際のMCPツール名と一致するか確認
- コマンドをターミナルから単独実行
- Codexをサブディレクトリから起動する場合はgit root基準のパスを使う

### SQLが見つからない

hookはMCP引数内の`sql`、`query`、`statement`というキーを再帰的に探します。別名キーを使うMCPでは`SQL_ARGUMENT_KEYS`の拡張が必要です。

### 方言エラー

```text
MCP_SQL_RESULT_GUARD_DIALECT=redshift
```

を実際のDBに合わせます。ただし、リポジトリの回帰テストはRedshift中心です。他方言は固有シナリオを追加してから運用してください。

### 集約関数が拒否された

- TSVの`allow`に`aggregate_reduction`があるか確認
- 関数が安全な縮約allowlistに含まれるか確認
- `MIN`、`MAX`、列挙集約、パーセンタイル、未知関数は最終出力時に拒否される
- 中間処理だけなら、最終SELECTがその列を参照していないか確認

### SELECT *を許可したい

`__SELECT_STAR__`行を無効化できます。ただし基表STARに機微列が含まれるかSQLだけでは判断できなくなります。

## 10. 会社への持込み・レビュー用チェック

- [ ] 実在のテーブル名、社内SQL、社内パスが公開物に含まれていない
- [ ] TSVサンプルが架空の列名になっている
- [ ] MITライセンスと依存ライセンスを確認した
- [ ] GitHub Actionsまたは社内CIでテストを再実行した
- [ ] コミットSHAを固定した
- [ ] PyPI等ではなく社内ミラーやソースから再ビルドする方針を決めた
- [ ] DB権限やマスキングの代替ではないと合意した
- [ ] fail-open設定をリスクに合わせて決めた
