# INSERT input policy

Sensitive raw values, transformed values, and values routed through CTEs or subqueries are allowed when they are only written to an INSERT destination and do not become part of the MCP result set.

```sql
WITH selected AS (
    SELECT user_id
    FROM users
)
INSERT INTO archive (user_id)
SELECT user_id
FROM selected;
```

`RETURNING` remains an MCP-visible result boundary.

```sql
-- Allow: the returned column is not configured as sensitive.
INSERT INTO archive (user_id)
SELECT user_id
FROM users
RETURNING archive_id;
```

```sql
-- Deny: the configured sensitive column is returned.
INSERT INTO archive (user_id)
SELECT user_id
FROM users
RETURNING user_id;
```

This guard does not authorize the INSERT destination. Database permissions and MCP-side statement policy must control which tables and writes are permitted.
