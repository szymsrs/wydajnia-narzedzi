# app/core/auth.py
import logging, traceback, time, re, hashlib
from typing import Any, Optional
from importlib import import_module

import bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import URL

log = logging.getLogger("app.core.auth")

# ===== domena (usługi) – importy cienkiej warstwy wywołań =====
from app.domain.services.issue import issue_tool as svc_issue_tool
from app.domain.services.scrap import scrap_tool as svc_scrap_tool
from app.domain.services.rw import record_rw_receipt as svc_record_rw_receipt
from app.domain.services.inventory import inventory_count as svc_inventory_count
from app.domain.services.bundle import issue_return_bundle as svc_issue_return_bundle  # NEW

# UWAGA: moduł nazywa się 'return' (słowo kluczowe) – używamy import_module
try:
    svc_return_tool = getattr(import_module("app.domain.services.return"), "return_tool")
except Exception as _e:  # pragma: no cover
    def svc_return_tool(*args, **kwargs):
        raise ImportError(f"Cannot import app.domain.services.return:return_tool: {_e}")

# alias typu – już normalny import (żeby Pylance był zadowolony)
from app.core.rfid_stub import RFIDReader


# ========= pomocnicze debugi =========
def _dbg(msg: str):
    print(msg)
    log.debug(msg)


def _mask(s: str, keep_left: int = 4, keep_right: int = 2) -> str:
    if s is None:
        return "<none>"
    if not isinstance(s, str):
        s = str(s)
    if len(s) <= keep_left + keep_right:
        return "*" * len(s)
    return f"{s[:keep_left]}***{s[-keep_right:]}"


def _dbg_hash(label: str, h) -> None:
    if h is None:
        _dbg(f"{label}: <None>")
        return
    try:
        s = h.decode() if isinstance(h, (bytes, bytearray)) else str(h)
    except Exception:
        s = str(h)
    pref = s[:15].replace("\n", "\\n")
    _dbg(f"{label}: len={len(s)} pref={pref!r} repr={s!r}")


def _is_bcrypt(s: str) -> bool:
    return s.startswith("$2a$") or s.startswith("$2b$") or s.startswith("$2y$")


def _feat_bool(features: Any, name: str, default: bool = False) -> bool:
    """
    Bezpieczne pobranie boola z features – obsługuje zarówno obiekt (pydantic) jak i dict.
    """
    if features is None:
        return default
    if hasattr(features, name):
        try:
            return bool(getattr(features, name))
        except Exception:
            pass
    if isinstance(features, dict) and name in features:
        try:
            return bool(features[name])
        except Exception:
            pass
    return default


# ========= weryfikacja sekretów =========
def verify_secret(stored: str | None, provided: str):
    if stored is None:
        _dbg("[AUTH] stored hash is None")
        return False, "empty"
    stored = stored.strip()

    try:
        # bcrypt
        if stored.startswith("$2"):
            ok = bcrypt.checkpw(provided.encode("utf-8"), stored.encode("utf-8"))
            _dbg(f"[AUTH] bcrypt -> {ok}")
            return ok, "bcrypt"

        # konwencje $hash$...
        if stored.startswith("$hash"):
            parts = stored.split("$")
            _dbg(f"[AUTH] $hash parts={parts[:4]}... len={len(parts)}")
            if "bcrypt" in parts:
                b = parts[-1]
                ok = bcrypt.checkpw(provided.encode("utf-8"), b.encode("utf-8"))
                _dbg(f"[AUTH] $hash+bcrypt -> {ok}")
                return ok, "hash+bcrypt"
            if "sha256" in parts:
                if len(parts) >= 5 and parts[-2] != "sha256":
                    salt = parts[-2]
                    hexhash = parts[-1].lower()
                    calc = hashlib.sha256((salt + provided).encode("utf-8")).hexdigest()
                    ok = calc == hexhash
                    _dbg(f"[AUTH] $hash+sha256+salt -> {ok}")
                    return ok, "hash+sha256+salt"
                else:
                    hexhash = parts[-1].lower()
                    calc = hashlib.sha256(provided.encode("utf-8")).hexdigest()
                    ok = calc == hexhash
                    _dbg(f"[AUTH] $hash+sha256 -> {ok}")
                    return ok, "hash+sha256"

        # goły 64-hex -> sha256
        if re.fullmatch(r"[0-9a-fA-F]{64}", stored):
            ok = hashlib.sha256(provided.encode("utf-8")).hexdigest().lower() == stored.lower()
            _dbg(f"[AUTH] 64hex sha256 -> {ok}")
            return ok, "sha256"

        _dbg(f"[AUTH] unknown hash format: prefix={_mask(stored[:12])}")
        return False, "unknown"
    except Exception as e:
        _dbg(f"[AUTH][ERROR] verify_secret: {e}\n{traceback.format_exc()}")
        return False, "error"


# ========= AuthRepo =========
class AuthRepo:
    def __init__(self, cfg: dict):
        db = cfg["db"]
        self.cfg = cfg

        # Budowanie DSN z obsługą znaków specjalnych w haśle
        url = URL.create(
            drivername="mysql+pymysql",
            username=db["user"],
            password=db["password"],
            host=db["host"],
            port=int(db["port"]),
            database=db["database"],
            query={"charset": "utf8mb4"},
        )

        _dbg(f"[AuthRepo] init host={db['host']}:{db['port']} db={db['database']} user={db['user']}")
        try:
            self.engine = create_engine(
                url,
                pool_pre_ping=True,
                pool_recycle=1800,
                future=True,
            )
            # szybki ping
            with self.engine.connect() as c:
                c.execute(text("SELECT 1"))
            _dbg("[AuthRepo] Połączenie z DB OK")
        except SQLAlchemyError as e:
            _dbg(f"[AuthRepo][ERROR] DB init fail: {e}\n{traceback.format_exc()}")
            raise

    # ====== Warstwa repo dla operacji domenowych (ETAP 2A) ======
    # Każda metoda:
    # - przekazuje rfid_confirmed=None (decyzja i modal po stronie services)
    # - propaguje reader/features
    # - loguje kontekst (required/pin_fallback) oraz status wyniku

    def issue_tool(
        self,
        employee_id: int,
        item_id: int,
        qty,
        *,
        operation_uuid: str,
        reader: Optional[RFIDReader] = None,
        features: Any = None,
    ) -> dict:
        req = _feat_bool(features, "rfid_required", False)
        pin = _feat_bool(features, "pin_fallback", True)
        _dbg(
            f"[REPO.issue] emp={employee_id} item={item_id} qty={qty} "
            f"uuid={_mask(operation_uuid)} required={req} pin_fallback={pin}"
        )
        try:
            with self.engine.begin() as conn:
                res = svc_issue_tool(
                    conn,
                    employee_id,
                    item_id,
                    qty,
                    operation_uuid=operation_uuid,
                    rfid_confirmed=None,
                    reader=reader,
                    features=features,
                )
            _dbg(f"[REPO.issue] status={res.get('status')}")
            return res
        except Exception as e:
            _dbg(f"[REPO.issue][ERROR] {e}\n{traceback.format_exc()}")
            return {"status": "error", "error": str(e)}

    def return_tool(
        self,
        employee_id: int,
        item_id: int,
        qty,
        *,
        operation_uuid: str,
        reader: Optional[RFIDReader] = None,
        features: Any = None,
    ) -> dict:
        req = _feat_bool(features, "rfid_required", False)
        pin = _feat_bool(features, "pin_fallback", True)
        _dbg(
            f"[REPO.return] emp={employee_id} item={item_id} qty={qty} "
            f"uuid={_mask(operation_uuid)} required={req} pin_fallback={pin}"
        )
        try:
            with self.engine.begin() as conn:
                res = svc_return_tool(
                    conn,
                    employee_id,
                    item_id,
                    qty,
                    operation_uuid=operation_uuid,
                    rfid_confirmed=None,
                    reader=reader,
                    features=features,
                )
            _dbg(f"[REPO.return] status={res.get('status')}")
            return res
        except Exception as e:
            _dbg(f"[REPO.return][ERROR] {e}\n{traceback.format_exc()}")
            return {"status": "error", "error": str(e)}

    # NEW: pakietowe RETURN+ISSUE w jednej transakcji
    def issue_return_bundle(
        self,
        employee_id: int,
        returns: list[tuple[int, int]],
        issues: list[tuple[int, int]],
        *,
        reader: Optional[RFIDReader] = None,
        features: Any = None,
    ) -> dict:
        req = _feat_bool(features, "rfid_required", False)
        pin = _feat_bool(features, "pin_fallback", True)
        _dbg(
            f"[REPO.bundle] emp={employee_id} returns={len(returns)} issues={len(issues)} "
            f"required={req} pin_fallback={pin}"
        )
        try:
            with self.engine.begin() as conn:
                res = svc_issue_return_bundle(
                    conn,
                    employee_id,
                    returns,
                    issues,
                    rfid_confirmed=None,
                    reader=reader,
                    features=features,
                )
            _dbg(f"[REPO.bundle] status={res.get('status')} flagged={res.get('flagged')}")
            return res
        except Exception as e:
            _dbg(f"[REPO.bundle][ERROR] {e}\n{traceback.format_exc()}")
            return {"status": "error", "error": str(e)}

    # NEW: pomocniczo – bieżące saldo otwartych sztuk u pracownika
    def get_employee_open_qty(self, employee_id: int) -> int:
        with self.engine.connect() as conn:
            qty = conn.execute(
                text(
                    """
                    SELECT COALESCE(SUM(CASE WHEN movement_type='ISSUE' THEN quantity ELSE -quantity END),0)
                    FROM transactions
                    WHERE employee_id=:emp
                    """
                ),
                dict(emp=employee_id),
            ).scalar()
        return int(qty or 0)

    def scrap_tool(
        self,
        employee_id: int,
        item_id: int,
        qty,
        *,
        operation_uuid: str,
        reason: str | None = None,
        reader: Optional[RFIDReader] = None,
        features: Any = None,
    ) -> dict:
        req = _feat_bool(features, "rfid_required", False)
        pin = _feat_bool(features, "pin_fallback", True)
        _dbg(
            f"[REPO.scrap] emp={employee_id} item={item_id} qty={qty} "
            f"uuid={_mask(operation_uuid)} reason={reason!r} required={req} pin_fallback={pin}"
        )
        try:
            with self.engine.begin() as conn:
                res = svc_scrap_tool(
                    conn,
                    employee_id,
                    item_id,
                    qty,
                    operation_uuid=operation_uuid,
                    rfid_confirmed=None,
                    reason=reason,
                    reader=reader,
                    features=features,
                )
            _dbg(f"[REPO.scrap] status={res.get('status')}")
            return res
        except Exception as e:
            _dbg(f"[REPO.scrap][ERROR] {e}\n{traceback.format_exc()}")
            return {"status": "error", "error": str(e)}

    def record_rw_receipt(
        self,
        document_id: int,
        item_id: int,
        qty,
        *,
        operation_uuid: str,
        reader: Optional[RFIDReader] = None,
        features: Any = None,
    ) -> dict:
        req = _feat_bool(features, "rfid_required", False)
        pin = _feat_bool(features, "pin_fallback", True)
        _dbg(
            f"[REPO.rw_receipt] doc={document_id} item={item_id} qty={qty} "
            f"uuid={_mask(operation_uuid)} required={req} pin_fallback={pin}"
        )
        try:
            with self.engine.begin() as conn:
                res = svc_record_rw_receipt(
                    conn,
                    document_id,
                    item_id,
                    qty,
                    operation_uuid=operation_uuid,
                    rfid_confirmed=None,
                    reader=reader,
                    features=features,
                )
            _dbg(f"[REPO.rw_receipt] status={res.get('status')}")
            return res
        except Exception as e:
            _dbg(f"[REPO.rw_receipt][ERROR] {e}\n{traceback.format_exc()}")
            return {"status": "error", "error": str(e)}

    def inventory_count(
        self,
        item_id: int,
        counted_qty,
        *,
        operation_uuid: str,
        reader: Optional[RFIDReader] = None,
        features: Any = None,
    ) -> dict:
        req = _feat_bool(features, "rfid_required", False)
        pin = _feat_bool(features, "pin_fallback", True)
        _dbg(
            f"[REPO.inventory] item={item_id} counted={counted_qty} "
            f"uuid={_mask(operation_uuid)} required={req} pin_fallback={pin}"
        )
        try:
            with self.engine.begin() as conn:
                res = svc_inventory_count(
                    conn,
                    item_id,
                    counted_qty,
                    operation_uuid=operation_uuid,
                    rfid_confirmed=None,
                    reader=reader,
                    features=features,
                )
            _dbg(f"[REPO.inventory] status={res.get('status')}")
            return res
        except Exception as e:
            _dbg(f"[REPO.inventory][ERROR] {e}\n{traceback.format_exc()}")
            return {"status": "error", "error": str(e)}

    # ===== API pomocnicze
    def login_auto(self, token: str, station_id: str):
        """
        Jedno pole: automatycznie rozpoznaje:
        - RFID UID (alfanumeryczne 6–32, bez spacji) -> login_card
        - PIN (same cyfry 4–8) -> login_pin
        - login + hasło (musi zawierać spację) -> login_password

        Kolejność prób: CARD -> PIN -> PASSWORD (jeśli jest spacja).
        """
        token = (token or "").strip()
        if not token:
            return None, "Podaj dane logowania."

        # Heurystyki
        def looks_like_card(s: str) -> bool:
            # Dostosuj do formatu Twojego czytnika. Na start: 6–32 znaków, alfanumerycznie, bez spacji.
            return " " not in s and s.isalnum() and 6 <= len(s) <= 32

        def looks_like_pin(s: str) -> bool:
            return s.isdigit() and 4 <= len(s) <= 8

        # 1) KARTA (UID)
        if looks_like_card(token):
            sess, err = self.login_card(token, station_id)
            if sess:
                return sess, None
            # jeżeli to np. 8 cyfr i nie jest kartą — spróbuj PIN
            if looks_like_pin(token):
                sess, err = self.login_pin(token, station_id)
                if sess:
                    return sess, None
            # jeśli nie weszło — próbuj dalej według spacji

        # 2) PIN
        if looks_like_pin(token):
            sess, err = self.login_pin(token, station_id)
            if sess:
                return sess, None

        # 3) LOGIN + HASŁO ("login haslo")
        if " " in token:
            login, pwd = token.split(" ", 1)
            login = login.strip()
            pwd = pwd.strip()
            if login and pwd:
                sess, err = self.login_password(login, pwd, station_id)
                if sess:
                    return sess, None

        return None, "Nieprawidłowe dane logowania."

    # ==== USER MANAGEMENT (employees) ====
    def list_employees(self, q: str | None = None):
        """
        Zwraca listę pracowników z flagą czy hasło istnieje i z jawnym PIN-em (jeśli zapisany).
        """
        sql = """
            SELECT id, username AS login, first_name, last_name, role, is_admin, active,
                   rfid_uid, created_at,
                   CASE WHEN password_hash IS NULL OR password_hash='' THEN 0 ELSE 1 END AS has_password,
                   pin_plain
            FROM employees
            {where}
            ORDER BY last_name, first_name
        """
        where = ""
        params = {}
        if q:
            where = "WHERE (username LIKE :q OR first_name LIKE :q OR last_name LIKE :q)"
            params["q"] = f"%{q}%"
        return self._fetchall(sql.format(where=where), **params)

    def get_employee(self, emp_id: int):
        """
        Pojedynczy pracownik – z flagą hasła, pin_plain oraz hashami (dla funkcji 'pokaż hashe').
        """
        return self._fetchone(
            """
            SELECT id, username AS login, first_name, last_name, role, is_admin, active, rfid_uid,
                   CASE WHEN password_hash IS NULL OR password_hash='' THEN 0 ELSE 1 END AS has_password,
                   pin_plain, password_hash, pin_hash
            FROM employees WHERE id = :id
        """,
            id=emp_id,
        )

    def get_hashes(self, emp_id: int):
        """Surowe wartości hashy (do podglądu adminowi w UI)."""
        return self._fetchone(
            """
            SELECT password_hash, pin_hash
            FROM employees WHERE id = :id
        """,
            id=emp_id,
        )

    def create_employee(
        self,
        login: str,
        first_name: str,
        last_name: str,
        role: str = "operator",
        is_admin: bool = False,
        password: str | None = None,
        pin: str | None = None,
        rfid_uid: str | None = None,
        active: bool = True,
    ):
        """
        Tworzy nowego pracownika.
        - rfid_uid jest opcjonalne (musi być UNIQUE, ale może być NULL)
        - pin: 4–8 cyfr (opcjonalny)
        - password/pin: hashowane bcryptem
        """
        # --- normalizacja i walidacje bazowe
        login = (login or "").strip()
        first_name = (first_name or "").strip()
        last_name = (last_name or "").strip()
        role = (role or "operator").strip()

        # rfid_uid: '' -> None (żeby przechodziło do kolumny NULL)
        rfid_uid = (rfid_uid or "").strip() or None

        # pin: '' -> None; walidacja, jeśli podany
        pin = (pin or "").strip() or None
        if pin is not None:
            if not pin.isdigit() or not (4 <= len(pin) <= 8):
                return None, "PIN musi mieć 4–8 cyfr."

        # password: '' -> None
        password = (password or "").strip() or None

        # --- unikalność loginu
        exists = self._fetchone("SELECT 1 FROM employees WHERE username = :u LIMIT 1", u=login)
        if exists:
            return None, "Login jest już zajęty."

        # --- unikalność karty (jeśli podana)
        if rfid_uid is not None:
            conflict = self._fetchone(
                """
                SELECT id, username FROM employees
                WHERE rfid_uid = :uid
                LIMIT 1
            """,
                uid=rfid_uid,
            )
            if conflict:
                return None, f"Karta przypisana do {conflict['username']} (id={conflict['id']})."

        # --- hashowanie sekretów
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode() if password else None
        pin_hash = bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode() if pin else None

        # --- INSERT
        try:
            with self.engine.begin() as c:
                res = c.execute(
                    text(
                        """
                    INSERT INTO employees (username, first_name, last_name, role, is_admin, active, rfid_uid,
                                        password_hash, pin_hash, pin_plain)
                    VALUES (:u, :fn, :ln, :role, :adm, :act, :rfid, :ph, :pinh, :pinp)
                """
                    ),
                    dict(
                        u=login,
                        fn=first_name,
                        ln=last_name,
                        role=role,
                        adm=int(bool(is_admin)),
                        act=int(bool(active)),
                        rfid=rfid_uid,
                        ph=pw_hash,
                        pinh=pin_hash,
                        pinp=pin,
                    ),
                )
                new_id = res.lastrowid  # MySQL last insert id (per-connection)
        except SQLAlchemyError as e:
            # przy zbyt restrykcyjnym schemacie (rfid_uid NOT NULL) zwróci błąd spójny dla UI
            return None, f"Błąd zapisu użytkownika: {e}"

        return self.get_employee(new_id), None

    def update_employee_basic(
        self,
        emp_id: int,
        *,
        login: str,
        first_name: str,
        last_name: str,
        role: str,
        is_admin: bool,
        active: bool,
    ):
        # sprawdź konflikt loginu
        conflict = self._fetchone(
            """
            SELECT 1 FROM employees WHERE username=:u AND id<>:id LIMIT 1
        """,
            u=login,
            id=emp_id,
        )
        if conflict:
            return "Login jest już zajęty."
        with self.engine.begin() as c:
            c.execute(
                text(
                    """
                UPDATE employees
                SET username=:u, first_name=:fn, last_name=:ln, role=:role,
                    is_admin=:adm, active=:act
                WHERE id=:id
            """
                ),
                dict(u=login, fn=first_name, ln=last_name, role=role, adm=int(is_admin), act=int(active), id=emp_id),
            )
        return None

    def reset_password(self, emp_id: int, new_password: str):
        h = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        with self.engine.begin() as c:
            c.execute(text("UPDATE employees SET password_hash=:h WHERE id=:id"), dict(h=h, id=emp_id))
        return None

    def reset_pin(self, emp_id: int, new_pin: str):
        if not new_pin.isdigit() or not (4 <= len(new_pin) <= 8):
            return "PIN musi mieć 4–8 cyfr."
        h = bcrypt.hashpw(new_pin.encode(), bcrypt.gensalt()).decode()
        with self.engine.begin() as c:
            c.execute(
                text(
                    """
                UPDATE employees
                   SET pin_hash=:h,
                       pin_plain=:p
                 WHERE id=:id
            """
                ),
                dict(h=h, p=new_pin, id=emp_id),
            )
        return None

    def clear_pin(self, emp_id: int):
        with self.engine.begin() as c:
            c.execute(text("UPDATE employees SET pin_hash=NULL, pin_plain=NULL WHERE id=:id"), dict(id=emp_id))
        return None

    def assign_card(self, emp_id: int, rfid_uid: str | None):
        uid = rfid_uid or None  # '' -> None
        if uid:
            conflict = self._fetchone(
                """
                SELECT id, username FROM employees WHERE rfid_uid=:uid AND id<>:id LIMIT 1
            """,
                uid=uid,
                id=emp_id,
            )
            if conflict:
                return f"Karta przypisana do {conflict['username']} (id={conflict['id']})."
        with self.engine.begin() as c:
            c.execute(text("UPDATE employees SET rfid_uid=:uid WHERE id=:id"), dict(uid=uid, id=emp_id))
        return None

    def count_active_admins(self) -> int:
        row = self._fetchone(
            """
            SELECT COUNT(*) AS cnt FROM employees
            WHERE is_admin=1 AND active=1
            """
        )
        return int(row["cnt"]) if row else 0

    def is_active_admin(self, emp_id: int) -> tuple[bool, bool]:
        row = self._fetchone(
            """
            SELECT is_admin, active FROM employees WHERE id=:id
            """,
            id=emp_id,
        )
        if not row:
            return False, False
        return bool(row.get("is_admin")), bool(row.get("active"))

    # ===== API dla UI (logowania) =====
    def login_password(self, login: str, password: str, station_id: str):
        t0 = time.perf_counter()
        _dbg(f"[PASS] start login='{login}' station={station_id} pwd_len={len(password) if password else 0}")
        try:
            user = self._get_user_by_login(login)
            _dbg(f"[PASS] user_exists={bool(user)} login='{login}'")

            if not user:
                _dbg("[PASS][FAIL] brak usera")
                return None, "Nieprawidłowy login/hasło."

            _dbg_hash("[PASS] user.password_hash", user.get("password_hash"))

            ph = user.get("password_hash")
            if not ph:
                _dbg("[PASS][FAIL] brak password_hash")
                return None, "Nieprawidłowy login/hasło."

            ok, kind = verify_secret(ph, password or "")
            _dbg(f"[PASS] verify kind={kind} -> ok={ok}")
            if not ok:
                dt = (time.perf_counter() - t0) * 1000
                _dbg(f"[PASS][FAIL] ({dt:.1f} ms)")
                return None, "Nieprawidłowy login/hasło."

            sess = self._create_session_for(user, station_id, method="password")
            dt = (time.perf_counter() - t0) * 1000
            _dbg(f"[PASS][OK] user_id={user.get('id')} session_id={sess.get('id')} ({dt:.1f} ms)")
            return sess, None
        except Exception as e:
            _dbg(f"[PASS][ERROR] {e}\n{traceback.format_exc()}")
            return None, f"Błąd logowania: {e}"

    def login_pin(self, pin: str, station_id: str):
        pin = "" if pin is None else str(pin)  # zachowaj wiodące zera
        t0 = time.perf_counter()
        _dbg(f"[PIN] start pin_len={len(pin)} station={station_id}")
        try:
            user = self._get_user_by_pin_scan_all(pin)  # skan kandydatów po pin_hash
            _dbg(f"[PIN] user_found={bool(user)}")
            if not user:
                dt = (time.perf_counter() - t0) * 1000
                _dbg(f"[PIN][FAIL] no match ({dt:.1f} ms)")
                return None, "Nieprawidłowy PIN."

            _dbg_hash("[PIN] user.pin_hash", user.get("pin_hash"))
            sess = self._create_session_for(user, station_id, method="pin")
            dt = (time.perf_counter() - t0) * 1000
            _dbg(f"[PIN][OK] user_id={user.get('id')} session_id={sess.get('id')} ({dt:.1f} ms)")
            return sess, None
        except Exception as e:
            _dbg(f"[PIN][ERROR] {e}\n{traceback.format_exc()}")
            return None, f"Błąd logowania PIN: {e}"

    def login_card(self, uid: str, station_id: str):
        t0 = time.perf_counter()
        _dbg(f"[CARD] start uid={_mask(uid)} station={station_id}")
        try:
            user = self._get_user_by_card(uid)
            _dbg(f"[CARD] user_found={bool(user)}")
            if not user:
                dt = (time.perf_counter() - t0) * 1000
                _dbg(f"[CARD][FAIL] unknown card ({dt:.1f} ms)")
                return None, "Nieznana karta."
            sess = self._create_session_for(user, station_id, method="card")
            dt = (time.perf_counter() - t0) * 1000
            _dbg(f"[CARD][OK] user_id={user.get('id')} session_id={sess.get('id')} ({dt:.1f} ms)")
            return sess, None
        except Exception as e:
            _dbg(f"[CARD][ERROR] {e}\n{traceback.format_exc()}")
            return None, f"Błąd logowania kartą: {e}"

    # ===== Dostępy do DB (proste SQL + mappings) =====
    def _fetchone(self, sql: str, **params):
        _dbg(f"[SQL]\n{sql}\n         params={ {k:_mask(str(v),3,2) for k,v in params.items()} }")
        with self.engine.connect() as c:
            row = c.execute(text(sql), params).mappings().first()
            _dbg(f"[SQL] row_found={bool(row)}")
            return dict(row) if row else None

    def _fetchall(self, sql: str, **params):
        _dbg(f"[SQL]\n{sql}\n         params={ {k:_mask(str(v),3,2) for k,v in params.items()} }")
        with self.engine.connect() as c:
            rows = c.execute(text(sql), params).mappings().all()
            _dbg(f"[SQL] rows={len(rows)}")
            return [dict(r) for r in rows]

    # ===== Prywatne selecty dla logowania =====
    def _get_user_by_login(self, login: str):
        # employees + username
        return self._fetchone(
            """
            SELECT 
                id, 
                username       AS login,        -- alias, żeby reszta logiki działała
                password_hash, 
                pin_hash, 
                rfid_uid, 
                active,
                first_name, 
                last_name, 
                is_admin, 
                role
            FROM employees
            WHERE username = :login
            LIMIT 1
        """,
            login=login,
        )

    def _get_user_by_card(self, uid: str):
        # employees + rfid_uid
        return self._fetchone(
            """
            SELECT 
                id, 
                username       AS login,
                password_hash, 
                pin_hash, 
                rfid_uid, 
                active,
                first_name, 
                last_name, 
                is_admin, 
                role
            FROM employees
            WHERE rfid_uid = :uid
            LIMIT 1
        """,
            uid=uid,
        )

    def _get_user_by_pin_scan_all(self, pin: str):
        """
        Skanujemy wszystkich z ustawionym pin_hash i w Pythonie porównujemy (bcrypt/sha256).
        """
        candidates = self._fetchall(
            """
            SELECT 
                id, 
                username       AS login,
                password_hash, 
                pin_hash, 
                rfid_uid, 
                active,
                first_name, 
                last_name, 
                is_admin, 
                role
            FROM employees
            WHERE pin_hash IS NOT NULL AND pin_hash <> ''
              AND active = 1
        """
        )
        _dbg(f"[PIN] candidates={len(candidates)}")
        for u in candidates:
            ok, kind = verify_secret(u.get("pin_hash", ""), pin)
            _dbg(f"[PIN] try user_id={u.get('id')} login='{u.get('login')}' kind={kind} ok={ok}")
            if ok:
                return u
        return None

    def _create_session_for(self, user: dict, station_id: str, method: str) -> dict:
        sess = {
            "id": f"mem-{user.get('id')}-{int(time.time())}",
            "user_id": user.get("id"),
            "login": user.get("login"),
            "first_name": user.get("first_name") or "",
            "last_name": user.get("last_name") or "",
            "name": f"{(user.get('first_name') or '').strip()} {(user.get('last_name') or '').strip()}".strip(),
            "role": user.get("role"),
            "is_admin": bool(user.get("is_admin")),
            "rfid_uid": user.get("rfid_uid"),
            "active": user.get("active"),
            "station": station_id,
            "method": method,   # <— ważne dla main.py
        }
        _dbg(f"[SESS] created {sess}")
        return sess

    # NEW: szybkie wyszukiwanie stanów po nazwie/SKU
    def search_stock(self, q: str, limit: int = 200) -> list[dict]:
        pattern = f"%{q.strip()}%" if q else "%"
        sql = """
            SELECT i.id AS item_id, i.sku, i.name, i.uom,
                COALESCE(SUM(l.qty_available), 0) AS qty_available
            FROM lots l
            JOIN items i ON i.id = l.item_id
            WHERE (i.name LIKE :q OR i.sku LIKE :q) AND COALESCE(l.qty_available,0) > 0
            GROUP BY i.id, i.sku, i.name, i.uom
            ORDER BY i.name
            LIMIT :lim
        """
        with self.engine.connect() as c:
            rows = c.execute(text(sql), {"q": pattern, "lim": int(limit)}).mappings().all()
        return [dict(r) for r in rows]
