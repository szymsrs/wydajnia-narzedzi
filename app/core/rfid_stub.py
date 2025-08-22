# app/core/rfid_stub.py

class RFIDReader:
    """Stub interfejsu do czytnika RFID/PIN.
    
    W produkcji zostanie zastąpiony klasą, która faktycznie komunikuje się
    z czytnikiem kart. Tutaj zwracamy None, żeby aplikacja działała w trybie
    developerskim/offline.
    """

    def read_token(self, allow_pin: bool = True) -> str | None:
        """
        Zwraca UID karty lub (jeśli allow_pin=True) – PIN.
        W trybie stub zawsze zwraca None.
        
        Args:
            allow_pin (bool): Czy dopuszczalne jest podanie PIN zamiast karty.
                              Używane w fallbacku, gdy nie ma karty RFID.
        
        Returns:
            str | None: UID/PIN, lub None gdy brak odczytu.
        """
        return None
