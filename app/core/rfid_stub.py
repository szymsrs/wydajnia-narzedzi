class RFIDReader:
    """Stub interfejsu do czytnika RFID/PIN."""

    def read_token(self) -> str | None:
        """Zwraca UID karty lub PIN; None gdy brak odczytu."""

        return None

