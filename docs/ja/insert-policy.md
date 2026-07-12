# INSERT入力の判定

機微列の生値、加工値、CTE・副問合せを経由した値は、INSERT先へ書き込むだけでMCPの結果セットへ返らない場合、許可されます。

```sql
WITH selected AS (
    SELECT user_id
    FROM users
)
INSERT INTO archive (user_id)
SELECT user_id
FROM selected;
```

`RETURNING`はMCPへ返る結果として検査されます。

```sql
-- 許可: 返す列は機微列ではない
INSERT INTO archive (user_id)
SELECT user_id
FROM users
RETURNING archive_id;
```

```sql
-- 拒否: 機微列を返す
INSERT INTO archive (user_id)
SELECT user_id
FROM users
RETURNING user_id;
```

このガードはINSERT先の認可や安全性を判断しません。書込み可能なテーブルやSQL文の範囲は、DB権限とMCP側のポリシーで制御してください。
