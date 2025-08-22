from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import select, update, and_, func
from sqlalchemy.orm import Session
import uuid

from app.dal.models import Document, DocumentLine, Lot, Movement, MovementAllocation, Location
from app.dal.tx import for_update
from app.dal.retry import retry_deadlock
from app.dal.errors import NegativeStockError

DEC2 = Decimal('0.01'); DEC3 = Decimal('0.001'); DEC4 = Decimal('0.0001')

def q(x: Decimal, qexp=DEC3) -> Decimal:
    return (x.quantize(qexp) if isinstance(x, Decimal) else Decimal(str(x)).quantize(qexp))

# --- Helpers

def get_warehouse_location_id(session: Session) -> int:
    wid = session.execute(select(Location.id).where(Location.type=='WAREHOUSE')).scalar()
    if not wid:
        # utwórz magazyn jeśli nie istnieje
        loc = Location(name='Magazyn', type='WAREHOUSE')
        session.add(loc); session.flush()
        wid = loc.id
    return wid

def ensure_scrap_location(session: Session) -> int:
    sid = session.execute(select(Location.id).where(Location.type=='SCRAP')).scalar()
    if not sid:
        loc = Location(name='Złom', type='SCRAP')
        session.add(loc); session.flush()
        sid = loc.id
    return sid

def ensure_employee_location(session: Session, employee_id: int, name: str) -> int:
    lid = session.execute(
        select(Location.id).where(and_(Location.type=='EMPLOYEE', Location.employee_id==employee_id))
    ).scalar()
    if not lid:
        loc = Location(name=name, type='EMPLOYEE', employee_id=employee_id)
        session.add(loc); session.flush()
        lid = loc.id
    return lid

def create_document(session: Session, *, doc_type: str, number: str, doc_date: date,
                    currency='PLN', suma_netto=None, suma_vat=None, suma_brutto=None,
                    parse_conf=None, parse_warnings=None) -> Document:
    d = Document(doc_type=doc_type, number=number, doc_date=doc_date,
                 currency=currency, suma_netto=suma_netto, suma_vat=suma_vat, suma_brutto=suma_brutto,
                 parse_conf=parse_conf, parse_warnings=parse_warnings)
    session.add(d); session.flush()
    return d

# --- PRZYJĘCIE: z linii dokumentu tworzymy partię + movement RECEIPT

def receipt_from_document_line(session: Session, *, document_id: int, item_id: int,
                               qty: Decimal, unit_price_netto: Decimal,
                               line_netto: Decimal, vat_proc=None, line_brutto=None,
                               currency='PLN') -> tuple[DocumentLine, Lot, Movement]:
    dl = DocumentLine(document_id=document_id, item_id=item_id,
                      qty=q(qty), unit_price_netto=q(unit_price_netto, DEC4),
                      line_netto=q(line_netto, DEC2), vat_proc=vat_proc,
                      line_brutto=line_brutto, currency=currency)
    session.add(dl); session.flush()

    lot = Lot(item_id=item_id, document_line_id=dl.id,
              qty_received=dl.qty, qty_available=dl.qty,
              unit_cost_netto=dl.unit_price_netto, currency=currency)
    session.add(lot); session.flush()

    wid = get_warehouse_location_id(session)
    mv = Movement(item_id=item_id, qty=dl.qty,
                  from_location_id=None, to_location_id=wid,
                  movement_type='RECEIPT', document_line_id=dl.id, ts=datetime.now())
    session.add(mv); session.flush()

    # alokacja 1:1 (przyjęcie -> partia)
    ma = MovementAllocation(movement_id=mv.id, lot_id=lot.id,
                            qty=dl.qty, unit_cost_netto=dl.unit_price_netto)
    session.add(ma)
    return dl, lot, mv

# --- ISSUE: FIFO z magazynu do pracownika, z alokacjami

@retry_deadlock()
def issue_to_employee(
    session: Session,
    *,
    employee_id: int,
    employee_name: str,
    item_id: int,
    qty: Decimal,
    operation_uuid: str | None = None,
) -> Movement:
    qty = q(qty)
    if qty <= 0:
        raise ValueError("qty must be > 0")

    # blokujemy partie FIFO do odczytu/aktualizacji
    lots = session.execute(
        for_update(
            select(Lot)
            .where(and_(Lot.item_id == item_id, Lot.qty_available > 0))
            .order_by(Lot.ts.asc(), Lot.id.asc())
        )
    ).scalars().all()

    need = qty
    used = []  # (lot, take_qty)
    for lot in lots:
        if need <= 0:
            break
        take = min(lot.qty_available, need)
        if take > 0:
            used.append((lot, take))
            need = q(need - take)
    if need > 0:
        raise ValueError(f"Brak ilości w magazynie. Brakuje {need}")

    emp_loc = ensure_employee_location(session, employee_id, employee_name)
    wid = get_warehouse_location_id(session)

    # Idempotencja
    op_uuid = operation_uuid or str(uuid.uuid4())
    existing = session.execute(
        select(Movement).where(Movement.operation_uuid == op_uuid)
    ).scalar_one_or_none()
    if existing:
        return existing

    mv = Movement(
        item_id=item_id,
        qty=qty,
        from_location_id=wid,
        to_location_id=emp_loc,
        movement_type='ISSUE',
        ts=datetime.now(),
        operation_uuid=op_uuid,
    )
    session.add(mv); session.flush()

    # aktualizuj partie + alokacje
    for lot, take in used:
        lot.qty_available = q(Decimal(lot.qty_available) - take)
        if Decimal(lot.qty_available) < 0:
            # dodatkowa bariera w warstwie aplikacyjnej (oprócz CHECK/triggerów w DB)
            raise NegativeStockError(f"lot {lot.id} would be negative")
        session.add(MovementAllocation(
            movement_id=mv.id,
            lot_id=lot.id,
            qty=take,
            unit_cost_netto=lot.unit_cost_netto
        ))
    return mv

# --- RETURN: odwzorowanie KONKRETNYCH alokacji z wcześniejszych ISSUE danego pracownika

@retry_deadlock()
def return_from_employee(
    session: Session,
    *,
    employee_id: int,
    employee_name: str,
    allocations_to_return: list[dict],
    doc_number: str | None = None,
    operation_uuid: str | None = None,
) -> Movement:
    """
    allocations_to_return: lista słowników:
      { "movement_id": <ISSUE movement id>, "lot_id": <lot>, "qty": <Decimal> }

    Zasada: tworzymy dokument ZWROT + linię na każdy (item, lot) zestaw,
    a następnie dla każdej pozycji ZWROTU tworzymy NOWĄ partię (lot) z tym samym kosztem,
    i alokujemy RETURN do nowej partii.
    """
    emp_loc = ensure_employee_location(session, employee_id, employee_name)
    wid = get_warehouse_location_id(session)

    # Grupa według item_id i unit_cost (z oryginalnych partii) aby zminimalizować liczbę linii
    # Pobierz meta dla każdej alokacji
    to_process = []
    for a in allocations_to_return:
        lot = session.execute(
            for_update(select(Lot).where(Lot.id == a["lot_id"]))
        ).scalar_one_or_none()
        if not lot:
            raise ValueError(f"Nie ma partii lot_id={a['lot_id']}")
        mv_issue = session.get(Movement, a["movement_id"])
        if not mv_issue or mv_issue.movement_type != 'ISSUE':
            raise ValueError(f"movement_id={a['movement_id']} nie jest ISSUE")
        qty = q(Decimal(str(a["qty"])))
        if qty <= 0:
            continue
        # weryfikacja: pracownik jest FROM w RETURN i TO w ISSUE
        if mv_issue.to_location_id != emp_loc:
            raise ValueError("Alokacja nie należy do tego pracownika")

        # weryfikacja limitu: nie można oddać więcej niż wydano z tej partii do tego movementu
        alloc = session.execute(
            select(MovementAllocation).where(
                and_(MovementAllocation.movement_id==mv_issue.id,
                     MovementAllocation.lot_id==lot.id)
            )
        ).scalar_one_or_none()
        if not alloc:
            raise ValueError("Brak alokacji ISSUE dla wskazanego movement/lot")
        # policz ile już zwrócono z tej alokacji
        already_ret = session.execute(
            select(func.coalesce(func.sum(MovementAllocation.qty), 0)).join(Movement).where(
                and_(MovementAllocation.lot_id==lot.id,
                     Movement.movement_type=='RETURN',
                     Movement.from_location_id==emp_loc,  # return od tego pracownika
                     MovementAllocation.unit_cost_netto==alloc.unit_cost_netto)
            )
        ).scalar()
        max_returnable = q(Decimal(alloc.qty) - Decimal(already_ret))
        if qty > max_returnable:
            raise ValueError(f"Za duża ilość do zwrotu (max {max_returnable}) dla lot {lot.id}")

        to_process.append({
            "item_id": lot.item_id,
            "qty": qty,
            "unit_cost": Decimal(lot.unit_cost_netto),
            "currency": lot.currency
        })

    if not to_process:
        raise ValueError("Nic do zwrotu")

    # Stwórz dokument ZWROT (1 nagłówek na całość)
    if not doc_number:
        doc_number = f"ZW/{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    d = create_document(session, doc_type='ZWROT', number=doc_number, doc_date=date.today(), currency='PLN')

    total_net = Decimal('0.00')

    # Utwórz jedną linię dokumentu per (item_id, unit_cost)
    grouped = {}
    for x in to_process:
        key = (x["item_id"], x["unit_cost"])
        g = grouped.get(key, {"qty": Decimal('0'), "currency": x["currency"]})
        g["qty"] = q(g["qty"] + x["qty"])
        grouped[key] = g

    return_mov = Movement(
        item_id=0, qty=0,  # uzupełnimy niżej
        from_location_id=emp_loc, to_location_id=wid,
        movement_type='RETURN', ts=datetime.now(),
        operation_uuid=operation_uuid or str(uuid.uuid4()),
    )
    session.add(return_mov); session.flush()

    # Dla każdej grupy twórz linię, NOWĄ partię i alokację RETURN -> nowa partia
    for (item_id, unit_cost), g in grouped.items():
        qty = g["qty"]
        line_net = (qty * unit_cost).quantize(DEC2)
        total_net += line_net

        dl = DocumentLine(document_id=d.id, item_id=item_id,
                          qty=qty, unit_price_netto=unit_cost,
                          line_netto=line_net, currency=g["currency"])
        session.add(dl); session.flush()

        # NOWA partia z kosztu zwracanego
        lot_new = Lot(item_id=item_id, document_line_id=dl.id,
                      qty_received=qty, qty_available=qty,
                      unit_cost_netto=unit_cost, currency=g["currency"])
        session.add(lot_new); session.flush()

        # Alokacja zwrotu (RETURN) do nowej partii
        session.add(MovementAllocation(movement_id=return_mov.id, lot_id=lot_new.id,
                                       qty=qty, unit_cost_netto=unit_cost))

    # uzupełnij movement item_id/qty (0 → wielopozycyjny; zostaw 0/None jako „zbiorczy”)
    return_mov.item_id = None
    return_mov.qty = None

    # sumy dokumentu
    d.suma_netto = total_net
    d.suma_brutto = None
    d.suma_vat = None

    return return_mov

# --- SCRAP (ze wskazaniem pracownika lub magazynu, odwzorowanie alokacji jak w RETURN)
def scrap_from_employee(session: Session, *, employee_id: int, employee_name: str,
                        allocations_to_scrap: list[dict], reason: str | None = None) -> Movement:
    emp_loc = ensure_employee_location(session, employee_id, employee_name)
    scrap_loc = ensure_scrap_location(session)

    mv = Movement(item_id=None, qty=None,
                  from_location_id=emp_loc, to_location_id=scrap_loc,
                  movement_type='SCRAP', ts=datetime.now())
    session.add(mv); session.flush()

    for a in allocations_to_scrap:
        lot = session.get(Lot, a["lot_id"])
        qty = q(Decimal(str(a["qty"])))
        if qty <= 0: 
            continue
        # nic nie przywracamy do magazynu; tylko alokacja zużycia
        session.add(MovementAllocation(movement_id=mv.id, lot_id=lot.id,
                                       qty=qty, unit_cost_netto=lot.unit_cost_netto))
    return mv
