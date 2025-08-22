from sqlalchemy import Column, BigInteger, String, Date, DateTime, Numeric, Enum, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

DocType = Enum('PRZYJECIE', 'FAKTURA', 'RW', 'ZWROT', 'INNE', name='doc_type')
LocType = Enum('WAREHOUSE', 'EMPLOYEE', 'SCRAP', name='loc_type')
MoveType = Enum('RECEIPT', 'ISSUE', 'RETURN', 'SCRAP', 'ADJUST', name='move_type')


class Document(Base):
    __tablename__ = 'documents'
    id = Column(BigInteger, primary_key=True)
    doc_type = Column(DocType, nullable=False)
    number = Column(String(64), nullable=False)
    doc_date = Column(Date, nullable=False)
    currency = Column(String(3), default='PLN')
    suma_netto = Column(Numeric(12, 2))
    suma_vat = Column(Numeric(12, 2))
    suma_brutto = Column(Numeric(12, 2))
    parse_conf = Column('parse_conf', String(3))
    parse_warnings = Column(JSON)

    lines = relationship("DocumentLine", back_populates="document")


class DocumentLine(Base):
    __tablename__ = 'document_lines'
    id = Column(BigInteger, primary_key=True)
    document_id = Column(BigInteger, ForeignKey('documents.id'), nullable=False)
    item_id = Column(BigInteger, nullable=False)
    qty = Column(Numeric(12, 3), nullable=False)
    unit_price_netto = Column(Numeric(12, 4), nullable=False)
    line_netto = Column(Numeric(12, 2), nullable=False)
    vat_proc = Column(Numeric(5, 2))
    line_brutto = Column(Numeric(12, 2))
    currency = Column(String(3), default='PLN')

    document = relationship("Document", back_populates="lines")
    lots = relationship("Lot", back_populates="source_line")


class Location(Base):
    __tablename__ = 'locations'
    id = Column(BigInteger, primary_key=True)
    name = Column(String(100), nullable=False)
    type = Column(LocType, nullable=False)
    employee_id = Column(BigInteger)


class Lot(Base):
    __tablename__ = 'lots'
    id = Column(BigInteger, primary_key=True)
    item_id = Column(BigInteger, nullable=False)
    document_line_id = Column(BigInteger, ForeignKey('document_lines.id'), nullable=False)
    qty_received = Column(Numeric(12, 3), nullable=False)
    qty_available = Column(Numeric(12, 3), nullable=False)
    unit_cost_netto = Column(Numeric(12, 4), nullable=False)
    currency = Column(String(3), default='PLN')
    ts = Column(DateTime)

    source_line = relationship("DocumentLine", back_populates="lots")


class Movement(Base):
    __tablename__ = 'movements'
    id = Column(BigInteger, primary_key=True)
    ts = Column(DateTime)
    item_id = Column(BigInteger, nullable=False)
    qty = Column(Numeric(12, 3), nullable=False)
    from_location_id = Column(BigInteger)
    to_location_id = Column(BigInteger)
    movement_type = Column(MoveType, nullable=False)
    operation_uuid = Column(String(36))  # ⬅️ nowa kolumna na idempotencję
    document_line_id = Column(BigInteger, ForeignKey('document_lines.id'))

    allocations = relationship("MovementAllocation", back_populates="movement")


class MovementAllocation(Base):
    __tablename__ = 'movement_allocations'
    movement_id = Column(BigInteger, ForeignKey('movements.id'), primary_key=True)
    lot_id = Column(BigInteger, ForeignKey('lots.id'), primary_key=True)
    qty = Column(Numeric(12, 3), nullable=False)
    unit_cost_netto = Column(Numeric(12, 4), nullable=False)

    movement = relationship("Movement", back_populates="allocations")
