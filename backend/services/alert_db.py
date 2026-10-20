import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent / "logs"
DB_PATH = DB_DIR / "alerts.db"
LOG_FILE = DB_DIR / "email_alerts.log"


def get_db_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initializes the SQLite alerts and threshold rules database tables and migrates existing logs."""
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS email_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    threshold INTEGER NOT NULL,
                    usage_percent REAL NOT NULL,
                    hostname TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    action_taken TEXT,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON email_alerts (timestamp DESC);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerts_resource ON email_alerts (resource);"
            )

            # Table for configurable email alert thresholds managed from the UI
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_threshold_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource TEXT NOT NULL,
                    threshold_percent INTEGER NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'HIGH',
                    recipient TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_thresholds_resource ON alert_threshold_rules (resource, enabled);"
            )

        # Seed default threshold rules if table is empty
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM alert_threshold_rules;")
        rules_count = cur.fetchone()[0]
        if rules_count == 0:
            default_rules = [
                ("CPU", 70, "HIGH", ""),
                ("CPU", 90, "CRITICAL", ""),
                ("CPU", 100, "CRITICAL", ""),
                ("RAM", 70, "HIGH", ""),
                ("RAM", 90, "CRITICAL", ""),
                ("RAM", 100, "CRITICAL", ""),
                ("Disk", 70, "HIGH", ""),
                ("Disk", 90, "CRITICAL", ""),
                ("Disk", 100, "CRITICAL", ""),
            ]
            conn.executemany(
                """
                INSERT INTO alert_threshold_rules (resource, threshold_percent, severity, recipient, enabled)
                VALUES (?, ?, ?, ?, 1);
                """,
                default_rules,
            )
            conn.commit()

        # Seed from existing email_alerts.log if table is empty
        cur.execute("SELECT COUNT(*) FROM email_alerts;")
        count = cur.fetchone()[0]

        if count == 0 and LOG_FILE.exists():
            lines = LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
            for line in lines:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    insert_alert(rec, conn=conn)
                except Exception:
                    pass
            conn.commit()
    except Exception as exc:
        logger.error(f"Failed to initialize alerts database: {exc}")
    finally:
        conn.close()


def insert_alert(record: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> int:
    """Inserts a new alert record into the SQLite database."""
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    try:
        details_val = record.get("details", "")
        if isinstance(details_val, (dict, list)):
            details_str = json.dumps(details_val)
        else:
            details_str = str(details_val or record.get("action_taken", ""))

        threshold_val = record.get("threshold", record.get("threshold_level", 70))
        if isinstance(threshold_val, str):
            try:
                threshold_val = int(threshold_val.replace("%", "").strip())
            except ValueError:
                threshold_val = 70

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO email_alerts (
                timestamp, recipient, subject, resource, threshold,
                usage_percent, hostname, status, provider, action_taken, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                str(record.get("timestamp", "")),
                str(record.get("recipient", "")),
                str(record.get("subject", "")),
                str(record.get("resource", record.get("metric_name", "UNKNOWN"))),
                int(threshold_val),
                float(record.get("usage_percent", record.get("value", 0.0)) or 0.0),
                str(record.get("hostname", "system-host")),
                str(record.get("status", "SENT")),
                str(record.get("provider", "smtp")),
                str(record.get("action_taken", "")),
                details_str,
            ),
        )
        if should_close:
            conn.commit()
        return cursor.lastrowid
    except Exception as exc:
        logger.error(f"Failed to insert alert into SQLite db: {exc}")
        return -1
    finally:
        if should_close and conn:
            conn.close()


def get_all_alerts(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves the latest alerts from the SQLite database with newest/latest first."""
    init_db()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, recipient, subject, resource, threshold,
                   usage_percent, hostname, status, provider, action_taken, details, created_at
            FROM email_alerts
            ORDER BY id DESC
            LIMIT ?;
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "timestamp": r["timestamp"],
                "recipient": r["recipient"],
                "subject": r["subject"],
                "metric_name": r["resource"],
                "resource": r["resource"],
                "threshold": r["threshold"],
                "threshold_level": f"{r['threshold']}%",
                "usage_percent": r["usage_percent"],
                "value": r["usage_percent"],
                "hostname": r["hostname"],
                "status": r["status"],
                "provider": r["provider"],
                "action_taken": r["action_taken"],
                "details": r["details"],
                "created_at": r["created_at"],
            })
        return results
    except Exception as exc:
        logger.error(f"Failed to fetch alerts from database: {exc}")
        return []
    finally:
        conn.close()


def get_alerts_count() -> int:
    """Returns the total number of alerts recorded in the database."""
    init_db()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM email_alerts;")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    except Exception as exc:
        logger.error(f"Failed to fetch alerts count: {exc}")
        return 0
    finally:
        conn.close()


def clear_alerts() -> bool:
    """Clears all records in the database table."""
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM email_alerts;")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='email_alerts';")
        return True
    except Exception as exc:
        logger.error(f"Failed to clear alerts from db: {exc}")
        return False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Dynamic Configurable Alert Threshold Rules CRUD & Dynamic Evaluator
# ---------------------------------------------------------------------------

def get_threshold_rules(resource: Optional[str] = None, enabled_only: bool = False) -> List[Dict[str, Any]]:
    """Retrieves all configurable threshold rules."""
    init_db()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT id, resource, threshold_percent, severity, recipient, enabled, created_at, updated_at FROM alert_threshold_rules"
        clauses = []
        params = []
        if resource:
            clauses.append("(resource = ? OR resource = 'ALL')")
            params.append(resource.upper())
        if enabled_only:
            clauses.append("enabled = 1")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY resource ASC, threshold_percent ASC;"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "resource": r["resource"],
                "threshold_percent": r["threshold_percent"],
                "severity": r["severity"],
                "recipient": r["recipient"] or "",
                "enabled": bool(r["enabled"]),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.error(f"Failed to fetch threshold rules: {exc}")
        return []
    finally:
        conn.close()


def get_distinct_thresholds() -> List[int]:
    """Returns all unique threshold percentages across configured rules and alerts for UI filters."""
    init_db()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT threshold_percent FROM alert_threshold_rules WHERE enabled = 1;")
        rule_thresholds = [r[0] for r in cursor.fetchall() if r[0] is not None]
        cursor.execute("SELECT DISTINCT threshold FROM email_alerts;")
        alert_thresholds = [r[0] for r in cursor.fetchall() if r[0] is not None]
        combined = set(rule_thresholds + alert_thresholds + [70, 90, 100])
        return sorted(list(combined))
    except Exception as exc:
        logger.error(f"Failed to fetch distinct thresholds: {exc}")
        return [70, 90, 100]
    finally:
        conn.close()


def create_threshold_rule(
    resource: str,
    threshold_percent: int,
    severity: str = "HIGH",
    recipient: str = "",
    enabled: int = 1,
) -> Optional[Dict[str, Any]]:
    """Creates a new configurable threshold alert rule."""
    init_db()
    conn = get_db_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO alert_threshold_rules (resource, threshold_percent, severity, recipient, enabled)
                VALUES (?, ?, ?, ?, ?);
                """,
                (resource.upper().strip(), int(threshold_percent), severity.upper().strip(), recipient.strip(), int(enabled)),
            )
            rule_id = cursor.lastrowid
            return {
                "id": rule_id,
                "resource": resource.upper().strip(),
                "threshold_percent": int(threshold_percent),
                "severity": severity.upper().strip(),
                "recipient": recipient.strip(),
                "enabled": bool(enabled),
            }
    except Exception as exc:
        logger.error(f"Failed to create threshold rule: {exc}")
        return None
    finally:
        conn.close()


def update_threshold_rule(
    rule_id: int,
    resource: Optional[str] = None,
    threshold_percent: Optional[int] = None,
    severity: Optional[str] = None,
    recipient: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> bool:
    """Updates an existing threshold rule."""
    init_db()
    conn = get_db_connection()
    try:
        updates = []
        params = []
        if resource is not None:
            updates.append("resource = ?")
            params.append(resource.upper().strip())
        if threshold_percent is not None:
            updates.append("threshold_percent = ?")
            params.append(int(threshold_percent))
        if severity is not None:
            updates.append("severity = ?")
            params.append(severity.upper().strip())
        if recipient is not None:
            updates.append("recipient = ?")
            params.append(recipient.strip())
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)

        if not updates:
            return True

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(rule_id)

        with conn:
            conn.execute(
                f"UPDATE alert_threshold_rules SET {', '.join(updates)} WHERE id = ?;",
                params,
            )
        return True
    except Exception as exc:
        logger.error(f"Failed to update threshold rule {rule_id}: {exc}")
        return False
    finally:
        conn.close()


def delete_threshold_rule(rule_id: int) -> bool:
    """Deletes a threshold rule by ID."""
    init_db()
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM alert_threshold_rules WHERE id = ?;", (rule_id,))
        return True
    except Exception as exc:
        logger.error(f"Failed to delete threshold rule {rule_id}: {exc}")
        return False
    finally:
        conn.close()


def toggle_threshold_rule(rule_id: int, enabled: Optional[bool] = None) -> bool:
    """Toggles or sets the enabled status of a threshold rule."""
    init_db()
    conn = get_db_connection()
    try:
        with conn:
            if enabled is not None:
                conn.execute(
                    "UPDATE alert_threshold_rules SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                    (1 if enabled else 0, rule_id),
                )
            else:
                conn.execute(
                    "UPDATE alert_threshold_rules SET enabled = (1 - enabled), updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                    (rule_id,),
                )
        return True
    except Exception as exc:
        logger.error(f"Failed to toggle threshold rule {rule_id}: {exc}")
        return False
    finally:
        conn.close()


def get_highest_matching_threshold(
    resource_name: str,
    usage_percent: float,
    per_core: Optional[List[float]] = None,
) -> Optional[int]:
    """
    Dynamically identifies the highest crossed threshold tier from configured active rules.
    - If CPU has a saturated core (>= 99%) and a 100% rule exists, returns 100.
    - Otherwise returns the highest configured threshold where usage_percent >= threshold_percent.
    """
    res_upper = resource_name.upper().strip()
    # Normalize resource names e.g. "MEMORY" -> "RAM"
    if res_upper == "MEMORY":
        res_upper = "RAM"

    rules = get_threshold_rules(resource=res_upper, enabled_only=True)
    if not rules:
        # Fallback to default tiers if rules not present
        if per_core and any(c >= 99.0 for c in per_core):
            return 100
        if usage_percent >= 99.0:
            return 100
        elif usage_percent >= 90.0:
            return 90
        elif usage_percent >= 70.0:
            return 70
        return None

    # Sort configured thresholds descending (e.g. [100, 90, 80, 70, 60])
    thresholds = sorted({r["threshold_percent"] for r in rules}, reverse=True)

    # Core saturation check for CPU
    if res_upper in ("CPU", "ALL") and per_core and any(c >= 99.0 for c in per_core):
        if 100 in thresholds:
            return 100

    for th in thresholds:
        # If threshold is 100, allow 99.0+ to trigger
        eval_th = 99.0 if th >= 100 else float(th)
        if usage_percent >= eval_th:
            return th

    return None


# Ensure db is created upon import
init_db()
