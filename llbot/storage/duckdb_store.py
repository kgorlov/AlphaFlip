"""DuckDB storage for local execution and reconciliation state."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from llbot.storage.audit_jsonl import audit_record_to_dict


class DuckDbExecutionStore:
    """Persist reconciled MetaScalp execution state into queryable DuckDB tables."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn = None

    def __enter__(self) -> "DuckDbExecutionStore":
        self.open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def open(self) -> None:
        if self._conn is not None:
            return
        import duckdb

        if self.path != Path(":memory:"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self.path))
        self.init_schema()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def init_schema(self) -> None:
        conn = self._require_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metascalp_orders (
                client_order_id TEXT PRIMARY KEY,
                intent_id TEXT NOT NULL,
                venue_order_id TEXT,
                symbol TEXT NOT NULL,
                qty DECIMAL(38, 18) NOT NULL,
                filled_qty DECIMAL(38, 18) NOT NULL,
                avg_fill_price DECIMAL(38, 18),
                status TEXT NOT NULL,
                is_open BOOLEAN NOT NULL,
                accepted_ts_ms BIGINT,
                expires_ts_ms BIGINT,
                last_update_ts_ms BIGINT,
                unknown_status BOOLEAN NOT NULL,
                connection_id BIGINT,
                metadata_json TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                source TEXT,
                ingested_at TIMESTAMP DEFAULT current_timestamp
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metascalp_fills (
                client_order_id TEXT PRIMARY KEY,
                intent_id TEXT NOT NULL,
                venue_order_id TEXT,
                symbol TEXT NOT NULL,
                filled_qty DECIMAL(38, 18) NOT NULL,
                avg_fill_price DECIMAL(38, 18) NOT NULL,
                fill_ts_ms BIGINT,
                status TEXT NOT NULL,
                source TEXT,
                raw_json TEXT NOT NULL,
                ingested_at TIMESTAMP DEFAULT current_timestamp
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metascalp_positions (
                source TEXT,
                row_no BIGINT NOT NULL,
                connection_id BIGINT,
                symbol TEXT NOT NULL,
                qty DECIMAL(38, 18) NOT NULL,
                avg_price DECIMAL(38, 18),
                raw_json TEXT NOT NULL,
                ingested_at TIMESTAMP DEFAULT current_timestamp
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metascalp_balances (
                source TEXT,
                row_no BIGINT NOT NULL,
                connection_id BIGINT,
                asset TEXT NOT NULL,
                available DECIMAL(38, 18),
                total DECIMAL(38, 18),
                raw_json TEXT NOT NULL,
                ingested_at TIMESTAMP DEFAULT current_timestamp
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metascalp_reconciliation_audit (
                source TEXT,
                row_no BIGINT NOT NULL,
                event_type TEXT NOT NULL,
                decision_result TEXT NOT NULL,
                client_order_id TEXT,
                before_status TEXT,
                after_status TEXT,
                symbol TEXT,
                raw_update_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                ingested_at TIMESTAMP DEFAULT current_timestamp
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_quotes (
                source TEXT,
                row_no BIGINT NOT NULL,
                event_type TEXT NOT NULL,
                venue TEXT NOT NULL,
                market TEXT NOT NULL,
                symbol TEXT NOT NULL,
                local_ts_ms BIGINT,
                exchange_ts_ms BIGINT,
                bid_price DECIMAL(38, 18),
                bid_qty DECIMAL(38, 18),
                ask_price DECIMAL(38, 18),
                ask_qty DECIMAL(38, 18),
                raw_json TEXT NOT NULL,
                ingested_at TIMESTAMP DEFAULT current_timestamp
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_trades (
                source TEXT,
                row_no BIGINT NOT NULL,
                venue TEXT NOT NULL,
                market TEXT NOT NULL,
                symbol TEXT NOT NULL,
                local_ts_ms BIGINT,
                exchange_ts_ms BIGINT,
                price DECIMAL(38, 18) NOT NULL,
                qty DECIMAL(38, 18) NOT NULL,
                side TEXT,
                trade_id TEXT,
                raw_json TEXT NOT NULL,
                ingested_at TIMESTAMP DEFAULT current_timestamp
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_intents (
                source TEXT,
                row_no BIGINT NOT NULL,
                intent_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                mode TEXT,
                intent_type TEXT,
                side TEXT,
                model TEXT,
                expected_edge_bps DECIMAL(38, 18),
                decision_result TEXT,
                risk_allowed BOOLEAN,
                risk_reason TEXT,
                raw_json TEXT NOT NULL,
                ingested_at TIMESTAMP DEFAULT current_timestamp
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS order_facts (
                source TEXT,
                row_no BIGINT NOT NULL,
                intent_id TEXT,
                client_order_id TEXT,
                venue_order_id TEXT,
                symbol TEXT,
                side TEXT,
                qty DECIMAL(38, 18),
                price DECIMAL(38, 18),
                status TEXT,
                raw_json TEXT NOT NULL,
                ingested_at TIMESTAMP DEFAULT current_timestamp
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fill_facts (
                source TEXT,
                row_no BIGINT NOT NULL,
                intent_id TEXT,
                client_order_id TEXT,
                symbol TEXT,
                filled_qty DECIMAL(38, 18),
                fill_price DECIMAL(38, 18),
                fill_reason TEXT,
                raw_json TEXT NOT NULL,
                ingested_at TIMESTAMP DEFAULT current_timestamp
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pnl_facts (
                source TEXT,
                row_no BIGINT NOT NULL,
                symbol TEXT,
                event_type TEXT,
                exit_reason TEXT,
                gross_pnl_usd DECIMAL(38, 18),
                cost_usd DECIMAL(38, 18),
                net_pnl_usd DECIMAL(38, 18),
                raw_json TEXT NOT NULL,
                ingested_at TIMESTAMP DEFAULT current_timestamp
            )
            """
        )

    def ingest_reconciliation_report(
        self,
        report: dict[str, Any],
        *,
        source: str | None = None,
        replace_source: bool = True,
    ) -> dict[str, int]:
        """Insert a reconciliation report produced by apps/reconcile_metascalp_updates.py."""

        conn = self._require_conn()
        orders = _list(report.get("orders"))
        positions = _list(report.get("positions"))
        balances = _list(report.get("balances"))
        audit_records = _list(report.get("audit_records"))

        if source is not None and replace_source:
            self.delete_source(source)

        inserted_orders = 0
        inserted_fills = 0
        for order in orders:
            client_order_id = str(order["client_order_id"])
            conn.execute("DELETE FROM metascalp_orders WHERE client_order_id = ?", [client_order_id])
            conn.execute("DELETE FROM metascalp_fills WHERE client_order_id = ?", [client_order_id])
            conn.execute(
                """
                INSERT INTO metascalp_orders (
                    client_order_id, intent_id, venue_order_id, symbol, qty, filled_qty,
                    avg_fill_price, status, is_open, accepted_ts_ms, expires_ts_ms,
                    last_update_ts_ms, unknown_status, connection_id, metadata_json,
                    raw_json, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    client_order_id,
                    str(order["intent_id"]),
                    _str_or_none(order.get("venue_order_id")),
                    str(order["symbol"]),
                    _decimal(order.get("qty"), "0"),
                    _decimal(order.get("filled_qty"), "0"),
                    _decimal_or_none(order.get("avg_fill_price")),
                    str(order["status"]),
                    bool(order.get("open", False)),
                    _int_or_none(order.get("accepted_ts_ms")),
                    _int_or_none(order.get("expires_ts_ms")),
                    _int_or_none(order.get("last_update_ts_ms")),
                    bool(order.get("unknown_status", False)),
                    _int_or_none(_metadata(order).get("connection_id")),
                    _json(_metadata(order)),
                    _json(order),
                    source,
                ],
            )
            inserted_orders += 1
            if _decimal(order.get("filled_qty"), "0") > 0 and order.get("avg_fill_price") is not None:
                conn.execute(
                    """
                    INSERT INTO metascalp_fills (
                        client_order_id, intent_id, venue_order_id, symbol, filled_qty,
                        avg_fill_price, fill_ts_ms, status, source, raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        client_order_id,
                        str(order["intent_id"]),
                        _str_or_none(order.get("venue_order_id")),
                        str(order["symbol"]),
                        _decimal(order.get("filled_qty"), "0"),
                        _decimal(order.get("avg_fill_price"), "0"),
                        _int_or_none(order.get("last_update_ts_ms")),
                        str(order["status"]),
                        source,
                        _json(order),
                    ],
                )
                inserted_fills += 1

        for row_no, position in enumerate(positions):
            conn.execute(
                """
                INSERT INTO metascalp_positions (
                    source, row_no, connection_id, symbol, qty, avg_price, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    source,
                    row_no,
                    _int_or_none(position.get("connection_id")),
                    str(position["symbol"]),
                    _decimal(position.get("qty"), "0"),
                    _decimal_or_none(position.get("avg_price")),
                    _json(position),
                ],
            )

        for row_no, balance in enumerate(balances):
            conn.execute(
                """
                INSERT INTO metascalp_balances (
                    source, row_no, connection_id, asset, available, total, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    source,
                    row_no,
                    _int_or_none(balance.get("connection_id")),
                    str(balance["asset"]),
                    _decimal_or_none(balance.get("available")),
                    _decimal_or_none(balance.get("total")),
                    _json(balance),
                ],
            )

        for row_no, record in enumerate(audit_records):
            conn.execute(
                """
                INSERT INTO metascalp_reconciliation_audit (
                    source, row_no, event_type, decision_result, client_order_id,
                    before_status, after_status, symbol, raw_update_json, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    source,
                    row_no,
                    str(record["event_type"]),
                    str(record["decision_result"]),
                    _str_or_none(record.get("client_order_id")),
                    _str_or_none(record.get("before_status")),
                    _str_or_none(record.get("after_status")),
                    _str_or_none(record.get("symbol")),
                    _json(record.get("raw_update", {})),
                    _json(record.get("metadata", {})),
                ],
            )

        return {
            "orders": inserted_orders,
            "fills": inserted_fills,
            "positions": len(positions),
            "balances": len(balances),
            "audit_records": len(audit_records),
        }

    def ingest_replay_events(
        self,
        events: list[Any],
        *,
        source: str | None = None,
        replace_source: bool = True,
    ) -> dict[str, int]:
        """Insert replay market data events into queryable market tables."""

        conn = self._require_conn()
        if source is not None and replace_source:
            conn.execute("DELETE FROM market_quotes WHERE source = ?", [source])
            conn.execute("DELETE FROM market_trades WHERE source = ?", [source])

        quotes = 0
        trades = 0
        for row_no, event in enumerate(events):
            event_type = str(getattr(event, "event_type"))
            payload = getattr(event, "payload")
            if event_type in {"book_ticker", "orderbook_depth"}:
                conn.execute(
                    """
                    INSERT INTO market_quotes (
                        source, row_no, event_type, venue, market, symbol, local_ts_ms,
                        exchange_ts_ms, bid_price, bid_qty, ask_price, ask_qty, raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        source,
                        row_no,
                        event_type,
                        str(getattr(event, "venue")),
                        str(getattr(event, "market")),
                        str(getattr(event, "symbol")),
                        _int_or_none(getattr(event, "local_ts_ms")),
                        _int_or_none(getattr(event, "exchange_ts_ms")),
                        _decimal_or_none(payload.get("bid_price")),
                        _decimal_or_none(payload.get("bid_qty")),
                        _decimal_or_none(payload.get("ask_price")),
                        _decimal_or_none(payload.get("ask_qty")),
                        _json(event),
                    ],
                )
                quotes += 1
            elif event_type == "trade":
                conn.execute(
                    """
                    INSERT INTO market_trades (
                        source, row_no, venue, market, symbol, local_ts_ms,
                        exchange_ts_ms, price, qty, side, trade_id, raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        source,
                        row_no,
                        str(getattr(event, "venue")),
                        str(getattr(event, "market")),
                        str(getattr(event, "symbol")),
                        _int_or_none(getattr(event, "local_ts_ms")),
                        _int_or_none(getattr(event, "exchange_ts_ms")),
                        _decimal(payload.get("price"), "0"),
                        _decimal(payload.get("qty"), "0"),
                        _str_or_none(payload.get("side")),
                        _str_or_none(payload.get("trade_id")),
                        _json(event),
                    ],
                )
                trades += 1
        return {"market_quotes": quotes, "market_trades": trades}

    def load_replay_events(
        self,
        *,
        source: str | None = None,
        day: str | None = None,
    ) -> list[Any]:
        """Load previously ingested replay events from market tables."""

        conn = self._require_conn()
        conditions = []
        parameters: list[Any] = []
        if source is not None:
            conditions.append("source = ?")
            parameters.append(source)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = conn.execute(
            f"""
            SELECT raw_json FROM market_quotes {where}
            UNION ALL
            SELECT raw_json FROM market_trades {where}
            """,
            parameters * 2 if conditions else [],
        ).fetchall()
        events = [_replay_event_from_json(row[0]) for row in rows]
        if day is not None:
            events = [
                event for event in events
                if isinstance(getattr(event, "captured_at_utc", None), str)
                and getattr(event, "captured_at_utc").startswith(day)
            ]
        return sorted(events, key=lambda event: (
            getattr(event, "local_ts_ms") or getattr(event, "exchange_ts_ms") or 0,
            getattr(event, "exchange_ts_ms") or 0,
            getattr(event, "venue"),
            getattr(event, "symbol"),
        ))

    def ingest_audit_records(
        self,
        records: list[dict[str, Any]],
        *,
        source: str | None = None,
        replace_source: bool = True,
    ) -> dict[str, int]:
        """Insert normalized signal/order/fill/PnL facts from audit dictionaries."""

        conn = self._require_conn()
        if source is not None and replace_source:
            for table in ("signal_intents", "order_facts", "fill_facts", "pnl_facts"):
                conn.execute(f"DELETE FROM {table} WHERE source = ?", [source])

        intents = orders = fills = pnl = 0
        for row_no, record in enumerate(records):
            event_type = str(record.get("event_type", ""))
            if event_type == "replay_signal_decision":
                conn.execute(
                    """
                    INSERT INTO signal_intents (
                        source, row_no, intent_id, symbol, mode, intent_type, side, model,
                        expected_edge_bps, decision_result, risk_allowed, risk_reason, raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        source,
                        row_no,
                        str(record.get("intent_id")),
                        str(record.get("symbol")),
                        _str_or_none(record.get("mode")),
                        _str_or_none(record.get("intent_type")),
                        _str_or_none(record.get("side")),
                        _str_or_none(record.get("model")),
                        _decimal_or_none(record.get("expected_edge_bps")),
                        _str_or_none(record.get("decision_result")),
                        bool(record.get("risk_allowed", False)),
                        _str_or_none(record.get("risk_reason")),
                        _json(record),
                    ],
                )
                intents += 1
                order = record.get("order_request")
                if isinstance(order, dict):
                    _insert_order_fact(conn, source, row_no, record, order)
                    orders += 1
                if record.get("fill_filled") is not None:
                    _insert_fill_fact(conn, source, row_no, record)
                    fills += 1
            elif event_type == "replay_position_exit":
                conn.execute(
                    """
                    INSERT INTO pnl_facts (
                        source, row_no, symbol, event_type, exit_reason, gross_pnl_usd,
                        cost_usd, net_pnl_usd, raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        source,
                        row_no,
                        _str_or_none(record.get("symbol")),
                        event_type,
                        _str_or_none(record.get("exit_reason")),
                        _decimal_or_none(record.get("gross_pnl_usd")),
                        _decimal_or_none(record.get("cost_usd")),
                        _decimal_or_none(record.get("realized_pnl_usd")),
                        _json(record),
                    ],
                )
                pnl += 1
        return {"signal_intents": intents, "order_facts": orders, "fill_facts": fills, "pnl_facts": pnl}

    def delete_source(self, source: str) -> None:
        conn = self._require_conn()
        for table in (
            "metascalp_orders",
            "metascalp_fills",
            "metascalp_positions",
            "metascalp_balances",
            "metascalp_reconciliation_audit",
            "market_quotes",
            "market_trades",
            "signal_intents",
            "order_facts",
            "fill_facts",
            "pnl_facts",
        ):
            conn.execute(f"DELETE FROM {table} WHERE source = ?", [source])

    def table_counts(self) -> dict[str, int]:
        conn = self._require_conn()
        tables = {
            "orders": "metascalp_orders",
            "fills": "metascalp_fills",
            "positions": "metascalp_positions",
            "balances": "metascalp_balances",
            "audit_records": "metascalp_reconciliation_audit",
            "market_quotes": "market_quotes",
            "market_trades": "market_trades",
            "signal_intents": "signal_intents",
            "order_facts": "order_facts",
            "fill_facts": "fill_facts",
            "pnl_facts": "pnl_facts",
        }
        return {
            name: int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
            for name, table in tables.items()
        }

    def query_all(self, sql: str, parameters: list[Any] | None = None) -> list[tuple[Any, ...]]:
        return self._require_conn().execute(sql, parameters or []).fetchall()

    def _require_conn(self):
        if self._conn is None:
            raise RuntimeError("DuckDbExecutionStore is not open")
        return self._conn


def load_reconciliation_report(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Reconciliation report must be a JSON object")
    return payload


def _replay_event_from_json(raw_json: str):
    from llbot.storage.replay_jsonl import ReplayEvent

    payload = json.loads(raw_json)
    return ReplayEvent(**payload)


def _list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Expected report section to be a list")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError("Expected report rows to be JSON objects")
    return value


def _metadata(order: dict[str, Any]) -> dict[str, Any]:
    metadata = order.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _json(value: Any) -> str:
    return json.dumps(audit_record_to_dict(value), ensure_ascii=True, separators=(",", ":"))


def _decimal(value: Any, default: str) -> Decimal:
    parsed = _decimal_or_none(value)
    return Decimal(default) if parsed is None else parsed


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _str_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _insert_order_fact(conn, source: str | None, row_no: int, record: dict[str, Any], order: dict[str, Any]) -> None:
    response = record.get("order_response")
    if not isinstance(response, dict):
        response = {}
    conn.execute(
        """
        INSERT INTO order_facts (
            source, row_no, intent_id, client_order_id, venue_order_id, symbol, side,
            qty, price, status, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            source,
            row_no,
            _str_or_none(record.get("intent_id")),
            _str_or_none(response.get("client_order_id") or response.get("ClientId")),
            _str_or_none(response.get("venue_order_id") or response.get("OrderId")),
            _str_or_none(order.get("symbol")),
            _str_or_none(order.get("side")),
            _decimal_or_none(order.get("qty")),
            _decimal_or_none(order.get("price_cap") or order.get("price")),
            _str_or_none(record.get("decision_result")),
            _json(record),
        ],
    )


def _insert_fill_fact(conn, source: str | None, row_no: int, record: dict[str, Any]) -> None:
    response = record.get("order_response")
    if not isinstance(response, dict):
        response = {}
    conn.execute(
        """
        INSERT INTO fill_facts (
            source, row_no, intent_id, client_order_id, symbol, filled_qty,
            fill_price, fill_reason, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            source,
            row_no,
            _str_or_none(record.get("intent_id")),
            _str_or_none(response.get("client_order_id") or response.get("ClientId")),
            _str_or_none(record.get("symbol")),
            _decimal_or_none(record.get("fill_qty")),
            _decimal_or_none(record.get("fill_price")),
            _str_or_none(record.get("fill_reason")),
            _json(record),
        ],
    )
