# Contributing

## Konwencja commitów

Stosujemy [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<scope>): <opis zmiany>
```

Do typowych `type` należą `feat`, `fix`, `docs`, `chore` i inne.

## Warstwy architektury

Kod jest podzielony na warstwy:

- `ui` – interfejs użytkownika,
- `dal` – dostęp do danych,
- `services` – logika biznesowa.

Zmiany trzymaj w odpowiednich folderach i utrzymuj zależności tylko w jedną stronę (ui → services → dal).


