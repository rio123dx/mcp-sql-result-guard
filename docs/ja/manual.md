# 導入・運用マニュアル

対象バージョン: `0.2.0`

## 1. このツールが解決する問題

LLMにSQL分析を任せたいが、識別子などの生値をモデルへ返したくない。一方で、識別子を検索、結合、グループ化、並べ替え、件数集計に利用することまでは妨げたくない――`mcp-sql-result-guard`は、この両立を支える軽量なガードレールです。

CodexがMCP SQLツールを呼ぶ直前に`PreToolUse` hookとして動作し、SQLGlotによる静的解析を行います。判定は、SQLに機微列名が現れるかどうかではなく、設定した列の値または値由来の情報が、トップレベルの結果列やDML `RETURNING`へ届く可能性があるかどうかに基づきます。

主な利用者は次のような技術者です。

- データエンジニア
- アナリティクスエンジニア
- データプラットフォームエンジニア
- LLM／MCPとデータウェアハウスを接続する開発者
- SQL実行エージェントへ軽量な出力ガードレールを追加したい利用者

## 2. 保護対象と保護対象外

### 2.1 保護対象

設定した機微列について、次の経路を通って最終結果へ届く値を検査します。

- 直接の結果列
- cast、ハッシュ、部分文字列、連結、算術式などの加工値
- CTE・副問合せ・別名を通る値
- `UNION`、`INTERSECT`、`EXCEPT`の各出力分岐
- 値を選択・収集する集約結果
- ウィンドウ関数やスカラー副問合せの出力
- DML `RETURNING`
- 派生表の`SELECT *`から展開できる既知の列
- 未解決の最終基表`SELECT *`（`__SELECT_STAR__`ルール）

### 2.2 SQL内部で許可する利用

機微列が最終結果へ値として届かない場合、次の用途は原則として許可します。

- `WHERE`
- `JOIN ON`／`JOIN USING`
- `GROUP BY`
- 通常の`ORDER BY`
- `HAVING`、`QUALIFY`、`EXISTS`、述語
- `CASE`／`IF`の条件
- CTE・副問合せの中間処理
- ウィンドウの`PARTITION BY`、`ORDER BY`、frame
- 集約の`FILTER`条件
- TSVで許可した既知の縮約集約

### 2.3 保護対象外

このツールは、MCP SQLツールの通常の結果セットへ値が流れる経路を対象にした、best-effortの実行前ガードレールです。次は保護範囲外です。

- DB権限、ロール、行／列レベルセキュリティの代替
- DBやMCP側のマスキング、認可、監査の代替
- UDF、ストアドプロシージャ、動的SQL、macroの内部動作
- `UNLOAD`、外部ファイル出力、任意の副作用
- 別のMCPツール、shell、DBクライアントを通る同等アクセス
- prompt、エラー、ログ、MCP metadataに既に含まれる値
- 小集団、反復照会、差分、外部知識からの推測

## 3. 事前要件

- Python 3.10以上
- Git
- Codexのproject-local設定を利用できる環境
- SQLを引数として受け取るMCPツール
- 保護したい列名パターンを決められること
- 利用DBのSQL方言と代表クエリをテストできること

既定・主要テスト方言はAmazon Redshiftです。SQLGlotが対応する別方言も指定できますが、導入前に方言固有のシナリオを追加してください。

## 4. Quick start

現時点ではcloneしたソースからインストールします。PyPI配布済みであることを前提にしません。

### 4.1 WSL／Linux

#### 1. cloneとインストール

```bash
git clone https://github.com/rio123dx/mcp-sql-result-guard.git
cd mcp-sql-result-guard

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

#### 2. TSVとCodex設定をコピー

```bash
mkdir -p .codex/hooks
cp examples/rules/sensitive_columns.tsv .codex/hooks/sensitive_columns.tsv
cp examples/codex/config.toml .codex/config.toml
```

#### 3. matcherを変更

`.codex/config.toml`を開き、仮のツール名を、Codexに表示される実際のMCP SQL実行ツール名へ置き換えます。

```toml
matcher = "^mcp__warehouse__execute_sql$"
```

matcherはツール名に対する正規表現です。SQLを実行しないMCPツールまで含めないでください。

#### 4. 標準入力からsmoke test

```bash
export MCP_SQL_RESULT_GUARD_RULES="$PWD/.codex/hooks/sensitive_columns.tsv"
export MCP_SQL_RESULT_GUARD_DIALECT=redshift
export MCP_SQL_RESULT_GUARD_FAIL_OPEN=true

printf '%s' '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT order_total FROM orders WHERE user_id IS NOT NULL"}}' \
  | ./.venv/bin/mcp-sql-result-guard

printf '%s' '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT user_id FROM orders"}}' \
  | ./.venv/bin/mcp-sql-result-guard
```

最初のコマンドは標準出力が空になり、2つ目は`permissionDecision: "deny"`を含むJSONを返します。

### 4.2 Windows PowerShell

#### 1. cloneとインストール

```powershell
git clone https://github.com/rio123dx/mcp-sql-result-guard.git
Set-Location mcp-sql-result-guard

py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install .
```

#### 2. TSV、Codex設定、wrapperをコピー

```powershell
New-Item -ItemType Directory -Force .codex\hooks | Out-Null
Copy-Item examples\rules\sensitive_columns.tsv .codex\hooks\sensitive_columns.tsv
Copy-Item examples\codex\config.toml .codex\config.toml
Copy-Item examples\codex\run-sql-guard.ps1 .codex\hooks\run-sql-guard.ps1
```

`.codex\config.toml`のmatcherを、実際のMCP SQL実行ツール名へ変更します。

#### 3. 標準入力からsmoke test

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

最初のコマンドは標準出力が空になり、2つ目はdeny JSONを返します。

### 4.3 fail-open／fail-closedを選択

- `MCP_SQL_RESULT_GUARD_FAIL_OPEN=true`（既定）: SQLまたはTSVを解析できない場合、警告してツール呼出しを許可します。
- `MCP_SQL_RESULT_GUARD_FAIL_OPEN=false`: 解析を完了できない場合にツール呼出しを拒否します。

導入初期は代表SQLを増やしながらfail-openで観測し、強い制御が必要な場合は、方言テストと運用手順を整備したうえでfail-closedを検討します。

## 5. TSVルールの設計

### 5.1 最小構成

ルールファイルはUTF-8のタブ区切りです。UTF-8 BOMも読み取れます。

```tsv
enabled	column_pattern	allow	action	note
1	user_id	aggregate_reduction	deny	ユーザー識別子をモデルへ返さない
1	email_address	aggregate_reduction	deny	メールアドレスをモデルへ返さない
1	phone_*	aggregate_reduction	deny	電話番号系の値をモデルへ返さない
1	__SELECT_STAR__		deny	未解決の最終SELECT *を拒否する
```

### 5.2 各列

| 列 | 内容 |
|---|---|
| `enabled` | `1`、`true`、`yes`、`on`で有効。`0`、`false`、`no`、`off`、空文字で無効 |
| `column_pattern` | 大文字小文字を区別しない列名パターン。`phone_*`のようなワイルドカード可 |
| `allow` | `aggregate_reduction`、`count`、`count_distinct`、`approx_count`をカンマ区切りで指定 |
| `action` | `deny`は停止、`warn`はモデルへ追加文脈を返して許可 |
| `note` | 判定理由へ加える説明 |

通常の列ルールは上から評価され、最初に一致した行が採用されます。個別パターンを上、広いワイルドカードを下へ置くと意図を追いやすくなります。

### 5.3 `aggregate_reduction`

`aggregate_reduction`は、次の既知の縮約を最終結果へ返すことを許可します。

- `COUNT`、`COUNT(DISTINCT ...)`、近似重複除外件数
- `SUM`、`AVG`
- `STDDEV`、`STDDEV_POP`、`STDDEV_SAMP`
- `VARIANCE`、`VAR_POP`、`VAR_SAMP`
- `CORR`、`COVAR_POP`、`COVAR_SAMP`
- `BOOL_AND`、`BOOL_OR`

COUNT系だけを許可し、`SUM`や`AVG`を許可しない場合は、従来のmaskを指定します。

```tsv
1	user_id	count,count_distinct,approx_count	deny	件数だけを許可する
```

### 5.4 最終出力で拒否する集約

入力値そのもの、入力値の一つ、または入力値の集合を返しうる集約は、`aggregate_reduction`を指定していても最終出力で拒否します。

- `MIN`、`MAX`、`ANY_VALUE`
- `LISTAGG`、`GROUP_CONCAT`、`STRING_AGG`
- `ARRAY_AGG`、JSON／オブジェクト集約
- `MEDIAN`、`PERCENTILE_CONT`、`PERCENTILE_DISC`、`MODE`
- 近似パーセンタイル、top-k関数
- `MIN_BY`、`MAX_BY`、`ARG_MIN`、`ARG_MAX`
- 未知の集約関数、UDF相当の呼出し

安全性はallowlistで判定します。未知の集約を自動的には許可しません。

### 5.5 `__SELECT_STAR__`

SQLだけでは基表の列構成を解決できないため、最終結果に残る未解決の基表`SELECT *`は特別ルールで制御します。

```tsv
1	__SELECT_STAR__		deny	未解決の最終SELECT *を拒否する
```

`SELECT COUNT(*)`は行数を返す集約であり、STARの列値出力とは扱いません。

## 6. Codex hookの設定

サンプルの[examples/codex/config.toml](../../examples/codex/config.toml)は、project-localな`.codex/config.toml`へコピーして使います。

```toml
[features]
hooks = true

[[hooks.PreToolUse]]
matcher = "^mcp__warehouse__execute_sql$"

[[hooks.PreToolUse.hooks]]
type = "command"
command = 'MCP_SQL_RESULT_GUARD_RULES="$(git rev-parse --show-toplevel)/.codex/hooks/sensitive_columns.tsv" MCP_SQL_RESULT_GUARD_DIALECT=redshift MCP_SQL_RESULT_GUARD_FAIL_OPEN=true "$(git rev-parse --show-toplevel)/.venv/bin/mcp-sql-result-guard"'
command_windows = "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& (Join-Path (git rev-parse --show-toplevel) '.codex\\hooks\\run-sql-guard.ps1')\""
timeout = 10
statusMessage = "Checking SQL result columns for configured sensitive values"
```

### 6.1 matcher

`PreToolUse`ではmatcherがツール名へ適用されます。正規表現をSQL実行ツールだけへ限定し、必要な場合は複数のSQLツール名を明示的に列挙します。

```toml
matcher = "^(mcp__warehouse__execute_sql|mcp__analytics__run_query)$"
```

### 6.2 SQL引数の検出

hookはMCPの`tool_input`を再帰的に調べ、`sql`、`query`、`statement`というキーの非空文字列をSQL候補として扱います。利用中のMCPが別のキーを使う場合は、現状のままでは検査対象になりません。

### 6.3 信頼レビュー

project-local hookは、プロジェクトの`.codex/`設定が信頼され、hook定義自体がレビューされてから実行されます。hookコマンドを変更した場合は再レビューが必要です。

Codex hookの現行仕様は[公式hooksドキュメント](https://developers.openai.com/codex/hooks)で確認してください。

## 7. 判定例

以下はすべて架空のテーブル名・列名です。`user_id`は`aggregate_reduction`付きで機微列に登録されているとします。

### 7.1 WHERE／JOIN／GROUP BYでの内部利用

```sql
-- 許可: user_idは絞込みだけに利用
SELECT order_total
FROM orders
WHERE user_id IS NOT NULL;
```

```sql
-- 許可: user_idは結合とグループ化に利用し、返すのは件数
SELECT COUNT(*)
FROM orders AS o
JOIN customer_segments AS s USING (user_id)
GROUP BY s.segment_name;
```

### 7.2 安全な縮約と値選択集約

```sql
-- 許可: aggregate_reduction設定時
SELECT SUM(user_id)
FROM orders;
```

```sql
-- 拒否: MINは入力値の一つを返しうる
SELECT MIN(user_id)
FROM orders;
```

### 7.3 CTE内部のLISTAGG

```sql
-- 許可: LISTAGG結果を作るが、最終出力前に捨てる
WITH collected AS (
    SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids
    FROM orders
)
SELECT COUNT(*)
FROM collected;
```

```sql
-- 拒否: CTEの別名からLISTAGG結果を最終出力
WITH collected AS (
    SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids
    FROM orders
)
SELECT ids
FROM collected;
```

### 7.4 中間STARと最終STAR

```sql
-- 許可: 基表STARを中間で使い、最終結果は件数へ縮約
WITH scoped AS (
    SELECT *
    FROM orders
    WHERE user_id IS NOT NULL
)
SELECT COUNT(*)
FROM scoped;
```

```sql
-- 拒否: 派生STARからuser_idが最終出力へ届く
WITH scoped AS (
    SELECT user_id, order_total
    FROM orders
)
SELECT *
FROM scoped;
```

`SELECT * FROM orders`のような未解決の最終基表STARは、`__SELECT_STAR__`ルールに従います。

### 7.5 生値・加工値

```sql
-- 拒否: 生値
SELECT user_id
FROM orders;
```

```sql
-- 拒否: ハッシュもuser_id由来の値
SELECT MD5(user_id)
FROM orders;
```

cast、部分文字列、連結、算術式なども同じように値経路を追跡します。

### 7.6 CTE・別名・UNIONを通る伝播

```sql
-- 拒否: 多段別名でも元の機微列まで追跡
WITH first_step AS (
    SELECT user_id AS key_a FROM orders
), second_step AS (
    SELECT key_a AS key_b FROM first_step
)
SELECT key_b
FROM second_step;
```

```sql
-- 拒否: UNIONの一方の分岐から値が届く
SELECT order_name FROM orders
UNION ALL
SELECT user_id FROM archived_orders;
```

### 7.7 RETURNINGと複数の機微列

```sql
-- 拒否: RETURNINGも最終結果として検査
UPDATE orders
SET reviewed = true
RETURNING user_id;
```

複数の機微列をTSVへ登録した場合、最終結果へ届く各列を検査し、判定理由へまとめます。

### 7.8 fail-open／fail-closed

SQL parse error、方言差、TSVの書式不正などで解析を完了できない場合、`MCP_SQL_RESULT_GUARD_FAIL_OPEN`が判定を決めます。

| 設定 | 解析失敗時の挙動 |
|---|---|
| `true` | 警告して許可 |
| `false` | 拒否 |

## 8. 動作確認

### 8.1 hook単体のsmoke test

Quick startの標準入力例を使い、次を確認します。

- WHEREだけで機微列を使うSQLは標準出力なし
- 機微列を直接返すSQLはdeny JSON
- `MCP_SQL_RESULT_GUARD_FAIL_OPEN`が意図した値
- `MCP_SQL_RESULT_GUARD_DIALECT`が利用DB方言と一致
- TSVがコピー先から読み込まれている

### 8.2 回帰テスト

開発用依存をインストールして実行します。

```bash
python -m pip install -e ".[dev]"
python -m pip check
python -m pytest
python scripts/run_scenarios.py
python -m build
```

現在の正しい件数は次のとおりです。

- pytest: **199 passed / 199**
- SQLシナリオ: **156 passed / 156**
- expected allow: **86**
- expected deny: **70**

実行可能なSQLマトリクスは[tests/data/sql_scenarios.tsv](../../tests/data/sql_scenarios.tsv)にあります。

## 9. 運用とルール更新

### 9.1 列パターンを追加する

1. TSVへ列パターンを追加する
2. 代表的なallow／deny SQLをシナリオへ追加する
3. pytestとSQLシナリオを実行する
4. matcherとfail-open／fail-closed設定をレビューする
5. TSVとhook設定を同じ変更管理手順で反映する

### 9.2 SQL方言またはSQLGlotを更新する

SQLGlotの更新はASTやscope解決を変える可能性があります。バージョン変更時は156シナリオを再実行し、利用DB固有の構文を追加します。特に、集約、`WITHIN GROUP`、STAR、DML `RETURNING`、CTE、集合演算を確認してください。

### 9.3 記録しておく情報

- 本パッケージのバージョンまたはコミットSHA
- TSVポリシーのrevision
- PythonとSQLGlotのバージョン
- pytest・SQLシナリオ・build結果
- Codex matcher
- SQL方言
- fail-open／fail-closed設定

## 10. トラブルシューティング

### hookが動かない

- `.codex/config.toml`が対象リポジトリにあるか確認する
- hookがCodexで信頼済みか確認する
- matcherが実際のMCPツール名と一致するか確認する
- hookコマンドをterminalから単独実行する
- サブディレクトリからCodexを起動してもgit root基準でpathを解決できるか確認する
- Windowsではwrapperと`.venv\Scripts\mcp-sql-result-guard.exe`の存在を確認する

### SQLが検出されない

MCP引数内の`sql`、`query`、`statement`だけがSQL候補です。別のキー名を使うMCPは、現仕様のままでは検査されません。

### 方言エラーが出る

`MCP_SQL_RESULT_GUARD_DIALECT`を利用DBに合わせます。ただしRedshift以外を利用する場合は、方言固有シナリオを追加してから依存してください。

### 安全に見える集約が拒否される

- TSVの`allow`に必要なmaskがあるか確認する
- 関数が既知の縮約allowlistに含まれるか確認する
- 未知関数は既定で拒否される
- `MIN`、`MAX`、列挙集約、パーセンタイルは値を保持しうるため拒否される

### `SELECT *`を許可したい

`__SELECT_STAR__`行を無効化できますが、基表STARの列構成をSQLだけで確認できなくなります。DB viewで列を限定する方法や、列を明示するSQLを優先してください。

### 解析失敗を許可したくない

`MCP_SQL_RESULT_GUARD_FAIL_OPEN=false`へ変更し、利用方言の代表SQLとエラー処理を先に検証します。

## 11. 本番導入チェックリスト

- [ ] matcherをSQL実行ツールのみに限定した
- [ ] TSVへ実際に保護したい列パターンを登録した
- [ ] 利用DB方言の代表SQLをシナリオテストへ追加した
- [ ] fail-open／fail-closedをリスクに応じて決定した
- [ ] DBロールを最小権限にした
- [ ] マスキング、行列権限、監査ログなどの補完策を確認した
- [ ] 基表の最終`SELECT *`を許可するか決定した
- [ ] SQLGlotと本パッケージのバージョンを固定した
- [ ] バージョン更新時にpytestとSQLシナリオを再実行する手順を決めた
- [ ] 小集団や反復照会による推測リスクを別レイヤーで扱うか決定した
- [ ] UDF、ストアドプロシージャ、`UNLOAD`、外部出力が本ツールの範囲外であることを確認した

## 12. 制約と関連ドキュメント

本ツールは静的解析に基づく軽量なガードレールであり、情報漏えいを完全に防ぐものではありません。導入判断では、DB・MCP・Codex・監査・privacy controlを含む全体のデータ経路を確認してください。

- [README（日本語）](../../README.ja.md)
- [Architecture](../architecture.md)
- [Limitations and threat model](../limitations.md)
- [Security policy](../../SECURITY.md)
- [Regression test report](../test-report.md)
- [Examples](../../examples/README.md)
- [Contributing](../../CONTRIBUTING.md)
- [Codex hooks documentation](https://developers.openai.com/codex/hooks)
